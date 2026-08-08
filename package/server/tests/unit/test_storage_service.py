"""Unit tests for app/service/storage.py.

The storage module wraps a handful of disk / Pillow / OpenCV operations
behind a small set of importable functions. We mock the storage root
(via ``update_storage_root_cache``) so each test runs against a tmp
directory and never touches the real ``data/uploads`` tree.

Covers:
- _ensure_unique_path appends "(1)" / "(2)" / ... on collision
- get_file_size returns the actual byte count
- get_image_dimensions reads a PNG via Pillow
- get_preview_path prefers .webp over .jpg, and returns None when neither exists
- delete_thumbnails removes existing thumbnails and cleans up empty directories
"""

import io
import os
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
import numpy as np
from PIL import Image

from app.service import storage
from app.service.storage import (
    _ensure_unique_path,
    _score_video_thumbnail_frame,
    _video_thumbnail_candidate_seconds,
    delete_thumbnails,
    generate_video_thumbnail,
    get_file_size,
    get_image_dimensions,
    get_preview_path,
)


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


@pytest.fixture
def isolated_storage(tmp_path, monkeypatch):
    """Pin the storage root to a tmp dir so we never touch the real one.

    ``_get_storage_root`` in production is hardcoded to ``./data/uploads`` and
    ignores ``update_storage_root_cache``. We monkey-patch the private
    function so the public helpers (get_preview_path, delete_thumbnails)
    read/write the tmp directory.
    """
    monkeypatch.setattr(storage, "_get_storage_root", lambda user_id, db=None: str(tmp_path))
    return tmp_path


# ----------------------- _ensure_unique_path -----------------------


def test_ensure_unique_path_returns_original_when_no_collision(tmp_path):
    assert _ensure_unique_path(str(tmp_path), "photo.jpg") == os.path.join(str(tmp_path), "photo.jpg")


def test_ensure_unique_path_appends_paren_one_on_collision(tmp_path):
    (tmp_path / "photo.jpg").write_bytes(b"")
    result = _ensure_unique_path(str(tmp_path), "photo.jpg")
    assert result == os.path.join(str(tmp_path), "photo(1).jpg")


def test_ensure_unique_path_appends_paren_two_on_double_collision(tmp_path):
    (tmp_path / "photo.jpg").write_bytes(b"")
    (tmp_path / "photo(1).jpg").write_bytes(b"")
    result = _ensure_unique_path(str(tmp_path), "photo.jpg")
    assert result == os.path.join(str(tmp_path), "photo(2).jpg")


# ----------------------- get_file_size -----------------------


def test_get_file_size_returns_actual_byte_count(tmp_path):
    p = tmp_path / "blob.bin"
    p.write_bytes(b"\x00" * 1024)
    assert get_file_size(str(p)) == 1024


def test_get_file_size_raises_for_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        get_file_size(str(tmp_path / "absent.bin"))


# ----------------------- get_image_dimensions -----------------------


def test_get_image_dimensions_reads_png_size(tmp_path):
    p = tmp_path / "tiny.png"
    Image.new("RGB", (123, 87), (255, 0, 0)).save(p)
    width, height, meta = get_image_dimensions(str(p))
    assert width == 123
    assert height == 87
    assert meta is None


def test_get_image_dimensions_uses_provided_image_obj(tmp_path):
    img = Image.new("RGB", (45, 67))
    width, height, meta = get_image_dimensions("unused-path.png", image_obj=img)
    assert (width, height) == (45, 67)
    assert meta is None


def test_get_image_dimensions_returns_none_tuple_for_missing_file(tmp_path):
    width, height, meta = get_image_dimensions(str(tmp_path / "absent.png"))
    assert width is None and height is None and meta is None


# ----------------------- get_preview_path -----------------------


def test_get_preview_path_prefers_webp_over_jpg(isolated_storage):
    file_id = uuid.uuid4()
    compact = str(file_id).replace("-", "")
    p1, p2 = compact[:2], compact[2:4]
    base = isolated_storage / "thumbnails" / p1 / p2
    base.mkdir(parents=True, exist_ok=True)
    (base / f"{compact}.jpg").write_bytes(b"jpg")
    webp = base / f"{compact}.webp"
    webp.write_bytes(b"webp")

    found = get_preview_path(uuid.uuid4(), file_id)
    assert found == str(webp)


def test_get_preview_path_falls_back_to_jpg(isolated_storage):
    file_id = uuid.uuid4()
    compact = str(file_id).replace("-", "")
    p1, p2 = compact[:2], compact[2:4]
    base = isolated_storage / "thumbnails" / p1 / p2
    base.mkdir(parents=True, exist_ok=True)
    jpg = base / f"{compact}.jpg"
    jpg.write_bytes(b"jpg")

    found = get_preview_path(uuid.uuid4(), file_id)
    assert found == str(jpg)


