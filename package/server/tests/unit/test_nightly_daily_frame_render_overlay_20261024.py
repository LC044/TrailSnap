"""Nightly coverage for the daily-frame overlay and still composition (2026-10-24).

The 2026-10-24 backend coverage gap ranked ``service/daily_frame_render.py``
second (44.3%, 137 of 246 statements uncovered). The 2026-10-18 nightly file
covered the *capability detection* half of the module -- ``ffmpeg_path``,
``ffprobe_path``, ``font_path`` and ``capabilities``.

The remaining half is the part that actually produces the user's video:
``make_overlay`` builds the caption card that is burned into every frame, and
``compose_still`` renders the photo behind it. Those functions decide what the
user ends up seeing, and a silent layout bug there would ship unnoticed, so
this file pins down the overlay geometry and the composition pipeline.

The tests use Pillow to generate real input images rather than mocking the
imaging calls, so the assertions describe actual rendered output.

Font handling: ``make_overlay`` calls ``ImageFont.truetype(font_path(), size)``
and ``font_path()`` returns ``None`` on a machine without a CJK font -- which
is exactly the CI container (Debian, no Noto CJK installed). The production
path guards this via ``capabilities()`` / a 503, but a unit test must not
inherit the host's font configuration, so the ``bundled_font`` fixture
substitutes Pillow's own embedded font. That keeps the suite hermetic and
identical on Windows and Linux.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import ImageFont

from app.service import daily_frame_render


pytestmark = [pytest.mark.smoke]


@pytest.fixture()
def bundled_font(monkeypatch):
    """Render with Pillow's embedded font instead of a host CJK font."""
    from PIL import ImageFont as pil_font

    class _EmbeddedFont:
        """Stand-in for the ``PIL.ImageFont`` module.

        ``daily_frame_render`` calls ``ImageFont.truetype(font_path(), size)``.
        Replacing the module reference (rather than patching ``truetype`` on the
        real module) keeps ``PIL.ImageFont.load_default`` working, because it
        calls the original ``truetype`` internally.
        """

        @staticmethod
        def truetype(font, size=10, *args, **kwargs):
            return pil_font.load_default(size=size)

    monkeypatch.setattr(daily_frame_render, "font_path", lambda: None)
    monkeypatch.setattr(daily_frame_render, "ImageFont", _EmbeddedFont)


def _settings(**overrides) -> dict:
    settings = {
        "orientation": "landscape",
        "fit": "cover",
        "background": (0, 0, 0, 255),
        "show_date": True,
        "show_caption": True,
    }
    settings.update(overrides)
    return settings


def _item(**overrides) -> dict:
    item = {"day": "2024-05-07", "caption": "测试字幕", "mode": "still", "start_seconds": 0}
    item.update(overrides)
    return item


def _write_photo(path: Path, size=(200, 120), color=(200, 40, 40)) -> Path:
    from PIL import Image

    Image.new("RGB", size, color).save(path)
    return path


def _opaque_band(overlay):
    """Return (top, bottom) of the drawn caption band, or None."""
    bbox = overlay.getchannel("A").getbbox()
    if bbox is None:
        return None
    return bbox[1], bbox[3]


# ---------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------


def test_dimensions_follow_the_orientation_setting():
    """Portrait output is a vertical frame, landscape is horizontal."""
    assert daily_frame_render.dimensions(_settings(orientation="portrait")) == (1080, 1920)
    assert daily_frame_render.dimensions(_settings(orientation="landscape")) == (1920, 1080)


# ---------------------------------------------------------------------------
# make_overlay
# ---------------------------------------------------------------------------


def test_overlay_has_the_frame_size(bundled_font):
    """The overlay must match the output frame exactly or compositing misaligns."""
    overlay = daily_frame_render.make_overlay(_item(), _settings())

    assert overlay.size == (1920, 1080)


def test_overlay_is_transparent_where_no_text_is_drawn(bundled_font):
    """Only the caption band is opaque; the rest stays transparent."""
    overlay = daily_frame_render.make_overlay(_item(), _settings())

    assert overlay.getpixel((5, 5))[3] == 0


