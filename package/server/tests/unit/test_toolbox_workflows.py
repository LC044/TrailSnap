"""Scoped file mutations against isolated SQLite + disposable real files."""
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import Album, AlbumPhoto, Photo, PhotoMetadata, Task, ToolboxPlanItem, User
from app.schemas.toolbox import ExecuteRequest, MediaScope, PlanRequest, ToolConfig
from app.service.toolbox_scope import allowed_directory, scope_preview
from app.service.toolbox_plans import create_plan, validate_template
from app.service.toolbox_execution import execute_plan, recovery_plan, start_plan

pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.delenv("TS_DESKTOP_PORTABLE", raising=False)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        user = User(id=uuid4(), username="toolbox", hashed_password="unused",
                    settings={"storage": {"external_directories": [str(tmp_path)]}})
        other = User(id=uuid4(), username="other", hashed_password="unused")
        db.add_all([user, other])
        db.commit()

        def add(relative, when=datetime(2026, 5, 2), owner=None, city="杭州市", **values):
            path = tmp_path / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(relative.encode())
            photo = Photo(id=uuid4(), owner_id=owner or user.id, filename=path.name,
                          file_path=str(path), file_type="image", photo_time=when, **values)
            photo.metadata_info = PhotoMetadata(photo_id=photo.id, province="浙江省", city=city)
            db.add(photo)
            db.commit()
            return photo
        yield SimpleNamespace(db=db, user=user, other=other, root=tmp_path, add=add)
    engine.dispose()


def run(library, plan, selected=None):
    start_plan(library.db, library.user, plan.id, ExecuteRequest(version=plan.version, confirmed=True, selected_items=selected))
    task = library.db.get(Task, plan.task_id)
    return asyncio.run(execute_plan(None, task, library.db))


def folder_scope(library, relative="2026"):
    return MediaScope(source="folders", folders=[str(library.root / relative)])


def test_scope_requires_explicit_source():
    with pytest.raises(ValidationError):
        MediaScope(source="selected")
    with pytest.raises(ValidationError):
        MediaScope(source="filter")
    with pytest.raises(ValidationError):
        PlanRequest.model_validate({"config": {"kind": "rename"}})
    with pytest.raises(ValidationError):
        ToolConfig(kind="organize")


def test_date_filters_all_strategies_and_folder_boundary(library):
    current = library.add("2026/05/02/a.jpg")
    library.add("2026-backup/b.jpg")
    library.add("2026/old.jpg", when=datetime(2025, 12, 31))
    scope = folder_scope(library)
    scope.start_date, scope.end_date = datetime(2026, 1, 1).date(), datetime(2026, 12, 31).date()
    preview = scope_preview(library.db, library.user, scope)
    assert preview["total"] == 1
    assert preview["items"][0]["id"] == str(current.id)
    plan = create_plan(library.db, library.user, PlanRequest(scope=scope, config=ToolConfig(
        kind="organize", target=str(library.root / "2026"), action="move", layout="preserve",
        rules=[{"strategy": "location", "granularity": "province_city", "nested": True}],
    )))
    assert plan.summary["ready"] == 1
    source = Path(current.file_path)
    assert source.exists(), "Preview must be read-only"
    assert not (source.parent / "浙江省").exists()
    run(library, plan)
    target = library.root / "2026/05/02/浙江省/杭州市/a.jpg"
    assert target.exists() and not source.exists()
    assert (library.root / "2026-backup/b.jpg").exists()
    assert (library.root / "2026/old.jpg").exists()
    again = create_plan(library.db, library.user, PlanRequest(scope=scope, config=ToolConfig.model_validate(plan.request["config"])))
    assert again.summary["ready"] == 0


def test_album_scope_is_union_and_owned(library):
    photo = library.add("a.jpg")
    albums = [Album(id=uuid4(), owner_id=library.user.id, type="user", name=name) for name in ("A", "B")]
    library.db.add_all(albums)
    library.db.flush()
    library.db.add_all([AlbumPhoto(album_id=album.id, photo_id=photo.id) for album in albums])
    library.db.commit()
    assert scope_preview(library.db, library.user, MediaScope(source="albums", album_ids=[a.id for a in albums]))["total"] == 1
    with pytest.raises(ValueError, match="相册"):
        scope_preview(library.db, library.other, MediaScope(source="albums", album_ids=[albums[0].id]))


def test_selection_ownership_and_exclusions(library):
    owned = library.add("owned.jpg")
    other = library.add("other.jpg", owner=library.other.id)
    with pytest.raises(ValueError, match="权限"):
        scope_preview(library.db, library.user, MediaScope(source="selected", photo_ids=[owned.id, other.id]))
    scope = MediaScope(source="selected", photo_ids=[owned.id], excluded_ids=[owned.id])
    assert scope_preview(library.db, library.user, scope)["total"] == 0


