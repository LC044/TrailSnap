"""2026-11-19 nightly coverage for the static artifact HTML gate in
``app/service/agent/album_p0.py``.

``_StaticArtifactHTMLParser`` and ``_validate_static_artifact_html`` were
never referenced by any test file.  They are the server-side guarantee that an
agent-authored page ships real pre-rendered text and at least one real photo,
so JavaScript stays a progressive enhancement.
"""

from __future__ import annotations

import pytest

from app.service.agent.album_p0 import (
    _StaticArtifactHTMLParser,
    _validate_static_artifact_html,
)


pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


PHOTO_ID = "11111111-2222-3333-4444-555555555555"
OTHER_PHOTO_ID = "11111111-2222-3333-4444-666666666666"

LONG_TEXT = "这是一段足够长的正文内容，用来满足必须在 DOM 中预渲染主要正文的要求。" * 3


def _parse(html: str) -> _StaticArtifactHTMLParser:
    parser = _StaticArtifactHTMLParser()
    parser.feed(html)
    return parser


def test_visible_text_is_collected():
    parser = _parse("<html><body><p>你好</p><p>世界</p></body></html>")

    assert parser.visible_text == ["你好", "世界"]


def test_script_and_style_content_is_ignored():
    parser = _parse(
        "<html><body><script>var x = 1;</script><style>p{color:red}</style>"
        "<p>正文</p></body></html>"
    )

    assert parser.visible_text == ["正文"]


def test_image_sources_are_collected_outside_ignored_tags():
    parser = _parse(
        f'<html><body><img src="/media/{PHOTO_ID}.jpg"><img src="/other.jpg"></body></html>'
    )

    assert parser.image_sources == [f"/media/{PHOTO_ID}.jpg", "/other.jpg"]


def test_images_inside_a_template_tag_are_ignored():
    parser = _parse('<html><body><template><img src="/hidden.jpg"></template></body></html>')

    assert parser.image_sources == []


def test_an_image_without_a_source_is_skipped():
    parser = _parse("<html><body><img alt='no source'></body></html>")

    assert parser.image_sources == []


def test_html_with_too_little_pre_rendered_text_is_rejected():
    with pytest.raises(ValueError, match="必须在 DOM 中预渲染主要正文"):
        _validate_static_artifact_html("<html><body><p>短</p></body></html>", [])


def test_html_with_enough_text_is_accepted():
    _validate_static_artifact_html(f"<html><body><p>{LONG_TEXT}</p></body></html>", [])


def test_html_must_reference_a_real_photo_when_photos_are_given():
    with pytest.raises(ValueError, match="必须在 DOM 中预渲染至少一张作品真实照片"):
        _validate_static_artifact_html(
            f"<html><body><p>{LONG_TEXT}</p><img src='/other.jpg'></body></html>",
            [PHOTO_ID],
        )


def test_html_referencing_a_real_photo_is_accepted():
    _validate_static_artifact_html(
        f'<html><body><p>{LONG_TEXT}</p><img src="/media/{PHOTO_ID}.jpg"></body></html>',
        [PHOTO_ID],
    )


def test_any_of_the_photo_ids_may_be_referenced():
    _validate_static_artifact_html(
        f'<html><body><p>{LONG_TEXT}</p><img src="/media/{OTHER_PHOTO_ID}.jpg"></body></html>',
        [PHOTO_ID, OTHER_PHOTO_ID],
    )


def test_a_photo_reference_inside_a_script_tag_does_not_count():
    with pytest.raises(ValueError, match="必须在 DOM 中预渲染至少一张作品真实照片"):
        _validate_static_artifact_html(
            f'<html><body><p>{LONG_TEXT}</p><script>var s="/media/{PHOTO_ID}.jpg";</script></body></html>',
            [PHOTO_ID],
        )
