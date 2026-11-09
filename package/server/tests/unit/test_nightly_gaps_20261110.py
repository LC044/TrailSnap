"""Nightly watch 2026-11-10: server coverage gaps.

Targets the lines the 2026-11-10 backend coverage snapshot (94% total) still
reports as uncovered:

* ``app/utils/color.py`` - the muted / warm / cool tone buckets and the
  "no metrics" bail-out of ``classify_saved_palette``,
* ``app/service/user_storage.py`` - the cross-drive guard of ``_is_below``
  and every branch of ``_move_file`` (same path, missing source, identical
  size, preserved conflict, discarded conflict) plus the live-photo
  companion move and the ``delete_user_layout`` retry exhaustion,
* ``app/api/photo.py`` - the async purge rate-limit, the folder tree
  bucketing, the transfer error paths and the demo-mode random padding,
* ``app/service/jobs/proactive_memory.py`` - the LLM fallback, the anchor
  failure and the per-run time budget.

Every test exercises already-implemented behaviour; no production code changes.
"""

from __future__ import annotations

import os
import shutil
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

pytestmark = [pytest.mark.smoke]


# --------------------------------------------------------------------------
# app/utils/color.py
# --------------------------------------------------------------------------
def test_classify_tones_labels_a_dark_and_desaturated_palette_as_muted():
    from app.utils.color import _classify_tones

    assert _classify_tones(brightness=0.2, saturation=0.1, warm_ratio=0.0, cool_ratio=0.0) == "muted"


def test_classify_tones_prefers_warm_over_cool():
    from app.utils.color import _classify_tones

    assert _classify_tones(brightness=0.5, saturation=0.3, warm_ratio=0.4, cool_ratio=0.0) == "warm"


def test_classify_tones_reports_a_cool_palette():
    from app.utils.color import _classify_tones

    assert _classify_tones(brightness=0.5, saturation=0.3, warm_ratio=0.0, cool_ratio=0.4) == "cool"


def test_classify_saved_palette_returns_none_without_usable_metrics():
    from app.utils.color import classify_saved_palette

    assert classify_saved_palette([]) is None
    assert classify_saved_palette([{"hex": "not-a-color", "ratio": 1}]) is None


def test_classify_saved_palette_rejects_a_stale_saved_metric():
    from app.utils.color import classify_saved_palette

    colors = [{"hex": "#3366cc", "ratio": 1.0}]
    # The saved brightness does not match the recomputed metric.
    assert classify_saved_palette(colors, saved_brightness=0.99, saved_saturation=0.99) is None


# --------------------------------------------------------------------------
# app/service/user_storage.py
# --------------------------------------------------------------------------
def test_is_below_returns_false_for_paths_on_different_drives():
    from app.service.user_storage import _is_below

    assert _is_below(r"C:\photos\a", r"D:\photos") is False


def test_is_below_returns_true_for_a_nested_path():
    from app.service.user_storage import _is_below

    assert _is_below(r"C:\photos\a\b", r"C:\photos") is True


def test_move_file_returns_none_when_source_and_target_are_the_same_missing_path(tmp_path):
    from app.service.user_storage import _move_file

    missing = str(tmp_path / "missing.jpg")
    assert _move_file(missing, missing) is None


def test_move_file_removes_the_source_when_both_files_have_the_same_size(tmp_path):
    from app.service.user_storage import _move_file

    source = tmp_path / "a.jpg"
    target = tmp_path / "b.jpg"
    source.write_bytes(b"12345")
    target.write_bytes(b"abcde")

    assert _move_file(str(source), str(target)) == str(target)
    assert not source.exists()
    assert target.read_bytes() == b"abcde"


def test_move_file_keeps_a_conflicting_file_as_a_migrated_copy(tmp_path):
    from app.service.user_storage import _move_file

    source = tmp_path / "a.jpg"
    target = tmp_path / "b.jpg"
    source.write_bytes(b"1234567890")
    target.write_bytes(b"abcde")

    result = _move_file(str(source), str(target), preserve_conflict=True)

    assert result == str(tmp_path / "b-migrated-1.jpg")
    assert (tmp_path / "b-migrated-1.jpg").read_bytes() == b"1234567890"
    # The source is moved (not copied) outside the desktop-verify mode.
    assert not source.exists()