def test_rename_template_validation_collision_and_memory(library):
    one = library.add("one.jpg")
    two = library.add("two.jpg")
    with pytest.raises(ValueError, match="变量"):
        validate_template("{dat}")
    config = ToolConfig(kind="rename", template="IMG_{date}_{date}")
    scope = MediaScope(source="selected", photo_ids=[one.id, two.id])
    plan = create_plan(library.db, library.user, PlanRequest(scope=scope, config=config))
    names = [Path(row.target).name for row in library.db.query(ToolboxPlanItem).filter_by(plan_id=plan.id)]
    assert sorted(names) == ["IMG_2026-05-02_2026-05-02(1).jpg", "IMG_2026-05-02_2026-05-02.jpg"]
    run(library, plan)
    library.db.refresh(library.user)
    assert library.user.settings["toolbox"]["recent"][0]["template"] == config.template
    assert one.filename.startswith("IMG_")


def test_confirmation_expiry_and_forged_tasks(library):
    photo = library.add("a.jpg")
    plan = create_plan(library.db, library.user, PlanRequest(
        scope=MediaScope(source="selected", photo_ids=[photo.id]), config=ToolConfig(kind="rename")))
    with pytest.raises(ValueError, match="确认"):
        start_plan(library.db, library.user, plan.id, ExecuteRequest(version=1))
    library.db.rollback()
    forged = Task(id=uuid4(), owner_id=library.user.id, type="BATCH_RENAME", payload={"toolbox_plan_id": str(plan.id)})
    with pytest.raises(ValueError, match="执行确认"):
        asyncio.run(execute_plan(None, forged, library.db))
    plan.expires_at = datetime.utcnow() - timedelta(seconds=1)
    library.db.commit()
    with pytest.raises(ValueError, match="过期"):
        start_plan(library.db, library.user, plan.id, ExecuteRequest(version=1, confirmed=True))


def test_racing_target_never_overwritten(library):
    photo = library.add("a.jpg")
    plan = create_plan(library.db, library.user, PlanRequest(
        scope=MediaScope(source="selected", photo_ids=[photo.id]), config=ToolConfig(kind="rename", template="new")))
    (library.root / "new.jpg").write_bytes(b"external writer")
    result = run(library, plan)
    assert result["failed_count"] == 1
    assert (library.root / "new.jpg").read_bytes() == b"external writer"
    assert (library.root / "a.jpg").exists()
    assert photo.filename == "a.jpg"


def test_combined_rules_and_app_albums_do_not_move_files(library):
    photo = library.add("source.jpg")
    config = ToolConfig(kind="album", rules=[
        {"strategy": "time", "granularity": "year"},
        {"strategy": "location", "granularity": "city"},
    ])
    plan = create_plan(library.db, library.user, PlanRequest(
        scope=MediaScope(source="selected", photo_ids=[photo.id]), config=config))
    run(library, plan)
    album = library.db.query(Album).filter_by(owner_id=library.user.id).one()
    assert album.name == "2026 / 杭州市"
    assert album.num_photos == 1
    assert (library.root / "source.jpg").exists()


def test_move_and_rename_can_be_undone_with_conflict_checks(library):
    photo = library.add("old.jpg")
    plan = create_plan(library.db, library.user, PlanRequest(
        scope=MediaScope(source="selected", photo_ids=[photo.id]), config=ToolConfig(kind="rename", template="new")))
    run(library, plan)
    undo = recovery_plan(library.db, library.user, plan, undo=True)
    assert undo.summary["ready"] == 1
    run(library, undo)
    assert (library.root / "old.jpg").exists()
    assert not (library.root / "new.jpg").exists()


def test_cleanup_scope_candidates_require_manual_selection(library):
    one = library.add("2026/a.jpg", md5="identical")
    outside = library.add("2025/b.jpg", md5="identical")
    scope = folder_scope(library)
    config = ToolConfig(kind="cleanup", compare_all=True)
    plan = create_plan(library.db, library.user, PlanRequest(scope=scope, config=config))
    rows = library.db.query(ToolboxPlanItem).filter_by(plan_id=plan.id).all()
    assert len(rows) == 1 and rows[0].photo_id == one.id and rows[0].status == "candidate"
    with pytest.raises(ValueError, match="勾选"):
        start_plan(library.db, library.user, plan.id, ExecuteRequest(version=1, confirmed=True))
    library.db.rollback()
    run(library, plan, [rows[0].id])
    assert one.is_deleted and not outside.is_deleted
    assert (library.root / "2026/a.jpg").exists()


