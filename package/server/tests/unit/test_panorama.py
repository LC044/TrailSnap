"""Panorama metadata, ownership, derivatives, and persisted scan jobs."""
import asyncio
import hashlib
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import panorama as api
from app.api.deps import get_current_user
from app.db.models.photo import Photo, FileType
from app.db.models.task import Task, TaskType
from app.db.models.user import User
from app.dependencies import get_db
from app.service import panorama as service
from app.service.tasks.panorama import ScanPanoramaStrategy
from app.utils.image_loading import Image
from app.utils.panorama import DIMENSIONS, full_geometry, parse_gpano, apply_detection

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def xmp(geometry=None, elements=False, extra=""):
    data = geometry or full_geometry(800, 400)
    fields = {"ProjectionType": "equirectangular", **{tag: str(data[key]) for key, tag in DIMENSIONS.items()}}
    if elements:
        body = "".join(f"<p:{key}>{value}</p:{key}>" for key, value in fields.items())
        return f'<root xmlns:p="http://ns.google.com/photos/1.0/panorama/">{body}{extra}</root>'.encode()
    attributes = " ".join(f'p:{key}="{value}"' for key, value in fields.items())
    return f'<root xmlns:p="http://ns.google.com/photos/1.0/panorama/" {attributes} {extra}/>'.encode()


def test_metadata_namespace_elements_crops_and_rejection():
    geometry = full_geometry(800, 400)
    assert parse_gpano(xmp(), 800, 400) == geometry
    assert parse_gpano(xmp(elements=True), 800, 400) == geometry
    crop = dict(geometry, croppedWidth=600, croppedHeight=250, croppedX=100, croppedY=50)
    assert parse_gpano(xmp(crop), 600, 250) == crop
    for raw in (None, b"<broken", b'<!DOCTYPE x [<!ENTITY x "bad">]><x/>', b"x" * 2097153):
        assert parse_gpano(raw, 800, 400) is None
    assert parse_gpano(xmp(), 799, 400) is None
    assert parse_gpano(xmp(), 800, 400, orientation=6) is None
    assert parse_gpano(xmp(extra='p:UsePanoramaViewer="False"'), 800, 400) is None
    assert parse_gpano(xmp(extra='p:PosePitchDegrees="NaN"'), 800, 400) is None
    assert parse_gpano(xmp(dict(geometry, croppedX=1)), 800, 400) is None


def fixture_photo(db, tmp_path, name="panorama", metadata=True):
    owner = User(id=uuid4(), username=name, hashed_password="x")
    path = tmp_path / f"{name}.jpg"
    Image.new("RGB", (800, 400), (40, 80, 120)).save(path, xmp=xmp() if metadata else b"")
    row = Photo(id=uuid4(), owner_id=owner.id, filename=path.name, file_path=str(path),
                file_type=FileType.image, width=800, height=400, size=path.stat().st_size, is_deleted=False)
    db.add_all([owner, row]); db.commit()
    return owner, row


def test_detection_and_manual_override_survive_scan(face_sqlite_session, tmp_path, monkeypatch):
    monkeypatch.setattr(service, "_get_storage_root", lambda _: str(tmp_path / "cache"))
    db = face_sqlite_session
    owner, photo = fixture_photo(db, tmp_path)
    app = FastAPI(); app.include_router(api.router, prefix="/photos")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: owner
    with TestClient(app) as client:
        response = client.put(f"/photos/{photo.id}/panorama", json={"mode": "auto"}).json()
        assert response["code"] == 0 and response["data"]["projection"] == "equirectangular"
        assert client.put(f"/photos/{photo.id}/panorama", json={"mode": "ordinary"}).json()["code"] == 0
        task = Task(type=TaskType.SCAN_PANORAMA.value, owner_id=owner.id, payload={"photo_id": str(photo.id)})
        db.add(task); db.commit()
        assert task.photo_id == photo.id
        result = asyncio.run(ScanPanoramaStrategy().process(None, task, db))
        assert result == {"panorama": False}
        db.refresh(photo)
        assert photo.panorama_override == "ordinary" and photo.panorama_detected is not None
        assert client.put(f"/photos/{photo.id}/panorama", json={"mode": "auto"}).json()["data"]["projection"] == "equirectangular"
        image_response = client.get(f"/photos/{photo.id}/panorama/image")
        assert image_response.status_code == 200 and image_response.headers["content-type"] == "image/jpeg"
        assert image_response.headers["cache-control"] == "private, no-cache"
        # Invalid crop geometry must not corrupt the previous setting.
        response = client.put(f"/photos/{photo.id}/panorama", json={"mode": "equirectangular", "geometry": {"fullWidth": 1}}).json()
        assert response["code"] == 400
        stranger = User(id=uuid4(), username="stranger", hashed_password="x")
        db.add(stranger); db.commit()
        app.dependency_overrides[get_current_user] = lambda: stranger
        for method, route, payload in [("get", "", None), ("get", "/image", None), ("put", "", {"mode": "ordinary"})]:
            response = client.request(method, f"/photos/{photo.id}/panorama{route}", json=payload).json()
            assert response["code"] == 404
        del app.dependency_overrides[get_current_user]
        assert client.get(f"/photos/{photo.id}/panorama").status_code == 401