def test_move_file_numbers_a_second_migrated_copy(tmp_path):
    from app.service.user_storage import _move_file

    source = tmp_path / "a.jpg"
    target = tmp_path / "b.jpg"
    source.write_bytes(b"1234567890")
    target.write_bytes(b"abcde")
    (tmp_path / "b-migrated-1.jpg").write_bytes(b"xxxxx")

    result = _move_file(str(source), str(target), preserve_conflict=True)

    assert result == str(tmp_path / "b-migrated-2.jpg")


def test_move_file_discards_an_obsolete_thumbnail_when_the_target_exists(tmp_path):
    from app.service.user_storage import _move_file

    source = tmp_path / "a.jpg"
    target = tmp_path / "b.jpg"
    source.write_bytes(b"12345")
    target.write_bytes(b"abcde")

    assert _move_file(str(source), str(target)) == str(target)
    assert not source.exists()


def test_move_live_photo_companions_moves_the_video_next_to_the_photo(tmp_path):
    from app.service.user_storage import _move_live_photo_companions

    source = tmp_path / "a.heic"
    target = tmp_path / "b.heic"
    source.write_bytes(b"photo")
    (tmp_path / "a.mov").write_bytes(b"movie")

    _move_live_photo_companions(str(source), str(target))

    assert (tmp_path / "b.mov").exists()
    assert not (tmp_path / "a.mov").exists()


def test_delete_user_layout_gives_up_when_the_directory_stays_locked(tmp_path, monkeypatch):
    from app.service import user_storage

    root = tmp_path / "users" / "u1"
    root.mkdir(parents=True)
    monkeypatch.setattr(user_storage, "_DELETE_RETRY_DELAYS", ())
    monkeypatch.setattr(user_storage.shutil, "rmtree", lambda *a, **k: (_ for _ in ()).throw(PermissionError("locked")))

    with pytest.raises(PermissionError):
        user_storage.delete_user_layout("u1", {"storage": {"photo_storage_path": str(tmp_path)}})


# --------------------------------------------------------------------------
# app/api/photo.py
# --------------------------------------------------------------------------
def _user():
    return SimpleNamespace(id=uuid4())


def test_purge_recycle_bin_reports_a_busy_worker_as_429():
    from app.api import photo as photo_api
    from app.schemas.photo import RecycleBinPurge

    ids = [uuid4() for _ in range(5)]
    with patch("app.crud.photo.get_recycle_bin_photo_ids", return_value=ids), \
         patch("app.service.recycle_bin_purge.ASYNC_PURGE_THRESHOLD", 2), \
         patch("app.service.recycle_bin_purge.active_job_for_user", return_value=None), \
         patch("app.service.recycle_bin_purge.start_purge_job", side_effect=RuntimeError("busy")):
        with pytest.raises(HTTPException) as excinfo:
            photo_api.purge_recycle_bin(
                RecycleBinPurge(photo_ids=ids), db=MagicMock(), current_user=_user()
            )

    assert excinfo.value.status_code == 429


def test_batch_transfer_rejects_a_target_outside_the_allowed_roots(tmp_path):
    from app.api import photo as photo_api
    from app.schemas.photo import BatchPhotoTransfer

    with patch.object(photo_api.config_manager, "get_user_config", return_value=SimpleNamespace(
            storage=SimpleNamespace(external_directories=[]))), \
         patch.object(photo_api.storage, "_get_storage_root", return_value=str(tmp_path / "uploads")):
        with pytest.raises(HTTPException) as excinfo:
            photo_api.batch_transfer_photos(
                BatchPhotoTransfer(photo_ids=[uuid4()], target_path=str(tmp_path / "elsewhere"), action="copy"),
                db=MagicMock(), current_user=_user(),
            )

    assert excinfo.value.status_code == 403


