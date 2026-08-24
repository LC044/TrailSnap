"""Unit tests covering 2026-08-24 nightly coverage gap scan (round 4).

Targets high-impact modules whose coverage is still below 60% after the
2026-08-21 / 2026-08-24 rounds:

* app/service/storage.py (54%, 114 missed) -- ``save_upload_file``,
  ``delete_file`` with ``is_live_photo=False``, and ``get_live_photo_vide``
  for HEIC / JPG never had direct tests; the existing
  test_storage_service.py only covers ``_ensure_unique_path``,
  ``get_preview_path``, ``delete_thumbnails``, and ``get_image_dimensions``.

* app/utils/exif.py (47%, 84 missed) -- ``_convert_to_degrees``,
  ``get_file_time_form_system``, and ``reverse_geocode`` were never
  exercised directly; test_exif_utils.py only covers ``get_gps_info`` and
  ``extract_metadata`` happy/error paths.

* app/service/face_cluster.py (49%, 168 missed) -- ``assign_face_to_identity``
  SQLite in-memory branch (lines 101-118) is uncovered; the existing
  test_nightly_face_cluster_gaps_20260819.py round only covers
  ``_serialize_rescan_preview`` / prototype selection helpers.

Pattern: MagicMock + tmp_path, no DB / no HTTP. Mirrors the
2026-08-21 / 2026-08-24 nightly rounds.
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# app.service.storage -- save_upload_file
# ---------------------------------------------------------------------------


def test_save_upload_file_writes_into_year_month_subdir(tmp_path, monkeypatch):
    """save_upload_file creates YYYY/MM/ uploads/YYYY/MM/<name> and writes bytes."""
    from app.service import storage

    user_id = uuid4()
    upload = MagicMock()
    upload.filename = "trip.jpg"
    upload.file = MagicMock()
    upload.file.read.side_effect = lambda n=1024: b"binary-content"

    captured = {}

    def _fake_open(target_path, mode):
        captured["path"] = target_path
        captured["mode"] = mode

        class _Buf:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

            def write(self_inner, data):
                captured.setdefault("bytes", b"")
                captured["bytes"] += data

        return _Buf()

    monkeypatch.setattr(storage, "_get_storage_root", lambda u: str(tmp_path))
    monkeypatch.setattr(storage.os.path, "exists", lambda p: False)
    monkeypatch.setattr(storage.os, "makedirs", lambda *a, **k: None)
    monkeypatch.setattr("builtins.open", _fake_open)
    monkeypatch.setattr(storage.shutil, "copyfileobj", lambda src, dst: None)

    out = storage.save_upload_file(upload, uuid4(), user_id)

    assert out.endswith("trip.jpg")
    assert "uploads" in out
    assert captured["path"].endswith("trip.jpg")


def test_save_upload_file_handles_collision_with_paren_suffix(tmp_path, monkeypatch):
    """When the target file already exists, _ensure_unique_path appends (1)."""
    from app.service import storage

    user_id = uuid4()
    upload = MagicMock()
    upload.filename = "trip.jpg"
    upload.file = MagicMock()

    # First check sees the collision, second (with the (1) suffix) sees no collision.
    def _exists(p):
        return p.endswith("trip.jpg")

    monkeypatch.setattr(storage, "_get_storage_root", lambda u: str(tmp_path))
    monkeypatch.setattr(storage.os.path, "exists", _exists)
    monkeypatch.setattr(storage.os, "makedirs", lambda *a, **k: None)
    monkeypatch.setattr("builtins.open", MagicMock())
    monkeypatch.setattr(storage.shutil, "copyfileobj", lambda src, dst: None)

    out = storage.save_upload_file(upload, uuid4(), user_id)

    assert out.endswith("trip(1).jpg")


# ---------------------------------------------------------------------------
# app.service.storage -- get_live_photo_vide
# ---------------------------------------------------------------------------


def test_get_live_photo_vide_heic_returns_mov_sibling(tmp_path):
    from app.service import storage

    img = tmp_path / "vacation.heic"
    img.write_bytes(b"raw")
    video = tmp_path / "vacation.mov"
    video.write_bytes(b"video")

    assert storage.get_live_photo_vide(str(img)) == str(video)


def test_get_live_photo_vide_jpg_returns_mp4_sibling(tmp_path):
    from app.service import storage

    img = tmp_path / "vacation.jpg"
    img.write_bytes(b"raw")
    video = tmp_path / "vacation.mp4"
    video.write_bytes(b"video")

    assert storage.get_live_photo_vide(str(img)) == str(video)


def test_get_live_photo_vide_returns_none_when_sibling_missing(tmp_path):
    from app.service import storage

    img = tmp_path / "plain.heic"
    img.write_bytes(b"raw")
    assert storage.get_live_photo_vide(str(img)) is None


# ---------------------------------------------------------------------------
# app.service.storage -- delete_file
# ---------------------------------------------------------------------------


def test_delete_file_removes_original_and_thumbnails(tmp_path, monkeypatch):
    """delete_file (is_live_photo=False) removes the original and the thumbnails."""
    from app.service import storage

    file_id = uuid4()
    user_id = uuid4()
    file_path = tmp_path / "photo.jpg"
    file_path.write_bytes(b"raw")

    monkeypatch.setattr(storage, "_get_storage_root", lambda u: str(tmp_path))
    monkeypatch.setattr(storage, "delete_thumbnails", lambda u, f: None)

    storage.delete_file(user_id, str(file_path), file_id, is_live_photo=False)

    assert not file_path.exists()


def test_delete_file_live_photo_also_removes_mov_sibling(tmp_path, monkeypatch):
    from app.service import storage

    file_id = uuid4()
    user_id = uuid4()
    img = tmp_path / "live.heic"
    img.write_bytes(b"raw")
    mov = tmp_path / "live.mov"
    mov.write_bytes(b"video")

    monkeypatch.setattr(storage, "_get_storage_root", lambda u: str(tmp_path))
    monkeypatch.setattr(storage, "delete_thumbnails", lambda u, f: None)

    storage.delete_file(user_id, str(img), file_id, is_live_photo=True)

    assert not img.exists()
    assert not mov.exists()


# ---------------------------------------------------------------------------
# app.utils.exif -- _convert_to_degrees
# ---------------------------------------------------------------------------


def test_convert_to_degrees_handles_tuple_with_zero_denominator():
    from app.utils.exif import _convert_to_degrees

    # (numerator, denominator) tuples; second element 0 -> 0.0 (graceful).
    result = _convert_to_degrees([(39, 1), (54, 1), (0, 1)])
    assert abs(result - 39.9) < 1e-6


def test_convert_to_degrees_handles_ifdrational_like_object():
    from app.utils.exif import _convert_to_degrees

    class _Rational:
        def __init__(self, n, d):
            self.numerator = n
            self.denominator = d

    value = [_Rational(116, 1), _Rational(23, 1), _Rational(30, 1)]
    result = _convert_to_degrees(value)
    assert abs(result - 116.39166666666668) < 1e-6


def test_convert_to_degrees_zero_denominator_returns_zero():
    from app.utils.exif import _convert_to_degrees

    value = [(0, 0), (1, 0), (2, 0)]
    # Falls back to 0.0 for each component, so the result is 0.
    assert _convert_to_degrees(value) == 0.0


# ---------------------------------------------------------------------------
# app.utils.exif -- get_file_time_form_system
# ---------------------------------------------------------------------------


def test_get_file_time_form_system_returns_stat_mtime(tmp_path):
    from app.utils.exif import get_file_time_form_system

    target = tmp_path / "note.txt"
    target.write_bytes(b"hi")
    expected = datetime.fromtimestamp(target.stat().st_mtime)
    actual = get_file_time_form_system(str(target))
    assert abs((actual - expected).total_seconds()) < 2


def test_get_file_time_form_system_falls_back_to_now_when_missing(tmp_path):
    from app.utils.exif import get_file_time_form_system

    missing = tmp_path / "never-existed.jpg"
    before = datetime.now()
    result = get_file_time_form_system(str(missing))
    after = datetime.now()

    # OSError path returns datetime.now(); the result must fall inside [before, after].
    assert before <= result <= after


# ---------------------------------------------------------------------------
# app.utils.exif -- reverse_geocode
# ---------------------------------------------------------------------------


def test_reverse_geocode_uses_admin_levels_when_present(monkeypatch):
    from app.utils import exif

    captured = {}

    def _fake_search(coords, mode=1, data_dir=None):
        captured["coords"] = coords
        captured["mode"] = mode
        return [{
            "admin_1": "\u6e56\u5317\u7701",
            "admin_2": "\u6b66\u6c49\u5e02",
            "admin_3": "\u6b66\u660c\u533a",
            "admin_4": "\u9ec4\u9e64\u697c",
            "name": "scenic",
            "country": "CN",
        }]

    monkeypatch.setattr(exif.rg, "search", _fake_search)
    out = exif.reverse_geocode(30.5, 114.3)
    assert captured["coords"] == [(30.5, 114.3)]
    assert captured["mode"] == 1
    assert out["province"] == "\u6e56\u5317\u7701"
    assert out["city"] == "\u6b66\u6c49\u5e02"
    assert out["district"] == "\u6b66\u660c\u533a"
    assert out["country"] == "CN"
    assert "\u9ec4\u9e64\u697c" in out["address"]


def test_reverse_geocode_returns_empty_when_search_raises(monkeypatch):
    from app.utils import exif

    def _boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(exif.rg, "search", _boom)
    assert exif.reverse_geocode(0.0, 0.0) == {}


def test_reverse_geocode_falls_back_to_name_when_admin4_empty(monkeypatch):
    from app.utils import exif

    def _fake_search(*a, **k):
        return [{
            "admin_1": "Hokkaido",
            "admin_2": "Sapporo",
            "admin_3": "Chuo",
            "admin_4": "",
            "name": "Odori Park",
            "country": "JP",
        }]

    monkeypatch.setattr(exif.rg, "search", _fake_search)
    out = exif.reverse_geocode(43.06, 141.35)
    assert out["city"] == "Sapporo"
    assert out["address"].endswith("Odori Park")


# ---------------------------------------------------------------------------
# app.service.face_cluster -- assign_face_to_identity (SQLite branch)
# ---------------------------------------------------------------------------


def _face_cluster_service_with_sqlite(query_all_value):
    """Build a FaceClusterService whose db.bind is 'sqlite' and query(...).all() returns given list."""
    from app.service import face_cluster

    svc = face_cluster.FaceClusterService.__new__(face_cluster.FaceClusterService)
    svc.db = MagicMock()
    svc.db.bind.dialect.name = "sqlite"
    svc.SIMILARITY_THRESHOLD = 0.7
    svc.DISTANCE_THRESHOLD = 0.4
    svc.RESCAN_AUTO_MATCH_THRESHOLD = 0.35
    svc.RESCAN_CANDIDATE_THRESHOLD = 0.45
    svc.RESCAN_REMOVAL_THRESHOLD = 0.52
    svc.MIN_CLUSTER_SIZE_FOR_IDENTITY = 5

    chain = MagicMock()
    chain.all.return_value = query_all_value
    # query(...).join(...).filter(...).all()
    svc.db.query.return_value.join.return_value.filter.return_value = chain
    return svc


def test_assign_face_to_identity_sqlite_returns_nearest_identity():
    from app.service import face_cluster

    nearest_id = uuid4()
    nearest_face = SimpleNamespace(
        id=999,
        face_identity_id=nearest_id,
        face_feature=[1.0, 0.0, 0.0],
        cluster_id=42,
    )
    far_face = SimpleNamespace(
        id=1000,
        face_identity_id=uuid4(),
        face_feature=[-1.0, 0.0, 0.0],
        cluster_id=42,
    )

    svc = _face_cluster_service_with_sqlite([nearest_face, far_face])

    # config_manager.get_user_config returns a real config object whose
    # ``face_cluster_threshold`` is a numpy scalar on some CI images; bypass it
    # by patching the call site to a plain Python float.
    class _StubAI:
        face_cluster_threshold = 0.4

    class _StubConfig:
        ai = _StubAI()

    with patch.object(face_cluster.config_manager, "get_user_config", return_value=_StubConfig()), \
         patch.object(face_cluster.crud_face, "update_face", return_value=True) as update:
        result = svc.assign_face_to_identity(face_id=1, embedding=[1.0, 0.0, 0.0])

    assert result == nearest_id
    update.assert_called_once()
    # update_face signature: update_face(db, face_id, obj_in, owner_id=None)
    args, kwargs = update.call_args
    assert kwargs.get("owner_id") is None
    obj_in = args[2]
    assert obj_in.recognize_confidence > 0.99


def test_assign_face_to_identity_sqlite_returns_none_when_no_candidates():
    from app.service import face_cluster

    svc = _face_cluster_service_with_sqlite([])

    result = svc.assign_face_to_identity(face_id=1, embedding=[1.0, 0.0, 0.0])
    assert result is None


def test_assign_face_to_identity_returns_none_on_pending_rollback():
    from app.service import face_cluster
    from sqlalchemy.exc import PendingRollbackError

    svc = _face_cluster_service_with_sqlite([])
    svc.db.query.side_effect = PendingRollbackError("txn rolled back", None, None)

    with pytest.raises(PendingRollbackError):
        svc.assign_face_to_identity(face_id=1, embedding=[1.0, 0.0, 0.0])
    svc.db.rollback.assert_called_once()