def test_get_preview_path_returns_none_when_no_thumb(isolated_storage):
    assert get_preview_path(uuid.uuid4(), uuid.uuid4()) is None


# ----------------------- delete_thumbnails -----------------------


def test_delete_thumbnails_removes_existing_files_and_empty_dirs(isolated_storage):
    file_id = uuid.uuid4()
    compact = str(file_id).replace("-", "")
    p1, p2 = compact[:2], compact[2:4]
    base = isolated_storage / "thumbnails" / p1 / p2
    base.mkdir(parents=True, exist_ok=True)
    webp = base / f"{compact}.webp"
    webp_thumb = base / f"{compact}-thumb.webp"
    jpg = base / f"{compact}.jpg"
    webp.write_bytes(b"x")
    webp_thumb.write_bytes(b"x")
    jpg.write_bytes(b"x")

    delete_thumbnails(uuid.uuid4(), file_id)

    assert not webp.exists()
    assert not webp_thumb.exists()
    assert not jpg.exists()
    # Both nested dirs should be cleaned up because they are now empty.
    assert not base.exists()
    assert not (isolated_storage / "thumbnails" / p1).exists()


def test_delete_thumbnails_is_noop_when_nothing_to_delete(isolated_storage):
    # Should not raise even though the directories do not exist.
    delete_thumbnails(uuid.uuid4(), uuid.uuid4())


# ----------------------- video thumbnails -----------------------


def test_video_thumbnail_candidates_include_later_frames_without_exceeding_duration():
    positions = _video_thumbnail_candidate_seconds(10.0)

    assert positions[0] == 0.0
    assert any(position >= 1.0 for position in positions)
    assert len(positions) == len(set(positions))
    assert all(0.0 <= position < 10.0 for position in positions)


def test_video_thumbnail_frame_score_rejects_black_frame():
    black = np.zeros((8, 8, 3), dtype=np.uint8)
    detailed = np.indices((8, 8)).sum(axis=0) % 2 * 180 + 30
    detailed = np.repeat(detailed[:, :, None], 3, axis=2).astype(np.uint8)

    assert _score_video_thumbnail_frame(black) == float("-inf")
    assert _score_video_thumbnail_frame(detailed) > 0


class _FakeVideoCapture:
    def __init__(self, opened=True):
        self.opened = opened
        self.position_ms = 0.0
        self.released = False

    def isOpened(self):
        return self.opened

    def get(self, prop):
        if prop == _FakeCV2.CAP_PROP_FPS:
            return 10.0
        if prop == _FakeCV2.CAP_PROP_FRAME_COUNT:
            return 100.0
        return 0.0

    def set(self, prop, value):
        assert prop == _FakeCV2.CAP_PROP_POS_MSEC
        self.position_ms = value
        return True

    def read(self):
        if self.position_ms == 0:
            return True, np.zeros((8, 8, 3), dtype=np.uint8)
        detailed = np.indices((8, 8)).sum(axis=0) % 2 * 180 + 30
        frame = np.repeat(detailed[:, :, None], 3, axis=2).astype(np.uint8)
        return True, frame

    def release(self):
        self.released = True


class _FakeCV2:
    CAP_PROP_FPS = 1
    CAP_PROP_FRAME_COUNT = 2
    CAP_PROP_POS_MSEC = 3
    COLOR_BGR2RGB = 4

    def __init__(self, capture):
        self.capture = capture

    def VideoCapture(self, _path):
        return self.capture

    @staticmethod
    def cvtColor(frame, _conversion):
        return frame[:, :, ::-1]


def test_generate_video_thumbnail_skips_black_first_frame_and_releases_capture():
    capture = _FakeVideoCapture()
    fake_cv2 = _FakeCV2(capture)

    with patch.object(storage, "cv2", fake_cv2), \
         patch.object(storage, "_save_thumbnails", return_value="thumbnail.webp") as save_mock:
        result = generate_video_thumbnail("video.mp4", uuid.uuid4(), uuid.uuid4())

    assert result == "thumbnail.webp"
    assert capture.released is True
    selected_image = save_mock.call_args.args[0]
    assert np.asarray(selected_image).mean() > 0


def test_generate_video_thumbnail_releases_capture_when_video_cannot_open():
    capture = _FakeVideoCapture(opened=False)

    with patch.object(storage, "cv2", _FakeCV2(capture)):
        result = generate_video_thumbnail("broken.mp4", uuid.uuid4(), uuid.uuid4())

    assert result is None
    assert capture.released is True
