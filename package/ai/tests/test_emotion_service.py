"""Unit tests for app/services/emotion_service.py.

EmotionService is a pure-Python module (PIL + numpy + colorsys) that extracts
dominant colors, brightness, saturation, and an emotion hint from a
base64-encoded image. No ML model is involved, so the tests build tiny PNGs
in memory and round-trip them through `analyze()`.

Covers:
- empty batch returns an empty list
- single-image happy path returns the documented schema
- bad base64 yields a per-image error entry (does not abort the batch)
- high-saturation warm color triggers the "vibrant" / "warm" classification
- dark image triggers the "night scene" category
"""

import base64
import io

import numpy as np
import pytest
from PIL import Image

from app.services.emotion_service import (
    EmotionService,
    _classify_emotion,
    _infer_categories_from_color,
    _is_greenish,
    _is_skin_tone,
    _kmeans_colors,
    _rgb_to_hex,
    emotion_service,
)


pytestmark = [pytest.mark.smoke]


# ----------------------- helpers -----------------------


def _png_b64(rgb, size=64):
    """Encode a flat-color RGB image as base64 PNG."""
    arr = np.full((size, size, 3), rgb, dtype=np.uint8)
    img = Image.fromarray(arr, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _png_b64_pixels(pixels):
    """Encode an arbitrary HxWx3 image as base64 PNG."""
    img = Image.fromarray(pixels.astype(np.uint8), mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


# ----------------------- pure-helper unit tests -----------------------


def test_rgb_to_hex_zero_pads_components():
    assert _rgb_to_hex(0, 0, 0) == "#000000"
    assert _rgb_to_hex(255, 255, 255) == "#FFFFFF"
    assert _rgb_to_hex(1, 16, 255) == "#0110FF"


def test_kmeans_colors_returns_empty_for_empty_pixels():
    centers, labels = _kmeans_colors(np.empty((0, 3), dtype=np.float32))
    assert centers.size == 0
    assert labels.size == 0


def test_kmeans_colors_clusters_uniform_pixels_into_k_centers():
    rng = np.random.RandomState(0)
    pixels = rng.randint(0, 256, size=(120, 3)).astype(np.float32)
    centers, labels = _kmeans_colors(pixels, k=3)
    assert centers.shape == (3, 3)
    assert labels.shape == (120,)
    assert set(labels.tolist()).issubset({0, 1, 2})


def test_classify_emotion_vibrant_when_saturated_and_bright():
    assert _classify_emotion(0.05, 0.8, 0.8, 0.9) == "vibrant"


def test_classify_emotion_muted_when_dark_and_desaturated():
    assert _classify_emotion(0.5, 0.1, 0.2, 0.0) == "muted"


def test_classify_emotion_warm_when_high_warm_ratio():
    # bright > 0.55 (so not muted), warm_ratio > 0.5 -> warm
    assert _classify_emotion(0.1, 0.3, 0.6, 0.7) == "warm"


def test_classify_emotion_cool_when_hue_in_blue_band():
    # bright > 0.55 so not muted; hue in (0.45, 0.75); warm_ratio low
    assert _classify_emotion(0.6, 0.3, 0.6, 0.0) == "cool"


def test_classify_emotion_neutral_fallback():
    # sat > 0.5 so not muted; warm_ratio low; hue outside (0.45, 0.75) -> neutral
    assert _classify_emotion(0.3, 0.6, 0.4, 0.1) == "neutral"


def test_is_greenish_true_for_grass_green():
    assert _is_greenish("#2E8B57") is True


def test_is_greenish_false_for_red_and_blue():
    assert _is_greenish("#FF0000") is False
    assert _is_greenish("#0000FF") is False


def test_is_skin_tone_true_for_warm_orange():
    assert _is_skin_tone("#E0AC7A") is True


def test_is_skin_tone_false_for_pure_red_and_blue():
    assert _is_skin_tone("#FF0000") is False
    assert _is_skin_tone("#0000FF") is False


def test_infer_categories_returns_default_when_no_signals():
    cats = _infer_categories_from_color(
        [{"hex": "#FFFFFF", "ratio": 1.0}],
        brightness=0.4,
        saturation=0.4,
    )
    assert cats == ["日常"]


def test_infer_categories_appends_outdoor_for_dominant_green():
    cats = _infer_categories_from_color(
        [{"hex": "#33AA33", "ratio": 1.0}],
        brightness=0.6,
        saturation=0.5,
    )
    assert "户外" in cats


def test_infer_categories_appends_night_when_dark():
    cats = _infer_categories_from_color(
        [{"hex": "#000000", "ratio": 1.0}],
        brightness=0.2,
        saturation=0.1,
    )
    assert "夜景" in cats


# ----------------------- service integration tests -----------------------


@pytest.fixture
def service():
    return EmotionService()


def test_emotion_service_singleton_is_emotion_service_instance():
    """The module-level singleton must be an EmotionService instance."""
    assert isinstance(emotion_service, EmotionService)


@pytest.mark.asyncio
async def test_analyze_empty_batch_returns_empty_list(service):
    results = await service.analyze([])
    assert results == []


@pytest.mark.asyncio
async def test_analyze_varied_image_returns_success_schema(service):
    # kmeans_colors needs many distinct points; a solid or 2-color image
    # can leave the kmeans++ initializer with zero-probability candidates.
    rng = np.random.RandomState(42)
    pixels = rng.randint(0, 256, size=(96, 96, 3), dtype=np.uint8)
    b64 = _png_b64_pixels(pixels)
    results = await service.analyze([b64])

    assert len(results) == 1
    out = results[0]
    assert out["status"] == "success"
    assert isinstance(out["dominant_colors"], list)
    assert len(out["dominant_colors"]) >= 1
    for c in out["dominant_colors"]:
        assert "hex" in c and c["hex"].startswith("#")
        assert 0.0 <= c["ratio"] <= 1.0
    assert 0.0 <= out["brightness"] <= 1.0
    assert 0.0 <= out["saturation"] <= 1.0
    assert out["emotion_hint"] in {"vibrant", "warm", "cool", "neutral", "muted"}
    assert isinstance(out["top_categories"], list)
    assert out.get("error") is None


@pytest.mark.asyncio
async def test_analyze_invalid_base64_yields_error_entry_not_crash(service):
    results = await service.analyze(["!!!not-base64!!!"])
    assert len(results) == 1
    out = results[0]
    assert out["status"] == "error"
    assert out["error"]
    assert out["dominant_colors"] == []
    assert out["brightness"] is None


@pytest.mark.asyncio
async def test_analyze_isolates_error_per_image(service):
    """A bad image in a batch must not poison the good one."""
    rng = np.random.RandomState(7)
    good_pixels = rng.randint(0, 256, size=(96, 96, 3), dtype=np.uint8)
    good_b64 = _png_b64_pixels(good_pixels)
    results = await service.analyze(["!!!not-base64!!!", good_b64])
    assert len(results) == 2
    assert results[0]["status"] == "error"
    assert results[1]["status"] == "success"


@pytest.mark.asyncio
async def test_analyze_dark_image_triggers_night_category(service):
    # Build a near-black image with a tiny color variance so K-Means can run.
    pixels = np.random.RandomState(0).randint(0, 30, size=(48, 48, 3), dtype=np.uint8)
    b64 = _png_b64_pixels(pixels)
    results = await service.analyze([b64])
    assert results[0]["status"] == "success"
    assert results[0]["brightness"] < 0.35
    assert "夜景" in results[0]["top_categories"]