def test_batch_transfer_reports_a_directory_creation_failure(tmp_path):
    from app.api import photo as photo_api
    from app.schemas.photo import BatchPhotoTransfer

    target = tmp_path / "target"
    with patch.object(photo_api.config_manager, "get_user_config", return_value=SimpleNamespace(
            storage=SimpleNamespace(external_directories=[str(target)]))), \
         patch.object(photo_api.storage, "_get_storage_root", return_value=str(tmp_path / "uploads")), \
         patch.object(photo_api.os, "makedirs", side_effect=OSError("read only")):
        with pytest.raises(HTTPException) as excinfo:
            photo_api.batch_transfer_photos(
                BatchPhotoTransfer(photo_ids=[uuid4()], target_path=str(target), action="copy"),
                db=MagicMock(), current_user=_user(),
            )

    assert excinfo.value.status_code == 500


def test_batch_transfer_skips_a_photo_whose_copy_fails(tmp_path):
    from app.api import photo as photo_api
    from app.schemas.photo import BatchPhotoTransfer

    target = tmp_path / "target"
    target.mkdir()
    source = tmp_path / "a.jpg"
    source.write_bytes(b"data")
    photo = SimpleNamespace(id=uuid4(), file_path=str(source), filename="a.jpg")
    db = MagicMock()

    with patch.object(photo_api.config_manager, "get_user_config", return_value=SimpleNamespace(
            storage=SimpleNamespace(external_directories=[str(target)]))), \
         patch.object(photo_api.storage, "_get_storage_root", return_value=str(tmp_path / "uploads")), \
         patch("app.crud.photo.get_photos_by_ids", return_value=[photo]), \
         patch.object(photo_api.shutil, "copy2", side_effect=OSError("busy")):
        response = photo_api.batch_transfer_photos(
            BatchPhotoTransfer(photo_ids=[photo.id], target_path=str(target), action="copy"),
            db=db, current_user=_user(),
        )

    assert response.data["message"] == "Successfully copyed 0 photos"


@pytest.mark.asyncio
async def test_replace_photo_file_maps_a_value_error_to_400():
    from app.api import photo as photo_api

    photo = SimpleNamespace(id=uuid4(), owner_id=uuid4(), file_type=None)
    with patch("app.crud.photo.get_photo", return_value=photo), \
         patch.object(photo_api.storage, "save_upload_file", side_effect=ValueError("bad file")):
        with pytest.raises(HTTPException) as excinfo:
            await photo_api.replace_photo_file(
                photo.id, file=MagicMock(), db=MagicMock(), current_user=SimpleNamespace(id=photo.owner_id)
            )

    assert excinfo.value.status_code == 400


def test_read_photo_folders_buckets_photos_into_own_and_child_counts(tmp_path):
    from app.api import photo as photo_api

    root = tmp_path / "library"
    (root / "child").mkdir(parents=True)
    norm_root = str(root).replace("\\", "/")

    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [
        (norm_root,),
        (norm_root + "/child/a.jpg",),
        (norm_root + "/child/b.jpg",),
        ("",),
        ("/elsewhere/x.jpg",),
    ]

    with patch("app.utils.path.get_user_roots", return_value=[str(root)]):
        response = photo_api.read_photo_folders(parent="library", db=db, current_user=_user())

    assert response.data["own_count"] == 1
    names = [child["name"] for child in response.data["children"]]
    assert names == ["child"]
    assert response.data["children"][0]["count"] == 2


def test_read_photo_folders_survives_an_unreadable_directory(tmp_path):
    from app.api import photo as photo_api

    root = tmp_path / "library"
    root.mkdir()
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []

    with patch("app.utils.path.get_user_roots", return_value=[str(root)]), \
         patch("app.api.photo.os.listdir", side_effect=PermissionError("denied")):
        response = photo_api.read_photo_folders(parent="", db=db, current_user=_user())

    assert response.data["children"][0]["has_children"] is False


