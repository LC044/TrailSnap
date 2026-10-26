"""Nightly coverage for the video helpers of ``app/service/daily_frame_render.py``.

The 2026-10-26 backend coverage scan listed ``service/daily_frame_render.py`` at
54.9% with 111 missed lines.  The missed lines are the ones that talk to the
outside world:

* ``ffprobe_path`` / ``font_path`` / ``capabilities`` decide whether the
  optional FFmpeg toolchain is usable at all.
* ``probe_duration`` reads the real duration of a clip, with an OpenCV
  fallback when ffprobe is missing.
* ``run_encoder`` drives ffmpeg and has to fail cleanly on a decoder error or
  a timeout.
* ``encode_segment`` turns one selected item into a one-second segment.

None of the branches need a real FFmpeg installation: the subprocess layer is
replaced by small fakes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import types
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.smoke]


class _Completed:
    def __init__(self, stdout=b"", returncode=0):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = b""


class _FakeProcess:
    """Minimal ``subprocess.Popen`` stand-in for the encoder loop."""

    def __init__(self, returncode=0, running_forever=False):
        self.returncode = None if running_forever else returncode
        self._running_forever = running_forever
        self.terminated = False
        self.killed = False

    def poll(self):
        if self._running_forever:
            return None
        return self.returncode

    def terminate(self):
        self.terminated = True
        self._running_forever = False

    def kill(self):
        self.killed = True
        self._running_forever = False

    def wait(self, timeout=None):
        return self.returncode or 0


# ---------------------------------------------------------------------------
# tool discovery
# ---------------------------------------------------------------------------


def test_ffprobe_path_prefers_the_binary_next_to_ffmpeg(monkeypatch, tmp_path):
    from app.service import daily_frame_render

    tools = tmp_path / "bin"
    tools.mkdir()
    ffmpeg = tools / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    ffprobe = tools / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
    ffmpeg.write_bytes(b"")
    ffprobe.write_bytes(b"")
    monkeypatch.setattr(daily_frame_render, "ffmpeg_path", lambda: str(ffmpeg))

    assert daily_frame_render.ffprobe_path() == str(ffprobe)


def test_ffprobe_path_falls_back_to_the_path_lookup(monkeypatch, tmp_path):
    from app.service import daily_frame_render

    tools = tmp_path / "bin"
    tools.mkdir()
    ffmpeg = tools / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    ffmpeg.write_bytes(b"")
    monkeypatch.setattr(daily_frame_render, "ffmpeg_path", lambda: str(ffmpeg))
    monkeypatch.setattr(daily_frame_render.shutil, "which", lambda name: "/usr/bin/ffprobe")

    assert daily_frame_render.ffprobe_path() == "/usr/bin/ffprobe"


def test_font_path_prefers_the_configured_file(monkeypatch, tmp_path):
    from app.service import daily_frame_render

    font = tmp_path / "custom.ttc"
    font.write_bytes(b"")
    monkeypatch.setenv("TS_VIDEO_FONT", str(font))

    assert daily_frame_render.font_path() == str(font)


def test_font_path_returns_none_when_no_font_is_installed(monkeypatch):
    from app.service import daily_frame_render

    monkeypatch.delenv("TS_VIDEO_FONT", raising=False)
    monkeypatch.setattr(daily_frame_render.os.path, "isfile", lambda path: False)

    assert daily_frame_render.font_path() is None


# ---------------------------------------------------------------------------
# capabilities
# ---------------------------------------------------------------------------


def test_capabilities_report_a_missing_ffmpeg(monkeypatch):
    from app.service import daily_frame_render

    monkeypatch.setattr(daily_frame_render, "ffmpeg_path", lambda: None)
    daily_frame_render.capabilities.cache_clear()
    try:
        result = daily_frame_render.capabilities()
    finally:
        daily_frame_render.capabilities.cache_clear()
    assert result["available"] is False
    assert "FFmpeg" in result["reason"]


def test_capabilities_report_a_missing_font(monkeypatch):
    from app.service import daily_frame_render

    monkeypatch.setattr(daily_frame_render, "ffmpeg_path", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(daily_frame_render, "ffprobe_path", lambda: "/usr/bin/ffprobe")
    monkeypatch.setattr(daily_frame_render, "font_path", lambda: None)
    daily_frame_render.capabilities.cache_clear()
    try:
        result = daily_frame_render.capabilities()
    finally:
        daily_frame_render.capabilities.cache_clear()
    assert result["available"] is False
    assert "中文字体" in result["reason"]


def test_capabilities_report_a_broken_encoder(monkeypatch):
    from app.service import daily_frame_render

    monkeypatch.setattr(daily_frame_render, "ffmpeg_path", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(daily_frame_render, "ffprobe_path", lambda: "/usr/bin/ffprobe")
    monkeypatch.setattr(daily_frame_render, "font_path", lambda: "/fonts/Noto.ttf")
    monkeypatch.setattr(daily_frame_render.ImageFont, "truetype",
                        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("broken font")))
    daily_frame_render.capabilities.cache_clear()
    try:
        result = daily_frame_render.capabilities()
    finally:
        daily_frame_render.capabilities.cache_clear()
    assert result["available"] is False
    assert "无法使用" in result["reason"]


def test_capabilities_are_available_with_a_working_toolchain(monkeypatch):
    from app.service import daily_frame_render

    monkeypatch.setattr(daily_frame_render, "ffmpeg_path", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(daily_frame_render, "ffprobe_path", lambda: "/usr/bin/ffprobe")
    monkeypatch.setattr(daily_frame_render, "font_path", lambda: "/fonts/Noto.ttf")
    monkeypatch.setattr(daily_frame_render.ImageFont, "truetype", lambda *args, **kwargs: object())
    monkeypatch.setattr(daily_frame_render.subprocess, "run",
                        lambda *args, **kwargs: _Completed(stdout=b" V....D libx264 libx264\n"))
    daily_frame_render.capabilities.cache_clear()
    try:
        result = daily_frame_render.capabilities()
    finally:
        daily_frame_render.capabilities.cache_clear()
    assert result == {"available": True, "reason": None}


# ---------------------------------------------------------------------------
# probe_duration
# ---------------------------------------------------------------------------


def test_probe_duration_uses_ffprobe(monkeypatch):
    from app.service import daily_frame_render

    payload = json.dumps({"streams": [{"duration": "4.5"}], "format": {"duration": "4.5"}}).encode()
    monkeypatch.setattr(daily_frame_render, "ffprobe_path", lambda: "/usr/bin/ffprobe")
    monkeypatch.setattr(daily_frame_render.subprocess, "run", lambda *args, **kwargs: _Completed(stdout=payload))

    assert daily_frame_render.probe_duration("/videos/clip.mp4") == 4.5


def test_probe_duration_ignores_unusable_values(monkeypatch):
    from app.service import daily_frame_render

    payload = json.dumps({"streams": [{"duration": "NaN"}], "format": {"duration": "0"}}).encode()
    monkeypatch.setattr(daily_frame_render, "ffprobe_path", lambda: "/usr/bin/ffprobe")
    monkeypatch.setattr(daily_frame_render.subprocess, "run", lambda *args, **kwargs: _Completed(stdout=payload))

    assert daily_frame_render.probe_duration("/videos/clip.mp4") is None


def test_probe_duration_survives_a_broken_probe(monkeypatch):
    from app.service import daily_frame_render

    monkeypatch.setattr(daily_frame_render, "ffprobe_path", lambda: "/usr/bin/ffprobe")

    def _boom(*args, **kwargs):
        raise OSError("ffprobe is missing")

    monkeypatch.setattr(daily_frame_render.subprocess, "run", _boom)
    assert daily_frame_render.probe_duration("/videos/clip.mp4") is None


def test_probe_duration_falls_back_to_opencv(monkeypatch):
    from app.service import daily_frame_render

    class _Capture:
        def get(self, prop):
            return 25.0 if prop == 4 else 100.0

        def release(self):
            return None

    module = types.ModuleType("cv2")
    module.CAP_PROP_FPS = 4
    module.CAP_PROP_FRAME_COUNT = 5
    module.VideoCapture = lambda path: _Capture()
    monkeypatch.setitem(sys.modules, "cv2", module)
    monkeypatch.setattr(daily_frame_render, "ffprobe_path", lambda: None)

    assert daily_frame_render.probe_duration("/videos/clip.mp4") == 4.0


def test_probe_duration_returns_none_without_opencv(monkeypatch):
    from app.service import daily_frame_render

    monkeypatch.setitem(sys.modules, "cv2", None)
    monkeypatch.setattr(daily_frame_render, "ffprobe_path", lambda: None)

    assert daily_frame_render.probe_duration("/videos/clip.mp4") is None


# ---------------------------------------------------------------------------
# run_encoder
# ---------------------------------------------------------------------------


def test_run_encoder_accepts_a_successful_process(monkeypatch, tmp_path):
    from app.service import daily_frame_render

    monkeypatch.setattr(daily_frame_render.subprocess, "Popen", lambda *args, **kwargs: _FakeProcess())
    daily_frame_render.run_encoder(["-i", "clip.mp4"], tmp_path, lambda: None)


def test_run_encoder_reports_a_decoder_error(monkeypatch, tmp_path):
    from app.service import daily_frame_render

    monkeypatch.setattr(daily_frame_render.subprocess, "Popen", lambda *args, **kwargs: _FakeProcess(returncode=1))
    with pytest.raises(RuntimeError, match="素材无法解码"):
        daily_frame_render.run_encoder(["-i", "clip.mp4"], tmp_path, lambda: None)


def test_run_encoder_times_out(monkeypatch, tmp_path):
    from app.service import daily_frame_render

    process = _FakeProcess(running_forever=True)
    monkeypatch.setattr(daily_frame_render.subprocess, "Popen", lambda *args, **kwargs: process)
    with pytest.raises(RuntimeError, match="素材处理超时"):
        daily_frame_render.run_encoder(["-i", "clip.mp4"], tmp_path, lambda: None, timeout=0)
    assert process.terminated or process.killed


def test_run_encoder_propagates_a_cancellation(monkeypatch, tmp_path):
    from app.service import daily_frame_render

    process = _FakeProcess(running_forever=True)
    monkeypatch.setattr(daily_frame_render.subprocess, "Popen", lambda *args, **kwargs: process)

    def _cancel():
        raise RuntimeError("cancelled")

    with pytest.raises(RuntimeError, match="cancelled"):
        daily_frame_render.run_encoder(["-i", "clip.mp4"], tmp_path, _cancel)
    assert process.terminated or process.killed


# ---------------------------------------------------------------------------
# encode_segment
# ---------------------------------------------------------------------------


def test_encode_segment_rejects_an_undecodable_photo(monkeypatch, tmp_path):
    from app.service import daily_frame_render

    def _boom(*args, **kwargs):
        raise OSError("broken jpeg")

    monkeypatch.setattr(daily_frame_render, "compose_still", _boom)
    item = {"mode": "still", "day": "2026-10-26", "caption": "hello"}
    settings = {"orientation": "portrait", "show_date": True, "show_caption": True,
                "fit": "cover", "background": (0, 0, 0, 255)}

    with pytest.raises(RuntimeError, match="照片无法解码"):
        daily_frame_render.encode_segment("photo.jpg", item, settings, tmp_path, 0, True, lambda: None)


def test_encode_segment_rejects_a_changed_clip_duration(monkeypatch, tmp_path):
    from app.service import daily_frame_render

    monkeypatch.setattr(daily_frame_render, "probe_duration", lambda path: None)
    item = {"mode": "clip", "start_seconds": 0, "day": "2026-10-26", "caption": "hello"}
    settings = {"orientation": "landscape", "show_date": True, "show_caption": True,
                "fit": "contain", "background": (0, 0, 0, 255)}

    with pytest.raises(RuntimeError, match="动态素材时长已变化"):
        daily_frame_render.encode_segment("clip.mp4", item, settings, tmp_path, 0, True, lambda: None)


def test_encode_segment_rejects_a_clip_start_beyond_the_duration(monkeypatch, tmp_path):
    from app.service import daily_frame_render

    monkeypatch.setattr(daily_frame_render, "probe_duration", lambda path: 2.0)
    item = {"mode": "clip", "start_seconds": 30, "day": "2026-10-26", "caption": "hello"}
    settings = {"orientation": "landscape", "show_date": True, "show_caption": True,
                "fit": "contain", "background": (0, 0, 0, 255)}

    with pytest.raises(RuntimeError, match="动态素材时长已变化"):
        daily_frame_render.encode_segment("clip.mp4", item, settings, tmp_path, 0, True, lambda: None)


# ---------------------------------------------------------------------------
# remove_output
# ---------------------------------------------------------------------------


def test_remove_output_deletes_the_segment_and_its_thumbnail(monkeypatch, tmp_path):
    from app.service import daily_frame_render

    monkeypatch.setattr(daily_frame_render, "DATA_DIR", tmp_path)
    owner = uuid.uuid4()
    root = daily_frame_render.output_root(owner)
    (root / "0001.mp4").write_bytes(b"video")
    (root / "0001.jpg").write_bytes(b"thumb")

    daily_frame_render.remove_output(owner, str(root / "0001.mp4"))
    assert not (root / "0001.mp4").exists()
    assert not (root / "0001.jpg").exists()


def test_remove_output_refuses_an_unexpected_path(monkeypatch, tmp_path):
    from app.service import daily_frame_render

    monkeypatch.setattr(daily_frame_render, "DATA_DIR", tmp_path)
    owner = uuid.uuid4()
    root = daily_frame_render.output_root(owner)
    stray = root / "notes.txt"
    stray.write_text("keep", encoding="utf-8")
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"keep")

    daily_frame_render.remove_output(owner, str(stray))
    daily_frame_render.remove_output(owner, str(outside))
    assert stray.is_file()
    assert outside.is_file()