def test_overlay_renders_the_date_with_dots_instead_of_dashes(bundled_font):
    """The date is rendered as 'YYYY.MM.DD'.

    ``make_overlay`` replaces the dashes of the ISO day with dots, so a dashed
    day and an already dotted day must render identically.
    """
    dashed = daily_frame_render.make_overlay(_item(day="2024-05-07"), _settings(show_caption=False))
    dotted = daily_frame_render.make_overlay(_item(day="2024.05.07"), _settings(show_caption=False))

    assert dashed.tobytes() == dotted.tobytes()


def test_overlay_omits_the_date_when_disabled(bundled_font):
    """Hiding the date must not draw it."""
    with_date = daily_frame_render.make_overlay(_item(), _settings(show_date=True))
    without_date = daily_frame_render.make_overlay(_item(), _settings(show_date=False))

    assert _opaque_band(with_date) is not None
    assert _opaque_band(without_date) is not None
    assert with_date.getbbox() != without_date.getbbox()


def test_overlay_omits_the_caption_when_disabled(bundled_font):
    """Hiding the caption leaves only the date on the band."""
    with_caption = daily_frame_render.make_overlay(_item(caption="很长很长的字幕内容"), _settings())
    without_caption = daily_frame_render.make_overlay(
        _item(caption="很长很长的字幕内容"), _settings(show_caption=False)
    )

    assert without_caption.getbbox() != with_caption.getbbox()


def test_overlay_without_date_or_caption_is_fully_transparent(bundled_font):
    """With both options off there is nothing to draw."""
    overlay = daily_frame_render.make_overlay(
        _item(), _settings(show_date=False, show_caption=False)
    )

    assert overlay.getbbox() is None


def test_overlay_wraps_a_long_caption_into_several_lines(bundled_font):
    """A caption wider than 80% of the frame is split, not clipped."""
    short = daily_frame_render.make_overlay(
        _item(caption="简短"), _settings(show_date=False)
    )
    long = daily_frame_render.make_overlay(
        _item(caption="很长很长的字幕内容" * 40), _settings(show_date=False)
    )

    short_band, long_band = _opaque_band(short), _opaque_band(long)
    assert short_band is not None and long_band is not None
    # Each extra caption line adds one 60px line height, so the wrapped band
    # must be clearly taller than the single-line band.
    assert long_band[1] - long_band[0] > short_band[1] - short_band[0] + 50


# ---------------------------------------------------------------------------
# compose_still
# ---------------------------------------------------------------------------


def test_compose_still_writes_a_frame_sized_rgb_image(tmp_path, bundled_font):
    """The composed still is an RGB image at the requested frame size."""
    source = _write_photo(tmp_path / "photo.jpg")
    destination = tmp_path / "still.png"

    daily_frame_render.compose_still(
        str(source), _item(), _settings(orientation="portrait"), destination
    )

    from PIL import Image

    with Image.open(destination) as composed:
        assert composed.size == (1080, 1920)
        assert composed.mode == "RGB"


def test_compose_still_centres_a_smaller_photo(tmp_path, bundled_font):
    """A photo smaller than the frame is centred rather than stretched."""
    source = _write_photo(tmp_path / "photo.jpg", size=(100, 60))
    destination = tmp_path / "still.png"

    daily_frame_render.compose_still(
        str(source), _item(), _settings(fit="contain"), destination
    )

    from PIL import Image

    with Image.open(destination) as composed:
        pixels = composed.convert("RGB").load()
        # The photo is centred, so the middle of the frame carries the photo
        # colour while the top-left corner keeps the background.
        assert pixels[960, 540] != (0, 0, 0)
        assert pixels[5, 5] == (0, 0, 0)


def test_compose_still_fills_the_frame_with_cover_fit(tmp_path, bundled_font):
    """'cover' fills the whole frame, so no background shows through."""
    source = _write_photo(tmp_path / "photo.jpg", size=(100, 60))
    destination = tmp_path / "still.png"

    daily_frame_render.compose_still(
        str(source), _item(), _settings(fit="cover"), destination
    )

    from PIL import Image

    with Image.open(destination) as composed:
        pixels = composed.convert("RGB").load()
        assert pixels[5, 5] != (0, 0, 0)
