"""Nightly watch 2026-11-22 · 静态作品 HTML 校验与磁盘预算装饰器盲区。

两处此前没有任何测试直接引用的逻辑：

- ``app/service/agent/album_p0.py::_StaticArtifactHTMLParser`` /
  ``_validate_static_artifact_html``：AI 生成的相册作品页必须服务端预渲染正文
  与至少一张真实照片，JS 只能做渐进增强。解析器要忽略 script/style/template
  里的内容，否则隐藏文本会被当成正文放行。
- ``app/service/disk_budget.py::media_io``：给同步媒体作业套上磁盘并发闸门，
  按参数名取出路径并占用对应卷的槽位；嵌套调用共享同一槽位不死锁。

本文件覆盖 happy / edge / error 三类。
"""

import os

import pytest

from app.service.agent import album_p0
from app.service.disk_budget import DiskBudget, media_io

pytestmark = [pytest.mark.smoke]


_LONG_BODY = ("这是一段足够长的服务端预渲染正文，用来证明主要文字确实出现在 DOM 之中，" + "而不是由 JavaScript 动态生成；相册作品页必须包含可读的说明文字与真实照片。")


# --------------------------------------------------------------------------- #
# _validate_static_artifact_html
# --------------------------------------------------------------------------- #

def test_static_artifact_html_accepts_prerendered_text_and_photo():
    html = f"<html><body><p>{_LONG_BODY}</p><img src='/files/photo-1.jpg'/></body></html>"

    album_p0._validate_static_artifact_html(html, ["photo-1"])


def test_static_artifact_html_rejects_a_body_rendered_only_by_javascript():
    html = "<html><body><div id='app'></div><script>render()</script></body></html>"

    with pytest.raises(ValueError, match="预渲染主要正文"):
        album_p0._validate_static_artifact_html(html, [])


def test_static_artifact_html_ignores_script_and_style_content():
    parser = album_p0._StaticArtifactHTMLParser()
    parser.feed(
        "<html><head><style>body{color:red}</style></head>"
        "<body><script>var x = 1;</script><p>可见正文</p></body></html>"
    )

    assert "".join(parser.visible_text) == "可见正文"
    assert "color:red" not in "".join(parser.visible_text)
    assert "var x = 1;" not in "".join(parser.visible_text)


def test_static_artifact_html_requires_a_real_photo_source():
    html = f"<html><body><p>{_LONG_BODY}</p></body></html>"

    with pytest.raises(ValueError, match="至少一张作品真实照片"):
        album_p0._validate_static_artifact_html(html, ["photo-1"])


def test_static_artifact_html_collects_img_sources_outside_ignored_blocks():
    parser = album_p0._StaticArtifactHTMLParser()
    parser.feed(
        "<html><body><template><img src='/ignored.jpg'/></template>"
        "<img src='/real.jpg'/></body></html>"
    )

    assert parser.image_sources == ["/real.jpg"]


# --------------------------------------------------------------------------- #
# disk_budget.media_io
# --------------------------------------------------------------------------- #

def test_media_io_admits_the_job_and_releases_the_slot(tmp_path, monkeypatch):
    budget = DiskBudget(limit=1)
    monkeypatch.setattr("app.service.disk_budget.disk_budget", budget)
    observed = {}

    @media_io()
    def job(file_path):
        observed["active"] = dict(budget._active)
        return os.path.basename(file_path)

    assert job(str(tmp_path / "a.jpg")) == "a.jpg"
    # 作业结束后槽位必须已经释放
    assert sum(budget._active.values()) == 0
    assert sum(observed["active"].values()) == 1


def test_media_io_honours_a_custom_path_argument_name(tmp_path, monkeypatch):
    budget = DiskBudget(limit=1)
    monkeypatch.setattr("app.service.disk_budget.disk_budget", budget)

    @media_io("source")
    def job(source):
        return source

    assert job(str(tmp_path / "b.jpg")).endswith("b.jpg")
    assert sum(budget._active.values()) == 0


def test_media_io_shares_one_slot_for_nested_calls(tmp_path, monkeypatch):
    budget = DiskBudget(limit=1)
    monkeypatch.setattr("app.service.disk_budget.disk_budget", budget)

    @media_io()
    def inner(file_path):
        return sum(budget._active.values())

    @media_io()
    def outer(file_path):
        # 嵌套调用必须复用同一个槽位，否则会在 limit=1 时自我死锁
        return inner(file_path)

    assert outer(str(tmp_path / "c.jpg")) == 1
    assert sum(budget._active.values()) == 0