def test_on_this_day_pads_with_random_photos_in_demo_mode():
    from app.api import photo as photo_api

    existing = SimpleNamespace(id=uuid4())
    extra = [SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())]
    db = MagicMock()

    with patch("app.crud.photo.get_on_this_day_photos", return_value=[existing]), \
         patch("app.crud.photo.get_random_photos", return_value=extra), \
         patch("app.middleware.demo_mode.DEMO_MODE", True):
        photos = photo_api.get_on_this_day_photos(
            month=1, day=1, year=2020, limit=3, db=db, current_user=_user()
        )

    assert len(photos) == 3


# --------------------------------------------------------------------------
# app/service/jobs/proactive_memory.py
# --------------------------------------------------------------------------
def _ai_config(enable=True, api_key="k"):
    connection = SimpleNamespace(id="c1", enable=enable, api_key=api_key, api_base=None)
    return SimpleNamespace(
        chat_connection_id="c1",
        analysis_connection_id=None,
        chat_model_name="gpt-test",
        analysis_model_name=None,
        connections=[connection],
    )


def test_llm_greeting_returns_none_when_the_model_call_fails(monkeypatch):
    from app.service.jobs import proactive_memory

    monkeypatch.setattr(
        proactive_memory.config_manager, "get_user_config",
        lambda *a, **k: SimpleNamespace(ai=_ai_config()),
    )

    class Boom:
        def invoke(self, *args, **kwargs):
            raise RuntimeError("model down")

    monkeypatch.setitem(sys.modules, "langchain_openai", types.SimpleNamespace(ChatOpenAI=lambda **k: Boom()))

    assert proactive_memory._llm_greeting(MagicMock(), uuid4(), 3, ["narrative"]) is None


def test_llm_greeting_returns_none_when_the_connection_is_disabled(monkeypatch):
    from app.service.jobs import proactive_memory

    monkeypatch.setattr(
        proactive_memory.config_manager, "get_user_config",
        lambda *a, **k: SimpleNamespace(ai=_ai_config(enable=False)),
    )

    assert proactive_memory._llm_greeting(MagicMock(), uuid4(), 3, []) is None


def test_generate_for_user_survives_a_failing_memory_anchor(monkeypatch):
    from app.service.jobs import proactive_memory

    photo = SimpleNamespace(
        id=uuid4(),
        photo_time=None,
        image_description=None,
        metadata_info=None,
    )
    cfg = SimpleNamespace(top_photos=5)
    user = SimpleNamespace(id=uuid4(), username="nightly")

    monkeypatch.setattr(proactive_memory.agent_crud, "has_proactive_for_date", lambda *a, **k: False)
    monkeypatch.setattr(proactive_memory, "get_on_this_day_photos", lambda *a, **k: [photo])
    monkeypatch.setattr(proactive_memory, "_has_llm", lambda *a, **k: False)
    monkeypatch.setattr(proactive_memory.agent_crud, "create_proactive_message", lambda *a, **k: None)
    monkeypatch.setitem(
        sys.modules, "app.service.agent.memory",
        types.SimpleNamespace(add_memory_anchor=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("nope"))),
    )

    assert proactive_memory._generate_for_user(MagicMock(), user, MagicMock(), cfg) is True


def test_proactive_memory_job_stops_when_the_time_budget_is_exhausted(monkeypatch):
    from app.service.jobs import proactive_memory

    users = [SimpleNamespace(id=uuid4(), username=f"u{i}") for i in range(3)]
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = users
    monkeypatch.setattr(proactive_memory, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        proactive_memory, "system_config",
        SimpleNamespace(config=SimpleNamespace(
            proactive_memory_schedule=SimpleNamespace(max_run_seconds=0))),
    )
    # Windows' time.time() can return the same value twice in a row, which
    # would make the elapsed budget exactly 0.0 and skip the break.
    class _Clock:
        def __init__(self):
            self.calls = 0

        def time(self):
            self.calls += 1
            return 1000.0 + self.calls

    monkeypatch.setattr(proactive_memory, "time", _Clock())

    processed = []
    monkeypatch.setattr(
        proactive_memory, "_generate_for_user",
        lambda *a, **k: processed.append(a[1].username) or True,
    )

    proactive_memory.proactive_memory_job()

    assert processed == []
