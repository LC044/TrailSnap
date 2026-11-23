"""Nightly watch 2026-11-23 - app/service/agent/album_p0.py 的静态 HTML 解析盲区。

相册的静态产物必须在 DOM 里预渲染正文和真实照片，JavaScript 只做增强。
_StaticArtifactHTMLParser 负责剥掉 script/style/template 并收集可见文本与
图片地址，_validate_static_artifact_html 用它做门禁。

本文件覆盖：

- script/style/template 里的文本与图片被忽略（edge）
- img 的 src 被收集，普通文本被 strip 后保留（happy）
- 可见文本不足 80 字时门禁拒绝（error）
- 没有引用到指定 photo_id 的图片时门禁拒绝（error）
- 文本充足且图片命中时门禁通过（happy）
"""

import pytest

from app.service.agent.album_p0 import (
    _StaticArtifactHTMLParser,
    _validate_static_artifact_html,
)

pytestmark = [pytest.mark.smoke]


def _parse(html: str) -> _StaticArtifactHTMLParser:
    parser = _StaticArtifactHTMLParser()
    parser.feed(html)
    return parser


def test_script_and_style_content_is_ignored():
    parser = _parse(
        "<div>正文</div>"
        "<script>var secret = 1;</script>"
        "<style>.a{color:red}</style>"
        "<template><p>草稿</p></template>"
    )

    assert parser.visible_text == ["正文"]
    assert parser.image_sources == []


def test_images_inside_ignored_blocks_are_not_collected():
    parser = _parse('<script><img src="/uploads/secret.png"></script><img src="/uploads/real.png">')

    assert parser.image_sources == ["/uploads/real.png"]


def test_visible_text_is_stripped_and_image_sources_collected():
    parser = _parse('<p>  旅行  </p><img src="/uploads/a.png" alt="x"><img alt="no src">')

    assert parser.visible_text == ["旅行"]
    assert parser.image_sources == ["/uploads/a.png"]


def test_validation_rejects_html_without_enough_visible_text():
    with pytest.raises(ValueError, match="预渲染主要正文"):
        _validate_static_artifact_html("<p>太短</p>", [])


def test_validation_rejects_html_without_a_matching_photo():
    html = "<p>" + "正文" * 60 + "</p><img src=\"/uploads/other.png\">"

    with pytest.raises(ValueError, match="至少一张作品真实照片"):
        _validate_static_artifact_html(html, ["photo-1"])


def test_validation_accepts_html_with_enough_text_and_a_matching_photo():
    html = "<p>" + "正文" * 60 + "</p><img src=\"/uploads/photo-1.jpg\">"

    _validate_static_artifact_html(html, ["photo-1"])
