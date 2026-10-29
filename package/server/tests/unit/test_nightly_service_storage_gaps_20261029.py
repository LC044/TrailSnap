"""2026-10-29 nightly gap tests for ``app/service/storage.py``.

These tests cover the storage helpers that were still unreachable: the video
seek-position planner, the blank-frame scorer, the thumbnail/video cleanup
paths and the live-photo sibling lookup. Everything is executed against a
temporary directory or with the filesystem access patched.
"""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.service import storage as storage_module


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


# ----------------------- _video_thumbnail_candidate_seconds -----------------------


def test_candidate_seconds_for_zero_duration():
    """A video without a duration only seeks to the very beginning."""
    assert storage_module._video_thumbnail_candidate_seconds(0) == [0.0]
    assert storage_module._video_thumbnail_candidate_seconds(-5) == [0.0]


def test_candidate_seconds_are_unique_and_bounded():
    """The seek positions are unique, ordered and never exceed the duration."""
    positions = storage_module._video_thumbnail_candidate_seconds(2.0)

    assert positions == sorted(positions)
    assert len(positions) == len(set(positions))
    assert all(0.0 <= p <= 2.0 for p in positions)
    assert positions[0] == 0.0


def test_candidate_seconds_collapse_for_very_short_videos():
    """For a tiny clip every candidate collapses onto the first frame."""
    positions = storage_module._video_thumbnail_candidate_seconds(0.02)

    assert positions == [0.0]


# ----------------------- _score_video_thumbnail_frame -----------------------


def test_score_frame_rejects_missing_frame():
    """A missing frame scores as unusable."""
    assert storage_module._score_video_thumbnail_frame(None) == float("-inf")


def test_score_frame_rejects_empty_frame():
    """An empty frame (size 0) scores as unusable."""
    empty = SimpleNamespace(size=0)

    assert storage_module._score_video_thumbnail_frame(empty) == float("-inf")


def test_score_frame_rejects_black_frame():
    """A nearly black frame is rejected."""
    import numpy as np

    black = np.zeros((4, 4, 3), dtype="uint8")

    assert storage_module._score_video_thumbnail_frame(black) == float("-inf")


def test_score_frame_accepts_contentful_frame():
    """A frame with real contrast gets a positive score."""
    import numpy as np

    frame = np.zeros((4, 4, 3), dtype="uint8")
    frame[:2] = 220
    frame[2:] = 40

    assert storage_module._score_video_thumbnail_frame(frame) > 0


# ----------------------- _get_storage_root -----------------------


def test_get_storage_root_survives_database_error():
    """A failing user lookup falls back to the default storage base."""
    user_id = uuid4()
    db = MagicMock()
    db.query.side_effect = RuntimeError("db down")

    with patch.object(storage_module.user_storage, "get_cached_storage_base", return_value=None):
        with patch.object(storage_module.user_storage, "configured_storage_base", return_value=None):
            with patch.object(storage_module.user_storage, "cache_storage_base", return_value="C:/storage") as cache:
                with patch.object(storage_module.user_storage, "ensure_user_layout", return_value="C:/storage/user"):
                    root = storage_module._get_storage_root(user_id, db)

    cache.assert_called_once_with(user_id, storage_module.user_storage.DEFAULT_STORAGE_BASE)
    assert root == "C:/storage/user"


# ----------------------- delete_thumbnails -----------------------


def test_delete_thumbnails_removes_all_variants(tmp_path):
    """Every generated variant (webp / jpg / mp4 / pano) is deleted."""
    user_id = uuid4()
    file_id = uuid4()
    compact = str(file_id).replace("-", "")
    base = tmp_path / "thumbnails" / compact[:2] / compact[2:4]
    base.mkdir(parents=True)
    for name in (f"{compact}.webp", f"{compact}-thumb.webp", f"{compact}.jpg",
                 f"{compact}-thumb.jpg", f"{compact}.mp4", f"{compact}-pano-1.jpg"):
        (base / name).write_bytes(b"x")

    created = [base / name for name in (
        f"{compact}.webp", f"{compact}-thumb.webp", f"{compact}.jpg",
        f"{compact}-thumb.jpg", f"{compact}.mp4", f"{compact}-pano-1.jpg",
    )]

    with patch.object(storage_module, "_get_storage_root", return_value=str(tmp_path)):
        storage_module.delete_thumbnails(user_id, file_id)

    assert all(not path.exists() for path in created)


def test_delete_thumbnails_is_silent_on_error():
    """A failing cleanup never raises to the caller."""
    with patch.object(storage_module, "_get_storage_root", side_effect=RuntimeError("no root")):
        storage_module.delete_thumbnails(uuid4(), uuid4())


# ----------------------- get_live_photo_vide -----------------------


def test_get_live_photo_vide_finds_mp4_sibling(tmp_path):
    """A JPEG with an .mp4 sibling returns the video path."""
    image = tmp_path / "IMG_0001.jpg"
    image.write_bytes(b"x")
    video = tmp_path / "IMG_0001.mp4"
    video.write_bytes(b"x")

    assert storage_module.get_live_photo_vide(str(image)) is not None


def test_get_live_photo_vide_returns_none_without_sibling(tmp_path):
    """Without a sibling video the helper returns ``None``."""
    image = tmp_path / "IMG_0002.jpg"
    image.write_bytes(b"x")

    assert storage_module.get_live_photo_vide(str(image)) is None


def test_get_live_photo_vide_handles_errors():
    """An unexpected error is logged and reported as ``None``."""
    assert storage_module.get_live_photo_vide(None) is None


# ----------------------- delete_file -----------------------


def test_delete_file_removes_photo_and_thumbnails(tmp_path):
    """Deleting a file also removes the live photo video and thumbnails."""
    user_id = uuid4()
    file_id = uuid4()
    photo = tmp_path / "IMG_0003.jpg"
    photo.write_bytes(b"x")
    video = tmp_path / "IMG_0003.mp4"
    video.write_bytes(b"x")

    with patch.object(storage_module, "delete_thumbnails") as delete_thumbnails:
        storage_module.delete_file(user_id, str(photo), file_id, is_live_photo=True)

    assert not photo.exists()
    assert not video.exists()
    delete_thumbnails.assert_called_once_with(user_id, file_id)


def test_delete_file_swallows_errors():
    """A failing delete is logged instead of raised."""
    with patch.object(storage_module.os.path, "exists", side_effect=RuntimeError("disk")):
        storage_module.delete_file(uuid4(), "whatever.jpg", uuid4())

# ----------------------- _load_cv2 -----------------------


def test_load_cv2_returns_none_when_opencv_missing():
    """A missing OpenCV install degrades to the ffmpeg fallback."""
    with patch.dict("sys.modules", {"cv2": None}):
        assert storage_module._load_cv2() is None
