"""Unit tests for the photo color extractor (app/utils/color.py).

The extractor powers the "色调 / 亮度 / 饱和度 / 情绪" metadata that the
classification task relies on, so a regression here silently degrades the
search-by-color experience.  These tests cover the three branches of
``extract_color_info`` without touching the database:

* Happy path  - a vivid image comes back as ``emotion_hint == "vibrant"``
                with a non-empty ``dominant_colors`` list and a deterministic
                hex format on every entry.
* Edge case   - RGBA / L images are forced through the RGB conversion path,
                preserving alpha-channel data without crashing.
* Error path  - an image with no pixels (zero-size) returns the canonical
                "empty" payload so downstream code never sees a half-filled
                dict that breaks JSON serialisation.
"""

import pytest
from PIL import Image

from app.utils.color import extract_color_info


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _solid_rgb(width, height, color):
    """Create an RGB image filled with a single color (test helper)."""
    return Image.new("RGB", (width, height), color)


def _solid_rgba(width, height, color, alpha):
    """Create an RGBA image filled with a single color (test helper)."""
    return Image.new("RGBA", (width, height), color + (alpha,))


def test_extract_color_info_vivid_image_classified_as_vibrant():
    """A mostly-red image should come back with vibrant emotion hint.

    Single-color images are deterministic: the dominant color hex and ratio
    are easy to assert, while the emotion-hint branch (high saturation
    AND high brightness) exercises the path most relevant to user-visible UX.
    """
    img = _solid_rgb(80, 80, (220, 30, 30))
    result = extract_color_info(img, max_size=40)

    assert result["emotion_hint"] == "vibrant"
    assert result["brightness"] > 0
    assert result["saturation"] > 0

    # dominant_colors must be a non-empty list with at least one entry.
    assert len(result["dominant_colors"]) >= 1
    first = result["dominant_colors"][0]
    assert set(first.keys()) == {"hex", "ratio"}
    # Hex must be in canonical "#RRGGBB" format (see ``_rgb_to_hex``).
    assert first["hex"].startswith("#") and len(first["hex"]) == 7
    # Ratio must be a positive probability (we round to 3 decimals).
    assert 0 < first["ratio"] <= 1.0


def test_extract_color_info_converts_non_rgb_to_rgb():
    """Palleted or grayscale images must survive the RGB conversion path.

    Without the ``img.convert('RGB')`` call, ``getdata()`` would yield
    tuples of length 1 (L) or bytes (P), which would break the
    ``for r, g, b in pixels`` unpacking in the quantiser.
    """
    # RGBA image with alpha - must end up as 3-channel RGB internally.
    rgba_img = _solid_rgba(40, 40, (10, 200, 50), alpha=128)
    result = extract_color_info(rgba_img)
    assert isinstance(result["dominant_colors"], list)
    assert result["brightness"] is not None
    assert result["saturation"] is not None

    # Grayscale (L) image - must not raise on ``r, g, b = ...`` unpacking.
    gray_img = Image.new("L", (40, 40), 200)
    result_gray = extract_color_info(gray_img)
    assert result_gray["emotion_hint"] is not None


def test_extract_color_info_empty_image_returns_safe_payload():
    """A zero-size image short-circuits to ``_empty_result`` so callers
    never see ``None`` values mixed with numbers (which would break the
    JSON response schema and TypeScript types downstream).
    """
    # 0x0 image has zero pixels - hits the ``if not pixels:`` short-circuit.
    empty = Image.new("RGB", (0, 0))
    result = extract_color_info(empty)

    assert result == {
        "dominant_colors": [],
        "brightness": None,
        "saturation": None,
        "emotion_hint": None,
    }
