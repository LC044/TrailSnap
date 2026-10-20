"""Nightly coverage for the module-level helpers in
``app.service.agent.album_p0``.

Targets the 2026-10-19 backend coverage gap (service/agent/album_p0.py
77.7%, 124 missed statements -- the largest thin-covered module in the
gap list) by exercising the pure helpers above the DB-backed queries.

These six helpers (``_StaticArtifactHTMLParser``,
``_validate_static_artifact_html``, ``_iso``, ``_uuid_list``,
``_string_list``, ``_normalize_artifact_content``) had zero direct
coverage before this file. The artifact-HTML safety net -- the code that
actually rejects a JavaScript-only export -- was only ever hit
incidentally.

The helpers are pure and DB-free, so these cases need no session
fixture, mirroring ``test_nightly_video_tools_helpers_gaps_20261020``.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import pytest

from app.service.agent.album_p0 import (
    _iso,
    _normalize_artifact_content,
    _StaticArtifactHTMLParser,
    _string_list,
    _uuid_list,
    _validate_static_artifact_html,
)


pytestmark = [pytest.mark.smoke]


# _validate_static_artifact_html requires >= 80 visible characters of body
# text, so these fixtures straddle that floor on purpose.
VALID_BODY = "travel body " * 9  # 108 chars -> clears the floor
SHORT_BODY = "short"  # 5 chars -> below the floor

IMG_P1 = '<img src="p1.jpg">'
IMG_UNRELATED = '<img src="unrelated.jpg">'
IMG_SIGNED = '<img src="/media/p1.jpg?sig=abc">'


# ---------------------------------------------------------------------------
# _iso: nullable datetime -> ISO string
# ---------------------------------------------------------------------------


def test_iso_formats_datetime():
    """Happy path: a datetime is rendered with .isoformat()."""
    assert _iso(datetime(2026, 1, 2, 3, 4, 5)) == "2026-01-02T03:04:05"


@pytest.mark.parametrize("falsy", [None, False, 0, ""])
def test_iso_returns_none_for_falsy(falsy):
    """Edge: the helper is total over the nullable columns it wraps."""
    assert _iso(falsy) is None


# ---------------------------------------------------------------------------
# _uuid_list: tolerant photo-id parsing with dedupe + limit
# ---------------------------------------------------------------------------


def test_uuid_list_parses_dedupes_and_preserves_order():
    """Happy path: valid ids come back as UUIDs, deduped, in input order."""
    first, second = str(uuid4()), str(uuid4())
    assert _uuid_list([first, second, first], limit=10) == [
        UUID(first),
        UUID(second),
    ]


def test_uuid_list_stops_at_limit():
    """Edge: the limit caps results, so later ids never reach UUID()."""
    ids = [str(uuid4()) for _ in range(5)]
    assert len(_uuid_list(ids, limit=2)) == 2


@pytest.mark.parametrize("junk", ["not-a-uuid", None, 123, object()])
def test_uuid_list_skips_unparsable_values(junk):
    """Error path: a bad entry is skipped, not raised on."""
    good = str(uuid4())
    assert _uuid_list([junk, good], limit=10) == [UUID(good)]


def test_uuid_list_accepts_uuid_objects():
    """Edge: UUID instances stringify cleanly through str()."""
    value = uuid4()
    assert _uuid_list([value], limit=10) == [value]


def test_uuid_list_empty_when_nothing_parsable():
    """Edge: fully invalid input yields an empty list, not None."""
    assert _uuid_list(["nope", None], limit=10) == []


# ---------------------------------------------------------------------------
# _string_list: narrow list-of-str coercion
# ---------------------------------------------------------------------------


def test_string_list_coerces_and_drops_falsy_items():
    """Happy path: truthy entries are stringified, falsy ones dropped."""
    assert _string_list(["a", "", "b"]) == ["a", "b"]


@pytest.mark.parametrize("value", [None, "abc", 5, {"a": 1}, ("x", "y")])
def test_string_list_ignores_non_list_inputs(value):
    """Error/edge: anything that is not a list returns [].

    A tuple deliberately returns [] -- this is a contract guard for model
    output, and the artifact schema only ever emits JSON arrays.
    """
    assert _string_list(value) == []


# ---------------------------------------------------------------------------
# _StaticArtifactHTMLParser: DOM walk that ignores script/style/template
# ---------------------------------------------------------------------------


def test_parser_collects_visible_text_and_images_only():
    """Happy path: text and img srcs are captured; script/style bodies are not."""
    html = (
        "<div>Hello <script>var x = 1;</script>"
        "<style>.a { color: red; }</style>"
        "World"
        '<img src="a.jpg"><img src="b.jpg"></div>'
    )
    parser = _StaticArtifactHTMLParser()
    parser.feed(html)
    assert parser.visible_text == ["Hello", "World"]
    assert parser.image_sources == ["a.jpg", "b.jpg"]


def test_parser_ignores_img_inside_ignored_depth():
    """Edge: an img nested in template is ignored (ignored_depth > 0)."""
    html = '<template><img src="hidden.jpg"></template><img src="real.jpg">'
    parser = _StaticArtifactHTMLParser()
    parser.feed(html)
    assert parser.image_sources == ["real.jpg"]


def test_parser_skips_imgs_without_src():
    """Edge: an attribute-less or empty-src img contributes nothing."""
    html = '<img alt="no source"><img src=""><img src="ok.jpg">'
    parser = _StaticArtifactHTMLParser()
    parser.feed(html)
    assert parser.image_sources == ["ok.jpg"]


def test_parser_drops_whitespace_only_data():
    """Edge: blank text nodes never reach visible_text."""
    parser = _StaticArtifactHTMLParser()
    parser.feed("<p>   \n\t  </p><p> kept </p>")
    assert parser.visible_text == ["kept"]


def test_parser_endtag_ignores_unbalanced_close():
    """Edge: a stray closing tag must not drive ignored_depth negative."""
    parser = _StaticArtifactHTMLParser()
    parser.feed("</script>visible")
    assert parser.ignored_depth == 0
    assert parser.visible_text == ["visible"]


# ---------------------------------------------------------------------------
# _validate_static_artifact_html: progressive-enhancement safety net
# ---------------------------------------------------------------------------


def test_validate_accepts_prerendered_html_with_matching_photo():
    """Happy path: enough body text plus a real photo id in an img src."""
    _validate_static_artifact_html("<p>" + VALID_BODY + "</p>" + IMG_P1, ["p1"])


def test_validate_skips_photo_check_when_no_ids_requested():
    """Edge: with no photo_ids the image requirement is not enforced."""
    _validate_static_artifact_html("<p>" + VALID_BODY + "</p>", [])


def test_validate_rejects_javascript_only_body():
    """Error: body text must be server-rendered, not produced by JS."""
    with pytest.raises(ValueError, match="预渲染主要正文"):
        _validate_static_artifact_html("<p>" + SHORT_BODY + "</p>" + IMG_P1, ["p1"])


def test_validate_rejects_missing_prerendered_photo():
    """Error: an artifact that shows none of the requested photos is refused."""
    with pytest.raises(ValueError, match="真实照片"):
        _validate_static_artifact_html(
            "<p>" + VALID_BODY + "</p>" + IMG_UNRELATED, ["p1"]
        )


def test_validate_matches_photo_id_as_substring_of_src():
    """Edge: src is matched by containment, not equality (signed urls)."""
    _validate_static_artifact_html("<p>" + VALID_BODY + "</p>" + IMG_SIGNED, ["p1"])


def test_validate_reports_unparsable_input():
    """Error: a non-string payload surfaces as the parse failure, not a crash."""
    with pytest.raises(ValueError, match="无法解析"):
        _validate_static_artifact_html(None, [])


# ---------------------------------------------------------------------------
# _normalize_artifact_content: model-alias -> editable artifact contract
# ---------------------------------------------------------------------------


def test_normalize_none_yields_empty_contract():
    """Edge: no content still yields the two contract keys."""
    assert _normalize_artifact_content(None) == {"sections": [], "summary": ""}


def test_normalize_maps_title_alias_to_heading():
    """Happy path: title/narrative aliases fill heading and body."""
    out = _normalize_artifact_content(
        {
            "sections": [
                {"title": "首日", "narrative": "抵达", "photo_ids": ["1", None]}
            ],
            "summary": "ok",
        }
    )
    section = out["sections"][0]
    assert section["heading"] == "首日"
    assert section["body"] == "抵达"
    assert section["photo_ids"] == ["1"]
    assert out["summary"] == "ok"


def test_normalize_lifts_singular_photo_id_into_photo_ids():
    """Edge: the photo_id alias is lifted into the photo_ids list."""
    out = _normalize_artifact_content(
        {"sections": [{"location": "京都", "photo_id": "9", "description": "d"}]}
    )
    section = out["sections"][0]
    assert section["heading"] == "京都"
    assert section["body"] == "d"
    assert section["photo_ids"] == ["9"]


def test_normalize_defaults_heading_by_position():
    """Edge: a section with no alias at all gets a positional heading."""
    out = _normalize_artifact_content({"sections": [{}]})
    assert out["sections"][0]["heading"] == "第 1 段"
    assert out["sections"][0]["body"] == ""
    assert out["sections"][0]["photo_ids"] == []


def test_normalize_skips_non_dict_sections_but_keeps_enumerate_index():
    """Edge: junk entries are dropped, yet the default heading keeps the
    original index so numbering reflects the model's own ordering."""
    out = _normalize_artifact_content(
        {"sections": ["junk", {"heading": "H"}], "summary": None}
    )
    assert out["sections"] == [{"heading": "H", "body": "", "photo_ids": []}]
    assert out["summary"] == ""


def test_normalize_prefers_existing_heading_over_title():
    """Edge: heading wins over the title alias when both are present."""
    out = _normalize_artifact_content(
        {"sections": [{"heading": "H", "title": "T", "story": "S"}]}
    )
    assert out["sections"][0]["heading"] == "H"
    assert out["sections"][0]["body"] == "S"


def test_normalize_coerces_non_string_scalars():
    """Edge: numeric summary/heading are stringified for the edit contract."""
    out = _normalize_artifact_content({"sections": [{"heading": 7}], "summary": 2026})
    assert out["sections"][0]["heading"] == "7"
    assert out["summary"] == "2026"


def test_normalize_does_not_mutate_input():
    """Edge: the caller's dict is copied, not rewritten in place."""
    original = {"sections": [{"title": "T"}]}
    _normalize_artifact_content(original)
    assert original == {"sections": [{"title": "T"}]}