def test_plain_2_to_1_manual_and_derivative(face_sqlite_session, tmp_path, monkeypatch):
    db = face_sqlite_session
    owner, photo = fixture_photo(db, tmp_path, metadata=False)
    assert service.detect_file(photo.file_path) is None
    response = api.update_panorama(photo.id, api.PanoramaUpdate(mode="equirectangular"), db, owner)
    assert response.code == 0
    monkeypatch.setattr(service, "_get_storage_root", lambda _: str(tmp_path / "cache"))
    before = hashlib.sha256(Path(photo.file_path).read_bytes()).hexdigest()
    path, width, height = service.derivative(photo)
    assert (width, height) == (800, 400)
    assert service.derivative(photo)[0] == path
    with Image.open(path) as preview:
        assert preview.size == (800, 400)
    assert hashlib.sha256(Path(photo.file_path).read_bytes()).hexdigest() == before


def test_large_and_cropped_preview_bounds(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "_get_storage_root", lambda _: str(tmp_path / "cache"))
    path = tmp_path / "large.jpg"
    Image.new("RGB", (5000, 2500)).save(path)
    photo = SimpleNamespace(id=uuid4(), owner_id=uuid4(), file_path=str(path), width=5000, height=2500,
                            panorama_metadata=full_geometry(5000, 2500))
    assert service.derivative(photo)[1:] == (4096, 2048)
    photo.panorama_metadata = dict(full_geometry(10000, 5000), croppedWidth=5000, croppedHeight=2500, croppedX=2500, croppedY=1250)
    assert service.derivative(photo)[1:] == (2048, 1024)


def test_scan_cursor_owner_and_duplicate_jobs(face_sqlite_session, tmp_path, monkeypatch):
    from app.service.task_manager import TaskManager
    monkeypatch.setattr(TaskManager, "get_instance", lambda: SimpleNamespace(start_worker_for_pending_tasks=lambda: None))
    db = face_sqlite_session
    owner, first = fixture_photo(db, tmp_path)
    fixture_photo(db, tmp_path, name="other")
    second = Photo(id=uuid4(), owner_id=owner.id, filename="second.jpg", file_path=first.file_path,
                   file_type=FileType.image, width=800, height=400, is_deleted=False)
    db.add(second); db.commit()
    page = api.scan_panorama(None, 1, db, owner).data
    assert page["queued"] == 1 and page["next"]
    assert api.scan_panorama(None, 1, db, owner).data["queued"] == 0
    from uuid import UUID
    assert api.scan_panorama(UUID(page["next"]), 1, db, owner).data == {"queued": 1, "next": None}
    jobs = db.query(Task).filter(Task.type == TaskType.SCAN_PANORAMA.value).all()
    assert {job.photo_id for job in jobs} == {first.id, second.id}
    assert all(job.owner_id == owner.id for job in jobs)


def test_panorama_filter_and_schema(face_sqlite_session, tmp_path):
    from app.crud.photo import get_all_photos, get_timeline_stats
    from app.schemas.photo import Photo as PhotoSchema
    from datetime import datetime
    db = face_sqlite_session
    owner, photo = fixture_photo(db, tmp_path)
    photo.photo_time = datetime(2026, 2, 16)
    apply_detection(photo, full_geometry(800, 400)); db.commit()
    assert [row.id for row in get_all_photos(db, user_id=owner.id, is_panorama=True)] == [photo.id]
    assert get_all_photos(db, user_id=owner.id, is_panorama=False) == []
    assert get_timeline_stats(db, user_id=owner.id, is_panorama=True)["total_photos"] == 1
    assert PhotoSchema.model_validate(photo).panorama_projection == "equirectangular"


