"""Nightly watch 2026-11-26 · app/services/emotion_service.py 的色彩情绪盲区。

情绪提取服务把缩略图拆成主色调，再据此给出情绪标签与场景类别。这套规则的
判定分支（鲜艳 / 克制 / 暖 / 冷 / 中性，以及户外 / 人像 / 夜景 / 室内 / 日常）
此前只有零散的引用，没有被逐条断言：

- 纯色图不能让 K-Means 在零距离下崩掉；
- 分类阈值必须区分「高饱和 + 高亮度」这类组合；
- 绿色主色 -> 户外，肤色主色 -> 人像，暗图 -> 夜景，低饱和中等亮度 -> 室内；
- 坏 base64 要变成一条 error 结果，而不是让整批失败。
"""

from __future__ import annotations

import base64
import io

import numpy as np
import pytest
from PIL import Image

from app.services import emotion_service as emotion

pytestmark = pytest.mark.smoke


def image_b64(color=(120, 180, 60), size=(40, 40), fmt="PNG"):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return base64.b64encode(buffer.getvalue()).decode()


# --- K-Means 与工具函数 ----------------------------------------------


def test_kmeans_on_an_empty_pixel_set_returns_empty_arrays():
    centers, labels = emotion._kmeans_colors(np.array([], dtype=np.float32), k=3)

    assert len(centers) == 0
    assert len(labels) == 0


def test_kmeans_survives_a_uniform_image():
    pixels = np.full((60, 3), 200.0, dtype=np.float32)

    centers, labels = emotion._kmeans_colors(pixels, k=5)

    assert centers.shape == (5, 3)
    assert len(labels) == 60


def test_rgb_to_hex_uses_upper_case_two_digit_channels():
    assert emotion._rgb_to_hex(255, 0, 16) == "#FF0010"


# --- 情绪分类 --------------------------------------------------------


@pytest.mark.parametrize(
    ("hue", "saturation", "brightness", "warm_ratio", "expected"),
    [
        (0.1, 0.8, 0.9, 0.6, "vibrant"),
        (0.1, 0.2, 0.2, 0.1, "muted"),
        (0.08, 0.6, 0.4, 0.8, "warm"),
        (0.6, 0.6, 0.4, 0.1, "cool"),
        (0.3, 0.6, 0.4, 0.1, "neutral"),
    ],
)
def test_classify_emotion_covers_every_label(hue, saturation, brightness, warm_ratio, expected):
    assert emotion._classify_emotion(hue, saturation, brightness, warm_ratio) == expected


# --- 场景类别 --------------------------------------------------------


def test_green_dominant_colors_mark_the_photo_as_outdoor():
    categories = emotion._infer_categories_from_color([{"hex": "#3FA050", "ratio": 0.8}], 0.7, 0.6)

    assert "户外" in categories


def test_skin_tone_dominant_colors_mark_the_photo_as_portrait():
    categories = emotion._infer_categories_from_color([{"hex": "#E0A080", "ratio": 0.8}], 0.6, 0.4)

    assert "人像" in categories


def test_a_dark_photo_is_marked_as_a_night_scene():
    categories = emotion._infer_categories_from_color([{"hex": "#202030", "ratio": 1.0}], 0.2, 0.2)

    assert "夜景" in categories


def test_a_dull_mid_bright_photo_is_marked_as_indoor():
    categories = emotion._infer_categories_from_color([{"hex": "#909090", "ratio": 1.0}], 0.45, 0.1)

    assert "室内" in categories


def test_a_plain_photo_falls_back_to_the_daily_category():
    categories = emotion._infer_categories_from_color([{"hex": "#505060", "ratio": 1.0}], 0.9, 0.9)

    assert categories == ["日常"]


def test_greenish_and_skin_tone_helpers_reject_unrelated_colors():
    assert emotion._is_greenish("#3FA050") is True
    assert emotion._is_greenish("#E0A080") is False
    assert emotion._is_skin_tone("#E0A080") is True
    assert emotion._is_skin_tone("#3FA050") is False


# --- 服务入口 --------------------------------------------------------


@pytest.mark.anyio
async def test_analyze_reports_a_successful_result_for_a_valid_image():
    service = emotion.EmotionService()

    results = await service.analyze([image_b64((120, 180, 60))])

    assert len(results) == 1
    result = results[0]
    assert result["status"] == "success"
    assert result["dominant_colors"]
    assert 0 <= result["brightness"] <= 1
    assert result["emotion_hint"]
    assert result["top_categories"]


@pytest.mark.anyio
async def test_analyze_turns_a_broken_image_into_an_error_entry():
    service = emotion.EmotionService()

    results = await service.analyze(["not-base64"])

    assert len(results) == 1
    assert results[0]["status"] == "error"
    assert results[0]["dominant_colors"] == []
    assert results[0]["top_categories"] == []
    assert results[0]["error"]