def test_stop_request_does_not_mutate_remaining_sources(library):
    photo = library.add("old.jpg")
    plan = create_plan(library.db, library.user, PlanRequest(
        scope=MediaScope(source="selected", photo_ids=[photo.id]), config=ToolConfig(kind="rename", template="new")))
    start_plan(library.db, library.user, plan.id, ExecuteRequest(version=1, confirmed=True))
    plan.stop_requested = True
    library.db.commit()
    asyncio.run(execute_plan(None, library.db.get(Task, plan.task_id), library.db))
    assert plan.status == "stopped"
    assert (library.root / "old.jpg").exists()


def test_directory_authorization(library, tmp_path):
    with pytest.raises(ValueError, match="越界"):
        allowed_directory(library.db, library.user, str(tmp_path.parent))


def test_copy_creates_owned_photo_and_skip_repeated_copy(library):
    photo = library.add("src/a.jpg")
    config = ToolConfig(kind="organize", target=str(library.root / "out"), action="copy")
    scope = MediaScope(source="selected", photo_ids=[photo.id])
    plan = create_plan(library.db, library.user, PlanRequest(scope=scope, config=config))
    run(library, plan)
    assert (library.root / "src/a.jpg").exists()
    assert library.db.query(Photo).count() == 2
    again = create_plan(library.db, library.user, PlanRequest(scope=scope, config=config))
    assert again.summary["ready"] == 0


def metadata_plan(library):
    from PIL import Image
    photo = library.add("original.jpg", md5="old")
    Image.new("RGB", (12, 12), "white").save(photo.file_path)
    config = ToolConfig(kind="metadata", time_mode="custom", custom_time="2024-01-02T03:04:05",
                        make="Test camera", only_missing_metadata=False)
    plan = create_plan(library.db, library.user, PlanRequest(
        scope=MediaScope(source="selected", photo_ids=[photo.id]), config=config))
    return photo, plan


def test_metadata_updates_file_hash_and_journey_transaction(library):
    import hashlib
    import piexif
    photo, plan = metadata_plan(library)
    result = run(library, plan)
    assert result["success_count"] == 1
    assert photo.photo_time == datetime(2024, 1, 2, 3, 4, 5)
    assert photo.metadata_info.make == "Test camera"
    content = Path(photo.file_path).read_bytes()
    assert photo.md5 == hashlib.md5(content).hexdigest()
    assert photo.size == len(content)
    assert photo.metadata_info.exif_info
    exif = piexif.load(photo.file_path)
    assert exif["Exif"][piexif.ExifIFD.DateTimeOriginal] == b"2024:01:02 03:04:05"
    assert library.db.query(Task).filter_by(type="ASSOCIATE_JOURNEYS").count() == 1
    assert not list(library.root.glob("*.toolbox-*"))


def test_metadata_commit_failure_restores_original_bytes(library, monkeypatch):
    photo, plan = metadata_plan(library)
    original = Path(photo.file_path).read_bytes()
    commit = library.db.commit
    failed = False

    def fail_once():
        nonlocal failed
        if not failed and photo.metadata_info.make == "Test camera":
            failed = True
            raise RuntimeError("simulated commit failure")
        commit()
    monkeypatch.setattr(library.db, "commit", fail_once)
    result = run(library, plan)
    assert result["failed_count"] == 1
    assert Path(photo.file_path).read_bytes() == original
    assert photo.photo_time == datetime(2026, 5, 2)
    assert photo.md5 == "old"
    assert photo.metadata_info.make is None
    assert not list(library.root.glob("*.toolbox-*"))


def test_same_plan_confirmation_is_idempotent_and_competing_plan_rejected(library):
    photo = library.add("a.jpg")
    request = PlanRequest(scope=MediaScope(source="selected", photo_ids=[photo.id]),
                          config=ToolConfig(kind="rename", template="new"))
    one = create_plan(library.db, library.user, request)
    two = create_plan(library.db, library.user, request)
    confirmed = ExecuteRequest(version=1, confirmed=True)
    start_plan(library.db, library.user, one.id, confirmed)
    task_id = one.task_id
    start_plan(library.db, library.user, one.id, confirmed)
    assert one.task_id == task_id
    with pytest.raises(ValueError, match="其他任务"):
        start_plan(library.db, library.user, two.id, confirmed)
    library.db.rollback()


def test_stopped_plan_retries_only_unprocessed_items(library):
    photo = library.add("a.jpg")
    original = create_plan(library.db, library.user, PlanRequest(
        scope=MediaScope(source="selected", photo_ids=[photo.id]), config=ToolConfig(kind="rename", template="new")))
    start_plan(library.db, library.user, original.id, ExecuteRequest(version=1, confirmed=True))
    original.stop_requested = True
    library.db.commit()
    asyncio.run(execute_plan(None, library.db.get(Task, original.task_id), library.db))
    retry = recovery_plan(library.db, library.user, original)
    assert retry.summary["ready"] == 1
    run(library, retry)
    assert photo.filename == "new.jpg"
    assert retry.summary["ready"] == 0


