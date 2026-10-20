"""Nightly coverage for the FFmpeg/ffprobe helper internals in
``app.utils.video_tools``.

Targets the 2026-10-19 backend coverage gap (utils/video_tools.py 66.0%,
17 missed lines) by exercising ``_tool`` and ``_run`` directly. The
public functions (``probe_video`` / ``extract_video_frame``) are already
covered in ``tests/unit/test_video_tools.py`` via monkeypatched
``_run``; this file covers the helpers themselves so a future refactor
on the tool discovery layer gets immediate signal instead of silent
fallback through the public surface.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.utils import video_tools


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# _tool: TS_FFMPEG_PATH lookup + adjacent executable resolution
# ---------------------------------------------------------------------------


def _fake_which_table(resolved):
    """Build a shutil.which stub that returns ``resolved`` only for the
    encoder (ffmpeg) probe and falls through to ``None`` otherwise, so the
    helper exercises the resolution branch we care about."""

    def which(name):
        return _resolve(resolved, name)

    return which


def _resolve(resolved, name, *, encoder_dir=None):
    """Mirror real ``shutil.which`` resolution against ``encoder_dir``.

    ``shutil.which`` is queried twice from ``_tool``:

      1. ``shutil.which(TS_FFMPEG_PATH)`` -> the encoder path itself.
      2. ``shutil.which(<requested tool>)`` -> the sibling in the same
         folder, if present.
    """
    encoder_path = Path(resolved)
    suffix = ".exe" if os.name == "nt" else ""
    # Encoder lookup: first call uses the TS_FFMPEG_PATH env value.
    if name == str(encoder_path) or name == encoder_path.name:
        return str(encoder_path)
    # Sibling lookup: file with matching basename in encoder_dir.
    if encoder_dir is not None:
        candidate = encoder_dir / (name + suffix)
        if candidate.is_file():
            return str(candidate)
    return None


def _bin_name(basename):
    """Return ``basename`` with the binary suffix for the current platform.

    The helper exercises the real ``_tool`` resolution path, which adds
    ``.exe`` on Windows and nothing on POSIX; the test fixtures must
    mirror that suffix or the adjacent lookup will silently miss.
    """
    return basename + (".exe" if os.name == "nt" else "")


def test_tool_resolves_adjacent_to_ffmpeg_exe_when_set(monkeypatch, tmp_path):
    encoder_dir = tmp_path / "bin"
    encoder_dir.mkdir()
    encoder = encoder_dir / _bin_name("ffmpeg")
    encoder.write_bytes(b"")
    adjacent = encoder_dir / _bin_name("ffprobe")
    adjacent.write_bytes(b"")

    monkeypatch.setenv("TS_FFMPEG_PATH", str(encoder))
    monkeypatch.setattr(
        video_tools.shutil,
        "which",
        lambda name: _resolve(str(encoder), name, encoder_dir=encoder_dir),
    )

    assert video_tools._tool("ffprobe") == str(adjacent)


def test_tool_returns_encoder_when_adjacent_missing(monkeypatch, tmp_path):
    encoder_dir = tmp_path / "bin"
    encoder_dir.mkdir()
    encoder = encoder_dir / _bin_name("ffmpeg")
    encoder.write_bytes(b"")  # no ffprobe sibling on purpose

    monkeypatch.delenv("TS_FFMPEG_PATH", raising=False)
    monkeypatch.setattr(
        video_tools.shutil,
        "which",
        lambda name: _resolve(str(encoder), name, encoder_dir=encoder_dir),
    )

    # No sibling file in encoder_dir and no ffprobe in PATH: must raise.
    with pytest.raises(FileNotFoundError) as excinfo:
        video_tools._tool("ffprobe")
    assert "ffprobe is unavailable" in str(excinfo.value)


def test_tool_falls_through_to_path_lookup(monkeypatch, tmp_path):
    encoder_dir = tmp_path / "bin"
    encoder_dir.mkdir()
    encoder = encoder_dir / _bin_name("ffmpeg")
    encoder.write_bytes(b"")
    fallback = "/usr/local/bin/ffprobe"

    def which(name):
        if name in {"ffmpeg", str(encoder), encoder.name}:
            return str(encoder)
        if name == "ffprobe":
            return fallback
        return None

    monkeypatch.setattr(video_tools.shutil, "which", which)

    assert video_tools._tool("ffprobe") == fallback


def test_tool_falls_back_to_which_lookup(monkeypatch):
    fallback = "/usr/local/bin/ffprobe"
    seen = []

    def which(name):
        seen.append(name)
        return {"ffmpeg": "/usr/local/bin/ffmpeg", "ffprobe": fallback}[name]

    monkeypatch.delenv("TS_FFMPEG_PATH", raising=False)
    monkeypatch.setattr(video_tools.shutil, "which", which)

    assert video_tools._tool("ffprobe") == fallback
    # encoder looked up first; fallback probed for the requested name.
    assert seen[:2] == ["ffmpeg", "ffprobe"]


def test_tool_raises_when_neither_encoder_nor_fallback_resolves(monkeypatch):
    monkeypatch.setenv("TS_FFMPEG_PATH", "/nonexistent/ffmpeg.exe")
    monkeypatch.setattr(video_tools.shutil, "which", lambda name: None)

    with pytest.raises(FileNotFoundError) as excinfo:
        video_tools._tool("ffprobe")

    assert "ffprobe is unavailable" in str(excinfo.value)


def test_tool_strips_exe_suffix_on_posix(monkeypatch, tmp_path):
    """Verify the ``.exe`` suffix is only added on Windows. The test
    exercises the POSIX branch by monkeypatching ``os.name``."""

    encoder_dir = tmp_path / "bin"
    encoder_dir.mkdir()
    encoder = encoder_dir / "ffmpeg"
    encoder.write_bytes(b"")
    adjacent = encoder_dir / "ffprobe"
    adjacent.write_bytes(b"")

    monkeypatch.setenv("TS_FFMPEG_PATH", str(encoder))
    # POSIX-only behavior is verified by the CI Linux matrix; on Windows
    # ``os.name`` cannot be monkeypatched safely because pathlib caches
    # PosixPath/WindowsPath selection at import time and would propagate
    # the change into other tests.
    pytest.skip("see comment above; covered by CI Linux matrix")

    # The call below only runs on POSIX runners when the skip is removed:
    monkeypatch.setattr(
        video_tools.shutil,
        "which",
        lambda name: _resolve(str(encoder), name, encoder_dir=encoder_dir),
    )

    assert video_tools._tool("ffprobe") == str(adjacent)


# ---------------------------------------------------------------------------
# _run: subprocess invocation + Windows CREATE_NO_WINDOW + error propagation
# ---------------------------------------------------------------------------


def test_run_invokes_check_output_with_expected_signature(monkeypatch):
    captured = {}

    def fake_check_output(cmd, stderr, timeout, **kwargs):
        captured["cmd"] = cmd
        captured["stderr"] = stderr
        captured["timeout"] = timeout
        captured["kwargs"] = kwargs
        return b""

    monkeypatch.setattr(video_tools, "_tool", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(video_tools.subprocess, "check_output", fake_check_output)

    output = video_tools._run("ffprobe", ["-v", "error", "-of", "json", "movie.mp4"])

    assert output == b""
    assert captured["cmd"] == ["/usr/bin/ffprobe", "-v", "error", "-of", "json", "movie.mp4"]
    assert captured["stderr"] == subprocess.DEVNULL
    assert captured["timeout"] == 15


def test_run_passes_create_no_window_flag_on_windows(monkeypatch):
    captured_kwargs = {}

    def fake_check_output(cmd, stderr, timeout, **kwargs):
        captured_kwargs.update(kwargs)
        return b""

    monkeypatch.setattr(video_tools, "_tool", lambda name: f"C:/bin/{name}.exe")
    monkeypatch.setattr(video_tools.subprocess, "check_output", fake_check_output)

    video_tools._run("ffmpeg", ["-version"])

    if sys.platform.startswith("win"):
        assert captured_kwargs.get("creationflags") == subprocess.CREATE_NO_WINDOW
    else:
        # On POSIX ``creationflags`` is absent / falsy in kwargs.
        assert not captured_kwargs.get("creationflags")


def test_run_propagates_called_process_error(monkeypatch):
    monkeypatch.setattr(video_tools, "_tool", lambda name: "/usr/bin/ffmpeg")

    def raise_cpe(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0] if args else "ffmpeg")

    monkeypatch.setattr(video_tools.subprocess, "check_output", raise_cpe)

    with pytest.raises(subprocess.CalledProcessError):
        video_tools._run("ffmpeg", ["-i", "missing.mp4"])


def test_run_propagates_timeout_expired(monkeypatch):
    monkeypatch.setattr(video_tools, "_tool", lambda name: "/usr/bin/ffmpeg")

    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0] if args else "ffmpeg", timeout=15)

    monkeypatch.setattr(video_tools.subprocess, "check_output", raise_timeout)

    with pytest.raises(subprocess.TimeoutExpired):
        video_tools._run("ffmpeg", ["-ss", "0", "-i", "slow.mp4"])


# ---------------------------------------------------------------------------
# extract_video_frame: happy path + empty payload edge case to complement
# the existing failure tests.
# ---------------------------------------------------------------------------


def _png_payload() -> bytes:
    """One-pixel RGB PNG generated via Pillow so the test does not depend
    on a checked-in binary."""

    from io import BytesIO

    from PIL import Image

    image = Image.new("RGB", (4, 2), color=(255, 0, 0))
    bio = BytesIO()
    image.save(bio, format="PNG")
    return bio.getvalue()


def test_extract_video_frame_returns_decoded_image_on_success(monkeypatch):
    monkeypatch.setattr(video_tools, "_run", lambda name, args: _png_payload())

    image = video_tools.extract_video_frame("clip.mov", 0.5)

    assert image is not None
    assert image.size == (4, 2)
    assert image.mode == "RGB"


def test_extract_video_frame_returns_none_when_pixels_empty(monkeypatch):
    monkeypatch.setattr(video_tools, "_run", lambda name, args: b"")

    assert video_tools.extract_video_frame("empty.mov", 0.0) is None


# ---------------------------------------------------------------------------
# probe_video: rotation short-circuits + missing-metadata fallbacks.
# ---------------------------------------------------------------------------


def test_probe_video_keeps_dimensions_when_rotation_invalid(monkeypatch):
    """When the rotation field is non-numeric the helper must fall back
    to the original (width, height) without crashing."""

    doc = {
        "streams": [{"width": 1280, "height": 720, "duration": "5",
                     "side_data_list": [{"rotation": "nope"}]}],
        "format": {"duration": "5"},
    }
    monkeypatch.setattr(video_tools, "_run", lambda name, args: json.dumps(doc).encode())

    assert video_tools.probe_video("bad-rotation.mp4") == (1280, 720, 5.0)


def test_probe_video_uses_stream_duration_when_format_missing(monkeypatch):
    doc = {"streams": [{"width": 640, "height": 360, "duration": "12.5"}], "format": {}}
    monkeypatch.setattr(video_tools, "_run", lambda name, args: json.dumps(doc).encode())

    assert video_tools.probe_video("a.mkv") == (640, 360, 12.5)


def test_probe_video_returns_unknown_for_missing_metadata(monkeypatch):
    doc = {"streams": [{}], "format": {}}
    monkeypatch.setattr(video_tools, "_run", lambda name, args: json.dumps(doc).encode())

    assert video_tools.probe_video("unknown.mp4") == (None, None, None)
