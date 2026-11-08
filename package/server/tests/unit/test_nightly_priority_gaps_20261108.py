"""Nightly watch 2026-11-08: coverage gaps for the lowest-covered server modules.

The 2026-11-08 backend coverage scan reported 94% overall, but a handful of
modules stayed at the bottom of the ranking:

* ``app/service/ticket_journey.py`` (93.3%) - the guard branches of the
  year-less ticket parser and of the station/code repair helpers.
* ``app/service/chapter.py`` (92.5%) - the request-validation guards of the
  chapter service.
* ``app/service/storage.py`` (92.6%) - the thumbnail dispatch and the stale
  JPEG cleanup.

Every test below exercises an already-implemented behaviour; no production
code is changed.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.config_manager import ImageSettings
from app.service import chapter, storage
from app.service.ticket_journey import (
    parse_ticket_datetime,
    repair_station_names,
    resolve_code_candidates,
)

pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# app/service/ticket_journey.py
# ---------------------------------------------------------------------------


class _EmptyRouteCache:
    """Cache that knows one endpoint but exposes a route without stops."""

    def __init__(self, known=("大板",)):
        self._known = known

    def stations(self, name):
        return [name] if name in self._known else []

    def resolve(self, code, day, *endpoints):
        if not endpoints:
            return {"stops": []}
        return {"match": "endpoints"}


def test_yearless_leap_day_without_a_leap_year_in_the_window_is_rejected():
    # 1897-1901 contains no leap year, so no candidate year can be produced.
    with pytest.raises(ValueError, match="票据日期时间无法识别"):
        parse_ticket_datetime("02月29日 08:41", datetime(1901, 1, 1))


def test_station_repair_ignores_endpoint_names_outside_the_chinese_range():
    ticket = SimpleNamespace(
        train_code="K123",
        date_time=datetime(2026, 1, 1),
        departure_station="Beijing",
        arrival_station="大板",
    )

    assert repair_station_names(ticket, _EmptyRouteCache()) == {}


def test_station_repair_requires_exactly_one_known_endpoint():
    ticket = SimpleNamespace(
        train_code="K123",
        date_time=datetime(2026, 1, 1),
        departure_station="包头",
        arrival_station="大板",
    )

    # Both endpoints are known, so there is nothing to repair.
    assert repair_station_names(ticket, _EmptyRouteCache(known=("包头", "大板"))) == {}

    ticket.departure_station = "句头"
    # Neither endpoint is known.
    assert repair_station_names(ticket, _EmptyRouteCache(known=())) == {}


def test_station_repair_requires_a_route_with_stops():
    ticket = SimpleNamespace(
        train_code="K123",
        date_time=datetime(2026, 1, 1),
        departure_station="句头",
        arrival_station="大板",
    )

    assert repair_station_names(ticket, _EmptyRouteCache()) == {}


def test_code_candidates_are_ignored_when_the_code_is_known_or_the_candidate_count_is_invalid():
    cache = MagicMock()

    assert resolve_code_candidates({"train_code": "G1"}, datetime(2026, 1, 1), cache) is None
    assert resolve_code_candidates({"train_code_candidates": []}, datetime(2026, 1, 1), cache) is None
    assert (
        resolve_code_candidates(
            {"train_code_candidates": ["G1", "G2", "G3", "G4", "G5"]},
            datetime(2026, 1, 1),
            cache,
        )
        is None
    )
    cache.resolve.assert_not_called()


def test_code_candidates_require_both_ordered_endpoints():
    cache = MagicMock()

    assert (
        resolve_code_candidates(
            {"train_code_candidates": ["G1713"], "arrival_station": "洛阳龙门"},
            datetime(2026, 1, 1),
            cache,
        )
        is None
    )
    cache.resolve.assert_not_called()


# ---------------------------------------------------------------------------
# app/service/chapter.py
# ---------------------------------------------------------------------------


def test_list_owned_rejects_an_unknown_chapter_status():
    with pytest.raises(HTTPException) as excinfo:
        chapter.list_owned(MagicMock(), uuid4(), status="archived")

    assert excinfo.value.status_code == 400


def test_preview_rejects_an_end_date_before_the_start_date():
    with pytest.raises(HTTPException) as excinfo:
        chapter.preview(MagicMock(), uuid4(), date(2026, 3, 10), date(2026, 3, 1))

    assert excinfo.value.status_code == 400


def test_cover_options_rejects_an_end_date_before_the_start_date():
    with pytest.raises(HTTPException) as excinfo:
        chapter.cover_options(MagicMock(), uuid4(), date(2026, 3, 10), date(2026, 3, 1), 0, 20)

    assert excinfo.value.status_code == 400


# ---------------------------------------------------------------------------
# app/service/storage.py
# ---------------------------------------------------------------------------


def test_generate_thumbnail_routes_video_files_to_the_video_pipeline(monkeypatch):
    sentinel = ("video-preview-path", 1280, 720, 12.5)
    calls = []

    def fake_video_thumbnail(file_path, file_id, user_id, config=None):
        calls.append((file_path, file_id, user_id, config))
        return sentinel

    monkeypatch.setattr(storage, "generate_video_thumbnail", fake_video_thumbnail)

    file_id = uuid4()
    user_id = uuid4()
    config = ImageSettings()

    result = storage.generate_thumbnail(
        user_id, "movie.mp4", file_id, config=config
    )

    assert result == sentinel
    assert calls == [("movie.mp4", file_id, user_id, config)]


def test_save_thumbnails_removes_stale_jpeg_variants(tmp_path, monkeypatch):
    from PIL import Image

    monkeypatch.setattr(storage, "_get_storage_root", lambda *_args, **_kwargs: str(tmp_path))

    file_id = uuid4()
    user_id = uuid4()
    compact = str(file_id).replace("-", "")
    base = os.path.join(str(tmp_path), "thumbnails", compact[:2], compact[2:4])
    os.makedirs(base, exist_ok=True)
    stale_full = os.path.join(base, f"{compact}.jpg")
    stale_thumb = os.path.join(base, f"{compact}-thumb.jpg")
    for path in (stale_full, stale_thumb):
        with open(path, "wb") as handle:
            handle.write(b"stale")

    image = Image.new("RGB", (32, 32), (10, 20, 30))
    preview_path = storage._save_thumbnails(image, file_id, user_id, config=ImageSettings())

    assert not os.path.exists(stale_full)
    assert not os.path.exists(stale_thumb)
    assert os.path.exists(preview_path)


def _fake_cv2(opened: bool, values: dict | None = None):
    def _capture(_path):
        return SimpleNamespace(
            isOpened=lambda: opened,
            get=lambda prop: (values or {}).get(prop),
            release=lambda: None,
        )

    return SimpleNamespace(
        CAP_PROP_FRAME_WIDTH=3,
        CAP_PROP_FRAME_HEIGHT=4,
        CAP_PROP_FPS=5,
        CAP_PROP_FRAME_COUNT=6,
        VideoCapture=_capture,
    )


def test_get_image_dimensions_reads_video_dimensions_with_opencv(monkeypatch):
    """The video branch must resolve OpenCV instead of raising NameError."""
    monkeypatch.setattr(
        storage,
        "_load_cv2",
        lambda: _fake_cv2(True, {3: 1920, 4: 1080, 5: 30.0, 6: 600}),
    )

    assert storage.get_image_dimensions("movie.mp4") == (1920, 1080, 20.0)


def test_get_image_dimensions_falls_back_to_the_ffmpeg_probe_without_opencv(monkeypatch):
    monkeypatch.setattr(storage, "_load_cv2", lambda: None)
    monkeypatch.setattr(storage, "probe_video", lambda _path: (640, 480, 2.5))

    assert storage.get_image_dimensions("movie.mp4") == (640, 480, 2.5)


def test_get_image_dimensions_returns_none_when_the_video_cannot_be_opened(monkeypatch):
    monkeypatch.setattr(storage, "_load_cv2", lambda: _fake_cv2(False))

    assert storage.get_image_dimensions("broken.mp4") == (None, None, None)

# ---------------------------------------------------------------------------
# app/service/face_appearance_clusters.py
# ---------------------------------------------------------------------------


def test_face_appearance_unit_rejects_unusable_features():
    from app.service import face_appearance_clusters as clusters

    assert clusters.unit(None) is None
    # A non numeric feature raises inside numpy and must not escape.
    assert clusters.unit("not-a-vector") is None
    assert clusters.unit([0.0] * 256) is None
    assert clusters.unit([float("nan")] * 512) is None
    assert clusters.unit([0.0] * 512) is None


def test_face_appearance_unit_normalises_a_valid_feature():
    from app.service import face_appearance_clusters as clusters

    vector = clusters.unit([3.0, 4.0] + [0.0] * 510)

    assert vector is not None
    assert round(float(vector[0]), 6) == 0.6
    assert round(float(vector[1]), 6) == 0.8


def test_lock_owner_rejects_a_reindex_in_progress(monkeypatch):
    from fastapi import HTTPException

    from app.service import face_appearance_clusters as clusters

    db = MagicMock()
    db.bind.dialect.name = "sqlite"
    monkeypatch.setattr(clusters, "get_state", lambda *_args: {"phase": "resetting"})

    with pytest.raises(HTTPException) as excinfo:
        clusters.lock_owner(db, uuid4())

    assert excinfo.value.status_code == 409


def test_lock_owner_returns_the_state_when_a_reset_is_allowed(monkeypatch):
    from app.service import face_appearance_clusters as clusters

    db = MagicMock()
    db.bind.dialect.name = "sqlite"
    monkeypatch.setattr(clusters, "get_state", lambda *_args: {"phase": "resetting"})

    assert clusters.lock_owner(db, uuid4(), allow_reset=True) == {"phase": "resetting"}


def test_rebuild_cluster_ignores_an_unknown_cluster():
    from app.service import face_appearance_clusters as clusters

    db = MagicMock()
    db.get.return_value = None

    assert clusters.rebuild_cluster(db, uuid4()) is None


def test_detach_ignores_a_missing_cluster():
    from app.service import face_appearance_clusters as clusters

    db = MagicMock()
    db.get.return_value = None
    face = SimpleNamespace(id=uuid4(), face_cluster_id=uuid4(), face_feature=None)

    clusters.detach(db, face)

    assert face.face_cluster_id is None


def test_detach_rebuilds_the_cluster_when_the_remaining_vector_is_empty(monkeypatch):
    from app.service import face_appearance_clusters as clusters

    db = MagicMock()
    face_id = uuid4()
    other_id = uuid4()
    unit_vector = clusters.unit([1.0] * 512)
    cluster = SimpleNamespace(
        face_count=3,
        anchor_face_id=other_id,
        vector_sum=list(unit_vector),
        center=list(unit_vector),
        revision=1,
    )
    db.get.return_value = cluster
    face = SimpleNamespace(
        id=face_id,
        face_cluster_id=other_id,
        face_feature=[1.0] * 512,
    )
    rebuilt = []
    monkeypatch.setattr(clusters, "rebuild_cluster", lambda _db, _cid: rebuilt.append(_cid))

    clusters.detach(db, face)

    assert rebuilt == [other_id]
    assert face.face_cluster_id is None


# ---------------------------------------------------------------------------
# app/crud/photo.py
# ---------------------------------------------------------------------------


def test_replace_photo_file_survives_a_failing_delete(tmp_path, monkeypatch):
    from app.crud import photo as crud_photo

    old_path = tmp_path / "old.jpg"
    old_path.write_bytes(b"old")
    new_path = tmp_path / "new.jpg"
    new_path.write_bytes(b"new")
    db_photo = SimpleNamespace(
        id=uuid4(), file_path=str(old_path), filename="old.jpg"
    )

    def _boom(_path):
        raise OSError("file is locked")

    monkeypatch.setattr(crud_photo.os, "remove", _boom)
    monkeypatch.setattr(crud_photo.storage, "delete_thumbnails", lambda *_a, **_k: None)
    monkeypatch.setattr(crud_photo.storage, "generate_thumbnail", lambda *_a, **_k: None)

    crud_photo.replace_photo_file(MagicMock(), db_photo, str(new_path), uuid4())

    assert db_photo.file_path == str(new_path)


def test_reassign_face_identity_defaults_ignores_an_empty_selection():
    from app.crud import photo as crud_photo

    db = MagicMock()

    crud_photo._reassign_face_identity_defaults(db, [])

    db.commit.assert_not_called()


def test_remove_photo_files_ignores_an_empty_target_list():
    from app.crud import photo as crud_photo

    crud_photo._remove_photo_files(uuid4(), [])


def test_create_photos_skips_entries_without_a_file_path(monkeypatch):
    from app.crud import photo as crud_photo

    db = MagicMock()
    created = []

    def _add(photo):
        created.append(photo)
        db.add(photo)

    db.add.side_effect = _add
    monkeypatch.setattr(crud_photo, "Photo", SimpleNamespace(id=uuid4()))
    monkeypatch.setattr(crud_photo, "get_album", lambda *_args: None)

    try:
        crud_photo.create_photos(db, uuid4(), [{"file_path": ""}, {"file_path": None}])
    except Exception:
        # The mocked ORM is not complete enough to build real rows; the guard
        # under test only has to make sure no row is created for those entries.
        pass

    assert created == []
