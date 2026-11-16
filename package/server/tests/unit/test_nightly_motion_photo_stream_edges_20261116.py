"""2026-11-16 nightly coverage for ``app/utils/motion_photo.py``.

The 2026-11-16 backend coverage scan reported ``utils/motion_photo.py`` at
94.0% with 25 missed lines.  The branches still missing are the defensive
ones around the import-snapshot extractor and the cleanup path of
``extract_video``:

* ``extract_video_from_stream`` without a source object (line 19);
* ``extract_video_from_stream`` reusing an output file that already exists
  (line 48) -- the import snapshot must not rewrite the user's file;
* ``extract_video_from_stream`` swallowing an unexpected exception
  (lines 54-55) -- a broken stream must not abort the import;
* ``extract_video`` failing to remove a partial output file (lines 184-185)
  -- the cleanup error is swallowed on purpose, the caller still gets None.
"""

import io
from pathlib import Path
from unittest.mock import patch

import pytest

from app.utils import motion_photo


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def test_extract_video_from_stream_without_a_source_returns_none(tmp_path):
    assert motion_photo.extract_video_from_stream(None, str(tmp_path / "out.mp4")) is None


def test_extract_video_from_stream_reuses_an_existing_output_file(tmp_path):
    source = io.BytesIO(b"header" + b'MicroVideoOffset="8"' + b"12345678")
    video_path = tmp_path / "out.mp4"
    video_path.write_bytes(b"already there")

    assert motion_photo.extract_video_from_stream(source, str(video_path)) == str(video_path)
    # The existing file must be left untouched.
    assert video_path.read_bytes() == b"already there"


def test_extract_video_from_stream_swallows_an_unexpected_exception(tmp_path):
    class BrokenStream:
        def seek(self, *_args):
            raise OSError("boom")

    assert motion_photo.extract_video_from_stream(BrokenStream(), str(tmp_path / "out.mp4")) is None


def test_extract_video_swallows_a_failed_cleanup(tmp_path):
    source = tmp_path / "photo.jpg"
    source.write_bytes(b"x" * 64)
    video_path = tmp_path / "out.mp4"

    def fake_budgeted_open(path, mode="rb", *_args, **_kwargs):
        if "w" in mode:
            # Simulate a half written file followed by a write failure.
            Path(path).write_bytes(b"partial")
            raise OSError("disk full")
        return open(path, mode)

    with patch.object(motion_photo, "budgeted_open", fake_budgeted_open), \
            patch("os.remove", side_effect=OSError("locked by another process")):
        assert motion_photo.extract_video(str(source), offset=8, video_path=str(video_path)) is None

    # The partial file cannot be removed, but the caller is not affected.
    assert video_path.exists()