@pytest.mark.parametrize("filters, expected", [
    ({"file_types": ["panorama"]}, {"panorama"}),
    ({"file_types": ["video", "panorama"]}, {"video", "panorama"}),
    ({"file_types": ["image"]}, {"image", "panorama"}),
    ({"file_types": ["image", "panorama", "panorama"]}, {"image", "panorama"}),
    ({"file_types": ["live_photo", "panorama"]}, {"live_photo", "panorama"}),
    ({"file_types": ["image", "video", "live_photo", "panorama"]}, {"image", "video", "live_photo", "panorama"}),
    ({"file_types": []}, {"image", "video", "live_photo", "panorama"}),
    ({"file_type": "panorama"}, {"panorama"}),
    ({"file_types": ["video", "panorama"], "years": [2025]}, set()),
    ({"file_types": ["video", "panorama"], "is_panorama": True}, {"panorama"}),
    ({"file_types": ["video", "panorama"], "is_panorama": False}, {"video"}),
])
def test_panorama_virtual_type_union_and_timeline(face_sqlite_session, tmp_path, filters, expected):
    from datetime import datetime
    from app.crud.photo import get_all_photos, get_timeline_stats, get_filter_options
    db = face_sqlite_session
    owner, panorama = fixture_photo(db, tmp_path)
    panorama.photo_time = datetime(2026, 2, 16)
    apply_detection(panorama, full_geometry(800, 400))
    for name in ("image", "video", "live_photo", "deleted"):
        db.add(Photo(id=uuid4(), owner_id=owner.id, filename=name,
                     file_path=str(tmp_path / name), file_type=FileType.video if name == "deleted" else FileType(name),
                     photo_time=panorama.photo_time, is_deleted=name == "deleted"))
    stranger, other = fixture_photo(db, tmp_path, name="stranger")
    other.photo_time = panorama.photo_time
    apply_detection(other, full_geometry(800, 400))
    db.commit()
    rows = get_all_photos(db, user_id=owner.id, **filters)
    names = ["panorama" if row.id == panorama.id else row.filename for row in rows]
    assert set(names) == expected
    assert len(names) == len(expected)
    stats = get_timeline_stats(db, user_id=owner.id, **filters)
    assert stats["total_photos"] == len(expected)
    assert get_filter_options(db, owner.id)["file_types"] == ["image", "video", "live_photo", "panorama"]


def test_postgres_panorama_migration_compiles_without_database():
    import importlib.util
    import io
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = Path(__file__).parents[2] / "alembic/versions/bbc00427d4d5_add_panorama_photo_metadata.py"
    spec = importlib.util.spec_from_file_location("panorama_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    output = io.StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})
    with Operations.context(context):
        migration.upgrade()
        migration.downgrade()
    sql = output.getvalue()
    assert "ADD COLUMN panorama_metadata JSON" in sql
    assert "CREATE INDEX ix_photos_panorama_projection" in sql
    assert "DROP COLUMN panorama_override" in sql


def test_panorama_reads_do_not_lock_photo_rows(face_sqlite_session, tmp_path, monkeypatch):
    """A reader must not wait on unrelated processing transactions for this photo."""
    from sqlalchemy.orm import Query
    from sqlalchemy.dialects import postgresql
    db = face_sqlite_session
    owner, photo = fixture_photo(db, tmp_path)
    apply_detection(photo, full_geometry(800, 400)); db.commit()
    monkeypatch.setattr(service, "_get_storage_root", lambda _: str(tmp_path / "cache"))
    statements = []
    original = Query.first

    def record(query):
        statements.append(str(query.statement.compile(dialect=postgresql.dialect())))
        return original(query)

    monkeypatch.setattr(Query, "first", record)
    assert api.get_panorama(photo.id, db, owner).code == 0
    assert api.panorama_image(photo.id, False, db, owner).media_type == "image/jpeg"
    assert len(statements) >= 2
    assert all("FOR UPDATE" not in sql.upper() for sql in statements)


def test_existing_metadata_processing_refreshes_panorama(face_sqlite_session, tmp_path):
    from app.service.tasks.metadata import extract_task_metadata, update_photo_metadata_from_extract
    db = face_sqlite_session
    owner, photo = fixture_photo(db, tmp_path)
    # A legacy ordinary override must not prevent explicit metadata reprocessing.
    photo.panorama_override = "ordinary"
    db.commit()
    extracted = extract_task_metadata({"file_path": photo.file_path}, photo)
    assert extracted["success"] is True
    update_photo_metadata_from_extract(db, photo, extracted["meta"], commit=False)
    db.commit(); db.refresh(photo)
    assert photo.panorama_projection == "equirectangular"
    assert photo.panorama_override is None
    assert photo.processed_tasks["metadata"] is True
