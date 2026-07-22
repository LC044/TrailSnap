"""Unit tests for the export template renderer (app/utils/template.py).

The template renderer drives the file-rename task and the frontend preview UI.
A regression here silently produces malformed filenames (illegal characters,
reserved Windows names, dropped Unicode) which are hard to spot until the user
opens the export folder.  These tests cover three branches without touching
the database:

* Happy path  - ``render`` resolves every supported variable to a stable,
                sanitized string and respects the ``{sequenceN}`` short-form
                zero-padding.
* Edge case   - ``_sanitize_segment`` strips invalid FS characters,
                normalizes Unicode to NFC, and renames Windows reserved names.
* Error path  - ``validate_template`` raises ``TemplateError`` for unknown
                variables; ``render`` propagates that error so a single bad
                token does not silently produce an empty filename.
"""

import unicodedata
from types import SimpleNamespace

import pytest

from app.utils.template import (
    RenderResult,
    TemplateError,
    build_extension,
    render,
    validate_template,
    _sanitize_segment,
)


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _photo(filename="IMG_001.jpg", **overrides):
    """Build a minimal photo-like object for the renderer.

    The renderer only reads ``photo_time`` / ``upload_time`` / ``filename`` /
    ``metadata_info`` / ``tags`` / ``albums``, so a SimpleNamespace is enough.
    """
    photo = SimpleNamespace(
        filename=filename,
        photo_time=SimpleNamespace(strftime=lambda fmt: "20240715"),
        upload_time=None,
        metadata_info=None,
        tags=[],
        albums=[],
        file_type="image",
    )
    for k, v in overrides.items():
        setattr(photo, k, v)
    return photo


def test_render_happy_path_uses_supported_variables_and_zfill():
    """``render`` should resolve a typical template and apply ``sequenceN`` zero-padding.

    We stub ``photo.photo_time.strftime`` via a callable, then assert that:

    * the date token resolves to the expected value,
    * ``{sequence3}`` pads the index to 3 digits (short-form => ``{sequence:3}``),
    * the resulting ``RenderResult.name`` contains no leftover braces.
    """
    photo = _photo()
    result = render("{date}_{sequence3}_{index}", photo, index=7)

    assert isinstance(result, RenderResult)
    assert result.errors == []
    # ``photo_time.strftime("%Y%m%d")`` -> "20240715", index zero-padded to "007".
    assert result.name == "20240715_007_7"
    # No stray brace characters in the final filename.
    assert "{" not in result.name and "}" not in result.name


def test_sanitize_segment_strips_invalid_chars_and_reserved_names():
    """``_sanitize_segment`` must produce a value that is safe on every major FS.

    It is exposed for unit testing only, but every renderer output flows through
    it, so a regression here would let illegal characters (Windows ``<>:"/\\|?*``
    + control chars) leak into exported filenames.  We also verify the reserved
    name guard (``con`` / ``prn`` / ...) prefixes an underscore.
    """
    # 1. Newlines collapse to space (so the segment stays one line), invalid
    #    FS chars + control chars (including NUL) become "_".
    #    See app/utils/template.py::_sanitize_segment for the rule chain:
    #      \n / \r / \t  -> " "
    #      [<>:"/\\|?*\x00-\x1f] -> "_"
    #      rstrip " ."
    raw = "hello\nworld\x00?bad/name"
    sanitized = _sanitize_segment(raw)
    assert "\n" not in sanitized
    assert "\x00" not in sanitized
    assert "/" not in sanitized
    assert "?" not in sanitized
    # \n becomes a space, then \x00 ? / each become "_".
    assert sanitized == "hello world__bad_name"

    # 2. Reserved Windows names get an underscore prefix to stay safe on NTFS.
    assert _sanitize_segment("con") == "_con"
    assert _sanitize_segment("PRN") == "_PRN"

    # 3. NFC normalisation - combining marks collapse to the canonical form so
    #    identical-looking characters produce identical filenames.
    decomposed = "e\u0301"  # "e" + combining acute accent
    normalized = _sanitize_segment(decomposed)
    assert normalized == unicodedata.normalize("NFC", decomposed)

    # 4. None / empty / whitespace-only input returns "" instead of crashing
    #    the renderer downstream (which expects str segments).
    assert _sanitize_segment(None) == ""
    assert _sanitize_segment("   ") == ""


def test_validate_template_rejects_unknown_variables_and_render_collects_errors():
    """Unknown template variables must fail fast, and per-token errors must
    surface through ``RenderResult.errors`` when a parser raises at render-time.

    The frontend relies on ``validate_template`` to flag typos (``{datte}``),
    and the rename worker relies on ``render`` to surface per-token failures
    in ``RenderResult.errors`` (e.g. an exception inside a parser) so that a
    single bad token does not abort the whole batch.
    """
    # Validation: unknown variable raises TemplateError naming the offender.
    with pytest.raises(TemplateError) as excinfo:
        validate_template("{date}_{datte}_{unknown}")
    assert "datte" in str(excinfo.value)
    assert "unknown" in str(excinfo.value)

    # Empty template is also an error.
    with pytest.raises(TemplateError):
        validate_template("")

    # render() pre-validates and therefore propagates TemplateError too -
    # callers must validate before render OR catch TemplateError here.  We
    # assert the contract so a future refactor (e.g. dropping the inner
    # validate_template call) would surface as a test failure rather than
    # silently producing empty filenames.
    photo = _photo()
    with pytest.raises(TemplateError):
        render("{date}_{datte}", photo, index=1)

    # Render-time errors: a parser that raises gets recorded in ``errors``
    # while the rest of the template still renders.  We force a parser
    # exception by patching ``_PARSER_BY_NAME["date"]`` to raise, then run
    # a single-token template so the result is deterministic.
    import app.utils.template as tpl_mod
    original = tpl_mod._PARSER_BY_NAME["date"]
    tpl_mod._PARSER_BY_NAME["date"] = lambda photo, ctx: (_ for _ in ()).throw(ValueError("boom"))
    try:
        result = render("{date}_ok", photo, index=1)
    finally:
        tpl_mod._PARSER_BY_NAME["date"] = original
    assert result.name == "_ok"
    assert any(e.startswith("date:") for e in result.errors)

    # Sanity: build_extension falls back to .jpg when no filename is present
    # AND the file_type mapping is honoured (video -> .mp4).
    no_name = _photo(filename="")
    assert build_extension(no_name) == ".jpg"
    video = _photo(filename="clip", file_type="video")
    assert build_extension(video) == ".mp4"
