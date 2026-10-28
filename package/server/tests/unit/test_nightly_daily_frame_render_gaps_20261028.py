"""2026-10-28 nightly coverage for ``app/service/daily_frame_render.py``.

The 2026-10-28 backend coverage scan reported ``service/daily_frame_render.py``
at 80.1% with 49 uncovered lines.  The uncovered code is the *tooling* layer of
the daily-frame film feature:

* the FFmpeg / FFprobe / CJK-font discovery helpers and the capability report
  that tells the user why exporting is unavailable;
* the duration probe (FFprobe first, OpenCV as the fallback);
* the still/overlay compositor;
* the encoder wrapper -- timeout, non-zero exit and cancellation handling;
* the segment builder for still and video sources;
* the cancellation guard at the start of ``render_work``.

None of it needs a database, so every case here is a pure unit test.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import ImageDraw, ImageFont


pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


FONT = r"C:\Windows\Fonts\msyh.ttc"


def _stub_font():
    """Replace the font loader with a stub.

    The CI image has no Chinese font installed and ``ImageFont.truetype``
    raises ``OSError`` for a missing file.  ``capabilities()`` only checks
    that the font can be loaded, so a stub is enough there.
    """
    return patch("app.service.daily_frame_render.ImageFont.truetype", return_value=MagicMock())


def _font_file():
    """A font that can be loaded on this machine, if there is one.

    The drawing tests need a real font; the CI image ships DejaVu while
    Windows ships a CJK font, so the file is looked up at runtime.
    """
    for candidate in (
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ):
        if os.path.isfile(candidate):
            return candidate
    return None


def _probe_name():
    """FFprobe sits next to FFmpeg; the suffix depends on the platform."""
    return "ffprobe.exe" if os.name == "nt" else "ffprobe"


def _measuring_draw():
    """A draw object whose text is wide enough to force the caption wrapping.

    The bundled fallback font has no Chinese glyphs, so every character would
    measure as zero and the caption would never wrap.  The real drawing is
    kept, only the measurement is replaced.
    """
    real_draw = ImageDraw.Draw
    lines = []

    class _Draw:
        def __init__(self, image, *args, **kwargs):
            self._inner = real_draw(image, *args, **kwargs)

        def textlength(self, text, font=None):
            return len(text) * 40

        def text(self, *args, **kwargs):
            lines.append(args[0] if args else kwargs.get("text"))
            return self._inner.text(*args, **kwargs)

        def __getattr__(self, item):
            return getattr(self._inner, item)

    patcher = patch("app.service.daily_frame_render.ImageDraw.Draw", side_effect=lambda image, *a, **k: _Draw(image, *a, **k))
    return patcher, lines


def _render():
    from app.service import daily_frame_render

    daily_frame_render.capabilities.cache_clear()
    return daily_frame_render


def _settings(**overrides):
    settings = {
        "orientation": "landscape",
        "show_date": True,
        "show_caption": True,
        "fit": "contain",
        "background": "#000000",
    }
    settings.update(overrides)
    return settings


def _item(**overrides):
    item = {"day": "2024-05-06", "caption": "上海外滩", "mode": "still", "start_seconds": 0}
    item.update(overrides)
    return item


# ---------------------------------------------------------------------------
# tool discovery
# ---------------------------------------------------------------------------


def test_ffmpeg_path_prefers_the_configured_binary(tmp_path):
    render = _render()
    binary = tmp_path / "ffmpeg.exe"
    binary.write_bytes(b"x")
    with patch.dict(os.environ, {"TS_FFMPEG_PATH": str(binary)}):
        with patch("app.service.daily_frame_render.shutil.which", return_value=str(binary)) as which:
            assert render.ffmpeg_path() == str(binary)
    which.assert_called_once_with(str(binary))


def test_ffmpeg_path_falls_back_to_the_path_lookup():
    render = _render()
    with patch.dict(os.environ, {"TS_FFMPEG_PATH": ""}):
        with patch("app.service.daily_frame_render.shutil.which", return_value=r"C:\bin\ffmpeg.exe") as which:
            assert render.ffmpeg_path() == r"C:\bin\ffmpeg.exe"
    which.assert_called_once_with("ffmpeg")


def test_ffprobe_path_prefers_the_adjacent_binary(tmp_path):
    render = _render()
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_bytes(b"x")
    probe = tmp_path / _probe_name()
    probe.write_bytes(b"x")
    with patch("app.service.daily_frame_render.ffmpeg_path", return_value=str(ffmpeg)):
        with patch("app.service.daily_frame_render.shutil.which", return_value=None) as which:
            assert render.ffprobe_path() == str(probe)
    which.assert_not_called()


def test_ffprobe_path_falls_back_to_the_path_lookup():
    render = _render()
    with patch("app.service.daily_frame_render.ffmpeg_path", return_value=None):
        with patch("app.service.daily_frame_render.shutil.which", return_value=r"C:\bin\ffprobe.exe") as which:
            assert render.ffprobe_path() == r"C:\bin\ffprobe.exe"
    which.assert_called_once_with("ffprobe")


def test_font_path_prefers_the_configured_font(tmp_path):
    render = _render()
    font = tmp_path / "font.ttc"
    font.write_bytes(b"x")
    with patch.dict(os.environ, {"TS_VIDEO_FONT": str(font)}):
        assert render.font_path() == str(font)


def test_font_path_is_none_when_nothing_is_installed():
    render = _render()
    with patch.dict(os.environ, {"TS_VIDEO_FONT": ""}):
        with patch("app.service.daily_frame_render.os.path.isfile", return_value=False):
            assert render.font_path() is None


# ---------------------------------------------------------------------------
# capability report
# ---------------------------------------------------------------------------


def test_capabilities_report_a_missing_ffmpeg():
    render = _render()
    with patch("app.service.daily_frame_render.ffmpeg_path", return_value=None):
        with patch("app.service.daily_frame_render.ffprobe_path", return_value=None):
            report = render.capabilities()
    assert report["available"] is False
    assert "FFmpeg" in report["reason"]


def test_capabilities_report_a_missing_chinese_font():
    render = _render()
    with patch("app.service.daily_frame_render.ffmpeg_path", return_value="ffmpeg"):
        with patch("app.service.daily_frame_render.ffprobe_path", return_value="ffprobe"):
            with patch("app.service.daily_frame_render.font_path", return_value=None):
                report = render.capabilities()
    assert report["available"] is False
    assert "字体" in report["reason"]


def test_capabilities_report_a_missing_h264_encoder():
    render = _render()
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=b"Encoders:\n mpeg4\n")
    with patch("app.service.daily_frame_render.ffmpeg_path", return_value="ffmpeg"):
        with patch("app.service.daily_frame_render.ffprobe_path", return_value="ffprobe"):
            with patch("app.service.daily_frame_render.font_path", return_value=FONT):
                with _stub_font():
                    with patch("app.service.daily_frame_render.subprocess.run", return_value=completed):
                        report = render.capabilities()
    assert report["available"] is False
    assert "H.264" in report["reason"]


def test_capabilities_are_available_with_ffmpeg_and_h264():
    render = _render()
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=b" V....D libx264  H.264")
    with patch("app.service.daily_frame_render.ffmpeg_path", return_value="ffmpeg"):
        with patch("app.service.daily_frame_render.ffprobe_path", return_value="ffprobe"):
            with patch("app.service.daily_frame_render.font_path", return_value=FONT):
                with _stub_font():
                    with patch("app.service.daily_frame_render.subprocess.run", return_value=completed):
                        report = render.capabilities()
    assert report["available"] is True
    assert report["reason"] is None


def test_capabilities_survive_a_broken_encoder():
    render = _render()
    with patch("app.service.daily_frame_render.ffmpeg_path", return_value="ffmpeg"):
        with patch("app.service.daily_frame_render.ffprobe_path", return_value="ffprobe"):
            with patch("app.service.daily_frame_render.font_path", return_value=FONT):
                with _stub_font():
                    with patch("app.service.daily_frame_render.subprocess.run", side_effect=OSError("boom")):
                        report = render.capabilities()
    assert report["available"] is False
    assert "编码器" in report["reason"]


# ---------------------------------------------------------------------------
# duration probe
# ---------------------------------------------------------------------------


def test_probe_duration_reads_the_first_stream_duration():
    render = _render()
    payload = json.dumps({"streams": [{"duration": "12.5"}], "format": {"duration": "13.0"}})
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=payload.encode())
    with patch("app.service.daily_frame_render.ffprobe_path", return_value="ffprobe"):
        with patch("app.service.daily_frame_render.subprocess.run", return_value=completed):
            assert render.probe_duration("clip.mp4") == 12.5


def test_probe_duration_falls_back_to_the_container_duration():
    render = _render()
    payload = json.dumps({"streams": [{"duration": "N/A"}], "format": {"duration": "7.25"}})
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=payload.encode())
    with patch("app.service.daily_frame_render.ffprobe_path", return_value="ffprobe"):
        with patch("app.service.daily_frame_render.subprocess.run", return_value=completed):
            assert render.probe_duration("clip.mp4") == 7.25


def test_probe_duration_ignores_unusable_values():
    render = _render()
    payload = json.dumps({"streams": [{"duration": "0"}], "format": {"duration": "inf"}})
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=payload.encode())
    with patch("app.service.daily_frame_render.ffprobe_path", return_value="ffprobe"):
        with patch("app.service.daily_frame_render.subprocess.run", return_value=completed):
            assert render.probe_duration("clip.mp4") is None


def test_probe_duration_returns_none_without_any_probe():
    render = _render()
    with patch("app.service.daily_frame_render.ffprobe_path", return_value=None):
        with patch.dict(sys.modules, {"cv2": None}):
            assert render.probe_duration("clip.mp4") is None


def test_probe_duration_uses_opencv_when_ffprobe_is_missing():
    render = _render()
    capture = MagicMock()
    capture.get.side_effect = lambda prop: {5: 25.0, 7: 250.0}.get(prop, 0.0)
    module = MagicMock()
    module.CAP_PROP_FPS = 5
    module.CAP_PROP_FRAME_COUNT = 7
    module.VideoCapture.return_value = capture
    with patch("app.service.daily_frame_render.ffprobe_path", return_value=None):
        with patch.dict(sys.modules, {"cv2": module}):
            assert render.probe_duration("clip.mp4") == 10.0
    capture.release.assert_called_once()


# ---------------------------------------------------------------------------
# output files
# ---------------------------------------------------------------------------


def test_output_root_creates_the_owner_directory(tmp_path):
    render = _render()
    owner = uuid.uuid4()
    with patch("app.service.daily_frame_render.DATA_DIR", str(tmp_path)):
        root = render.output_root(owner)
    assert root == tmp_path / "users" / str(owner) / "daily-frame"
    assert root.is_dir()


def test_remove_output_deletes_the_film_and_its_poster(tmp_path):
    render = _render()
    owner = uuid.uuid4()
    with patch("app.service.daily_frame_render.DATA_DIR", str(tmp_path)):
        root = render.output_root(owner)
        film = root / "work-1.mp4"
        film.write_bytes(b"x")
        poster = root / "work-1.jpg"
        poster.write_bytes(b"x")
        render.remove_output(owner, str(film))
    assert not film.exists()
    assert not poster.exists()


def test_remove_output_ignores_a_path_outside_the_owner_root(tmp_path):
    render = _render()
    owner = uuid.uuid4()
    stranger = tmp_path / "stranger.mp4"
    stranger.write_bytes(b"x")
    with patch("app.service.daily_frame_render.DATA_DIR", str(tmp_path)):
        render.output_root(owner)
        render.remove_output(owner, str(stranger))
    assert stranger.exists()


def test_remove_output_ignores_a_file_with_the_wrong_suffix(tmp_path):
    render = _render()
    owner = uuid.uuid4()
    with patch("app.service.daily_frame_render.DATA_DIR", str(tmp_path)):
        root = render.output_root(owner)
        other = root / "notes.txt"
        other.write_bytes(b"x")
        render.remove_output(owner, str(other))
    assert other.exists()


# ---------------------------------------------------------------------------
# composition
# ---------------------------------------------------------------------------


def test_dimensions_follow_the_orientation():
    render = _render()
    assert render.dimensions(_settings(orientation="portrait")) == (1080, 1920)
    assert render.dimensions(_settings(orientation="landscape")) == (1920, 1080)


def test_make_overlay_returns_an_empty_layer_without_text():
    render = _render()
    font = _font_file()
    if font is None:
        pytest.skip("no usable font on this machine")
    with patch("app.service.daily_frame_render.font_path", return_value=font):
        overlay = render.make_overlay(_item(caption=""), _settings(show_caption=False, show_date=False))
    assert overlay.size == (1920, 1080)
    assert overlay.getbbox() is None


def test_make_overlay_draws_the_date_and_the_caption():
    render = _render()
    font = _font_file()
    if font is None:
        pytest.skip("no usable font on this machine")
    with patch("app.service.daily_frame_render.font_path", return_value=font):
        overlay = render.make_overlay(_item(), _settings())
    assert overlay.getbbox() is not None


def test_make_overlay_wraps_a_long_caption_into_several_lines():
    render = _render()
    font = _font_file()
    if font is None:
        pytest.skip("no usable font on this machine")
    patcher, lines = _measuring_draw()
    with patch("app.service.daily_frame_render.font_path", return_value=font):
        with patcher:
            render.make_overlay(_item(caption="短"), _settings(show_date=False))
    assert len(lines) == 1

    patcher, lines = _measuring_draw()
    with patch("app.service.daily_frame_render.font_path", return_value=font):
        with patcher:
            render.make_overlay(_item(caption="很长的中文说明文字" * 8), _settings(show_date=False))
    # A long caption is split over several lines.
    assert len(lines) > 1


def test_compose_still_writes_a_canvas_of_the_expected_size(tmp_path):
    from PIL import Image

    render = _render()
    source = tmp_path / "photo.jpg"
    Image.new("RGB", (400, 300), "red").save(source)
    destination = tmp_path / "still.png"
    font = _font_file()
    if font is None:
        pytest.skip("no usable font on this machine")
    with patch("app.service.daily_frame_render.font_path", return_value=font):
        render.compose_still(str(source), _item(), _settings(fit="cover"), destination)
    with Image.open(destination) as produced:
        assert produced.size == (1920, 1080)


# ---------------------------------------------------------------------------
# encoder wrapper
# ---------------------------------------------------------------------------


def _process(returncode=0, polls=(0,)):
    """A Popen double whose ``poll`` walks ``polls`` and then stays put."""
    process = MagicMock()
    remaining = list(polls)

    def poll():
        return remaining.pop(0) if remaining else returncode

    process.poll.side_effect = poll
    process.returncode = returncode
    return process


def test_run_encoder_reports_a_non_zero_exit():
    render = _render()
    process = _process(returncode=1, polls=(None,))
    with patch("app.service.daily_frame_render.ffmpeg_path", return_value="ffmpeg"):
        with patch("app.service.daily_frame_render.subprocess.Popen", return_value=process):
            with pytest.raises(RuntimeError) as excinfo:
                render.run_encoder(["-i", "a.mp4"], Path("."), lambda: None)
    assert "素材无法解码" in str(excinfo.value)


def test_run_encoder_times_out():
    render = _render()
    process = _process(returncode=0, polls=(None, None, None))
    with patch("app.service.daily_frame_render.ffmpeg_path", return_value="ffmpeg"):
        with patch("app.service.daily_frame_render.subprocess.Popen", return_value=process):
            with patch("app.service.daily_frame_render.time.monotonic", side_effect=[0.0, 0.0, 999.0, 999.0]):
                with pytest.raises(RuntimeError) as excinfo:
                    render.run_encoder(["-i", "a.mp4"], Path("."), lambda: None, timeout=10)
    assert "超时" in str(excinfo.value)


def test_run_encoder_polls_for_cancellation():
    render = _render()
    process = _process(returncode=0, polls=(None,))
    with patch("app.service.daily_frame_render.ffmpeg_path", return_value="ffmpeg"):
        with patch("app.service.daily_frame_render.subprocess.Popen", return_value=process):
            with pytest.raises(RuntimeError):
                render.run_encoder(["-i", "a.mp4"], Path("."), lambda: (_ for _ in ()).throw(RuntimeError("stop")))


def test_run_encoder_returns_when_the_process_succeeds():
    render = _render()
    process = _process(returncode=0, polls=(None,))
    with patch("app.service.daily_frame_render.ffmpeg_path", return_value="ffmpeg"):
        with patch("app.service.daily_frame_render.subprocess.Popen", return_value=process):
            render.run_encoder(["-i", "a.mp4"], Path("."), lambda: None)


# ---------------------------------------------------------------------------
# segment building
# ---------------------------------------------------------------------------


def test_encode_segment_builds_a_still_segment(tmp_path):
    render = _render()
    calls = []
    with patch("app.service.daily_frame_render.compose_still") as compose:
        with patch("app.service.daily_frame_render.run_encoder", side_effect=lambda args, *a, **k: calls.append(args)):
            result = render.encode_segment("photo.jpg", _item(mode="still"), _settings(), tmp_path, 3, False, lambda: None)
    compose.assert_called_once()
    assert result == tmp_path / "0003.mp4"
    assert "-loop" in calls[0]


def test_encode_segment_scales_a_portrait_preview(tmp_path):
    render = _render()
    calls = []
    with patch("app.service.daily_frame_render.compose_still"):
        with patch("app.service.daily_frame_render.run_encoder", side_effect=lambda args, *a, **k: calls.append(args)):
            render.encode_segment("photo.jpg", _item(mode="still"), _settings(orientation="portrait"),
                                  tmp_path, 0, True, lambda: None)
    assert "scale=360:640" in calls[0][calls[0].index("-vf") + 1]


def test_encode_segment_rejects_a_clip_that_got_shorter(tmp_path):
    render = _render()
    with patch("app.service.daily_frame_render.probe_duration", return_value=2.0):
        with pytest.raises(RuntimeError) as excinfo:
            render.encode_segment("clip.mp4", _item(mode="video", start_seconds=30), _settings(),
                                  tmp_path, 0, False, lambda: None)
    assert "时长已变化" in str(excinfo.value)


def test_encode_segment_rejects_a_clip_without_a_duration(tmp_path):
    render = _render()
    with patch("app.service.daily_frame_render.probe_duration", return_value=None):
        with pytest.raises(RuntimeError):
            render.encode_segment("clip.mp4", _item(mode="video", start_seconds=0), _settings(),
                                  tmp_path, 0, False, lambda: None)


def test_encode_segment_builds_a_video_segment(tmp_path):
    render = _render()
    calls = []
    overlay = MagicMock()
    with patch("app.service.daily_frame_render.probe_duration", return_value=30.0):
        with patch("app.service.daily_frame_render.make_overlay", return_value=overlay):
            with patch("app.service.daily_frame_render.run_encoder", side_effect=lambda args, *a, **k: calls.append(args)):
                render.encode_segment("clip.mp4", _item(mode="video", start_seconds=3), _settings(fit="cover"),
                                      tmp_path, 1, False, lambda: None)
    overlay.save.assert_called_once()
    assert "-filter_complex" in calls[0]
    assert "crop=1920:1080" in calls[0][calls[0].index("-filter_complex") + 1]


# ---------------------------------------------------------------------------
# cancellation guard
# ---------------------------------------------------------------------------


def test_render_work_is_cancelled_for_an_unknown_work():
    render = _render()
    session = MagicMock()
    session.get.return_value = None
    with patch("app.db.session.SessionLocal", return_value=session):
        with patch("app.db.models.daily_frame.DailyFrameWork", MagicMock()):
            with patch("app.db.models.task.Task", MagicMock()):
                with pytest.raises(render.RenderCancelled):
                    render.render_work(uuid.uuid4(), 1, uuid.uuid4())


def test_render_work_is_cancelled_for_a_finished_work():
    render = _render()
    work = MagicMock()
    work.generation = 2
    work.task_id = uuid.uuid4()
    work.deleted_at = None
    work.status = "ready"
    session = MagicMock()
    session.get.return_value = work
    with patch("app.db.session.SessionLocal", return_value=session):
        with patch("app.db.models.daily_frame.DailyFrameWork", MagicMock()):
            with patch("app.db.models.task.Task", MagicMock()):
                with pytest.raises(render.RenderCancelled):
                    render.render_work(uuid.uuid4(), 1, uuid.uuid4())