def test_cleanup_refuses_deleted_reference_at_execution(library):
    photo = library.add("2026/a.jpg", md5="same")
    retained = library.add("2025/b.jpg", md5="same")
    plan = create_plan(library.db, library.user, PlanRequest(
        scope=folder_scope(library), config=ToolConfig(kind="cleanup", compare_all=True)))
    row = library.db.query(ToolboxPlanItem).filter_by(plan_id=plan.id).one()
    start_plan(library.db, library.user, plan.id, ExecuteRequest(version=1, confirmed=True, selected_items=[row.id]))
    retained.is_deleted = True
    library.db.commit()
    result = asyncio.run(execute_plan(None, library.db.get(Task, plan.task_id), library.db))
    assert result["failed_count"] == 1
    assert not photo.is_deleted


def test_browser_folder_resolution_rejects_ambiguous_roots(library, monkeypatch):
    from app.service.toolbox_scope import canonical, resolve_browser_folder
    root = library.root / "photos"
    (root / "2026").mkdir(parents=True)
    monkeypatch.setattr("app.utils.path.get_user_roots", lambda *_: [str(root)])
    assert resolve_browser_folder(library.db, library.user, "photos/2026") == canonical(str(root / "2026"))
    with pytest.raises(ValueError, match="上级"):
        resolve_browser_folder(library.db, library.user, "photos/../outside")
    monkeypatch.setattr("app.utils.path.get_user_roots", lambda *_: [str(root), str(library.root / "other/photos")])
    with pytest.raises(ValueError, match="不唯一"):
        resolve_browser_folder(library.db, library.user, "photos/2026")


def test_auto_metadata_preserves_filename_time_repair(library):
    photo = library.add("IMG_20240304_050607.jpg")
    config = ToolConfig(kind="metadata", time_mode="auto", only_missing_metadata=False)
    plan = create_plan(library.db, library.user, PlanRequest(
        scope=MediaScope(source="selected", photo_ids=[photo.id]), config=config))
    row = library.db.query(ToolboxPlanItem).filter_by(plan_id=plan.id).one()
    assert row.detail["time"] == "2024-03-04T05:06:07"


def test_multiple_copy_outputs_retry_and_preview_skip_completed_targets(library):
    from app.db.models.tag import PhotoTag
    photo = library.add("src/a.jpg")
    photo.tags = [PhotoTag(id=uuid4(), tag_name=name, owner_id=library.user.id) for name in ("A", "B")]
    album = Album(id=uuid4(), owner_id=library.user.id, type="user", name="Original", num_photos=1)
    photo.albums = [album]
    library.db.commit()
    config = ToolConfig(kind="organize", target=str(library.root / "out"), action="copy", multi_group="all",
                        rules=[{"strategy": "category"}])
    request = PlanRequest(scope=MediaScope(source="selected", photo_ids=[photo.id]), config=config)
    plan = create_plan(library.db, library.user, request)
    assert plan.summary["ready"] == 2
    blocker = library.root / "out/B/a.jpg"
    blocker.parent.mkdir(parents=True)
    blocker.write_bytes(b"occupied")
    result = run(library, plan)
    assert result["success_count"] == result["failed_count"] == 1
    assert album.num_photos == 2
    blocker.unlink()
    retry = recovery_plan(library.db, library.user, plan)
    assert retry.summary["ready"] == 1
    run(library, retry)
    assert album.num_photos == 3
    assert (library.root / "out/A/a.jpg").exists()
    assert (library.root / "out/B/a.jpg").exists()
    again = create_plan(library.db, library.user, request)
    assert again.summary["ready"] == 0


def test_preferences_conflict_preserves_other_settings(library):
    from app.api.toolbox_workflows import save_preferences
    from app.schemas.toolbox import ToolboxPreferences
    saved = save_preferences(ToolboxPreferences(presets=[
        {"id": "travel", "name": "Travel", "config": {"kind": "rename", "template": "TRIP_{date}"}}]),
        library.db, library.user)
    assert saved.code == 0
    assert library.user.settings["storage"]["external_directories"] == [str(library.root)]
    assert library.user.settings["toolbox"]["presets"][0]["name"] == "Travel"
    conflict = save_preferences(ToolboxPreferences(version=0), library.db, library.user)
    assert conflict.code == 400
    assert library.user.settings["toolbox"]["presets"][0]["name"] == "Travel"
