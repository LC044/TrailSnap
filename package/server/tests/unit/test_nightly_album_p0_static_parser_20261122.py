"""Nightly watch 2026-11-22: ``app/service/agent/album_p0.py``::_StaticArtifactHTMLParser 盲区。

智能相册的静态 HTML 必须把正文与真实照片预渲染在 DOM 里（JS 只做增强）。
判定用的就是这个解析器：它要忽略 script/style/template 里的内容，
收集可见正文，并记录 <img src> 以便校验作品真实照片。

本文件覆盖：
- script/style/template 内的文本与图片被忽略（edge）
- 正文文本被逐段收集（happy）
- <img src> 被收集用于后续照片校验（happy）
- 嵌套的忽略标签按深度计数，收尾后恢复收集（edge）
"""

from __future__ import annotations

import pytest

from app.service.agent.album_p0 import _StaticArtifactHTMLParser


pytestmark = [pytest.mark.smoke]


def _parse(html: str) -> _StaticArtifactHTMLParser:
    parser = _StaticArtifactHTMLParser()
    parser.feed(html)
    parser.close()
    return parser


def test_visible_text_is_collected_outside_ignored_tags():
    parser = _parse("<html><body><p>第一段正文</p><p>第二段正文</p></body></html>")

    assert parser.visible_text == ["第一段正文", "第二段正文"]


def test_script_and_style_content_is_ignored():
    parser = _parse(
        "<html><body><script>var hidden = 1;</script>"
        "<style>.a{color:red}</style><p>可见正文</p></body></html>"
    )

    assert "可见正文" in parser.visible_text
    assert all("hidden" not in text for text in parser.visible_text)
    assert all("color:red" not in text for text in parser.visible_text)


def test_images_inside_ignored_tags_are_not_collected():
    parser = _parse(
        '<html><body><template><img src="/ignored.png"></template>'
        '<img src="/kept.jpg"><img src="/kept-2.jpg"></body></html>'
    )

    assert parser.image_sources == ["/kept.jpg", "/kept-2.jpg"]


def test_images_are_collected_for_the_photo_check():
    parser = _parse('<html><body><img src="/photos/real-photo.jpg" alt="x"></body></html>')

    assert parser.image_sources == ["/photos/real-photo.jpg"]


def test_nested_ignored_tags_are_counted_by_depth():
    parser = _parse(
        "<html><body><template><div><script>var a = 1;</script>"
        '<img src="/hidden.png"></template><p>恢复后的正文</p></body></html>'
    )

    assert parser.image_sources == []
    assert parser.visible_text == ["恢复后的正文"]
