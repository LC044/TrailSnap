"""Nightly watch 2026-11-25 · app/service/storage.py 的视频缩略图失败兜底盲区。

覆盖扫描显示 storage.py 未覆盖的行集中在 generate_video_thumbnail 的失败分支：
ffmpeg 兜底抛错（L235-L237）、OpenCV 读取抛错（L273-L274）、以及视频流打不开
时直接返回 None（L242-L243）。这些分支决定了坏视频会不会把整个上传流程拖垮，
属于必须钉住的健壮性行为。

注意：generate_video_thumbnail 通过 _load_cv2() 取 OpenCV，而不是模块级
`cv2` 变量，所以测试必须替换 _load_cv2 才能真正切换到 ffmpeg 兜底路线。
"""

from uuid import uuid4

import pytest

from app.service import storage

pytestmark = [pytest.mark.regression, pytest.mark.module_photo]


class _BoomCv2:
    """VideoCapture 直接抛错的假 OpenCV。"""

    def VideoCapture(self, path):  # noqa: N802 - 模仿 cv2 的命名
        raise RuntimeError("opencv exploded")


class _ClosedCv2:
    """能打开但视频流已损坏的假 OpenCV。"""

    class _Cap:
        def isOpened(self):  # noqa: N802 - 模仿 cv2 的命名
            return False

        def release(self):
            return None

    def VideoCapture(self, path):  # noqa: N802 - 模仿 cv2 的命名
        return self._Cap()


def test_ffmpeg_fallback_failure_returns_none(tmp_path, monkeypatch):
    video = tmp_path / "broken.mp4"
    video.write_bytes(b"not-a-video")
    monkeypatch.setattr(storage, "_load_cv2", lambda: None)

    def _boom(path):
        raise RuntimeError("ffprobe failed")

    monkeypatch.setattr(storage, "probe_video", _boom)

    assert storage.generate_video_thumbnail(str(video), uuid4(), uuid4()) is None


def test_opencv_failure_returns_none(tmp_path, monkeypatch):
    video = tmp_path / "broken.mp4"
    video.write_bytes(b"not-a-video")
    monkeypatch.setattr(storage, "_load_cv2", lambda: _BoomCv2())

    assert storage.generate_video_thumbnail(str(video), uuid4(), uuid4()) is None


def test_unreadable_video_returns_none(tmp_path, monkeypatch):
    video = tmp_path / "broken.mp4"
    video.write_bytes(b"not-a-video")
    monkeypatch.setattr(storage, "_load_cv2", lambda: _ClosedCv2())

    assert storage.generate_video_thumbnail(str(video), uuid4(), uuid4()) is None
