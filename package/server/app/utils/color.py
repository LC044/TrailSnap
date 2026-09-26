"""照片色彩提取工具 - 纯 PIL 实现，无需 numpy

只提取主色调、亮度、饱和度、情绪暗示。
top_categories 由分类任务完成后回填，不在此处猜测。
"""

import colorsys
from PIL import Image


CURRENT_COLOR_ANALYSIS_VERSION = 2


def _classify_tones(brightness: float, saturation: float, warm_ratio: float, cool_ratio: float) -> str:
    """Describe visible color properties, without inferring a person's mood."""
    if saturation > 0.5 and brightness > 0.55:
        return 'vibrant'
    if saturation < 0.16 and brightness < 0.35:
        return 'muted'
    if warm_ratio > 0.35:
        return 'warm'
    if cool_ratio > 0.35:
        return 'cool'
    return 'neutral'


def saved_palette_metrics(colors: list) -> tuple[float, float, float, float, float] | None:
    """Return normalized brightness, saturation, warm/cool shares and ratio sum."""
    weighted = []
    for color in colors or []:
        if not isinstance(color, dict):
            continue
        hex_color = color.get('hex')
        ratio = color.get('ratio')
        if not isinstance(hex_color, str) or len(hex_color) != 7 or not isinstance(ratio, (int, float)) or ratio <= 0:
            continue
        try:
            r, g, b = _hex_to_rgb(hex_color)
        except ValueError:
            continue
        weighted.append((colorsys.rgb_to_hsv(r / 255, g / 255, b / 255), ratio))
    total = sum(ratio for _, ratio in weighted)
    if not total:
        return None
    brightness_sum = sum(hsv[2] * ratio for hsv, ratio in weighted)
    saturation_sum = sum(hsv[1] * ratio for hsv, ratio in weighted)
    brightness = brightness_sum / total
    saturation = saturation_sum / total
    warm = sum(ratio for (h, s, _), ratio in weighted if (h < 0.12 or h > 0.88) and s > 0.2) / total
    cool = sum(ratio for (h, s, _), ratio in weighted if 0.45 < h < 0.75 and s > 0.2) / total
    return brightness, saturation, warm, cool, total


def classify_saved_palette(colors: list, saved_brightness: float | None = None, saved_saturation: float | None = None) -> str | None:
    """Reclassify old records whose metrics used unnormalised top-five ratios."""
    metrics = saved_palette_metrics(colors)
    if not metrics:
        return None
    brightness, saturation, warm, cool, total = metrics
    if saved_brightness is not None and saved_saturation is not None:
        if total >= 0.8 or abs(saved_brightness - brightness * total) > 0.01 or abs(saved_saturation - saturation * total) > 0.01:
            return None
    return _classify_tones(brightness, saturation, warm, cool)


def extract_color_info(img: Image.Image, max_size: int = 100) -> dict:
    """
    从图片中提取主色调、亮度、饱和度及情绪暗示。

    不推断场景分类(top_categories)——那是分类任务的事。

    Args:
        img: PIL Image 对象 (RGB)
        max_size: 缩放到此尺寸再分析，提速

    Returns:
        dict with dominant_colors, brightness, saturation, emotion_hint
    """
    if img.mode != 'RGB':
        img = img.convert('RGB')

    # 缩放以加速
    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    pixels = list(img.getdata())

    if not pixels:
        return _empty_result()

    n = len(pixels)

    # --- 1. 量化颜色：将每个通道 0-255 映射到 0-31 (32级)，减少颜色空间 ---
    quantized = {}
    for r, g, b in pixels:
        qr, qg, qb = r >> 3, g >> 3, b >> 3  # 32级
        key = (qr << 10) | (qg << 5) | qb
        if key in quantized:
            quantized[key]['sum_r'] += r
            quantized[key]['sum_g'] += g
            quantized[key]['sum_b'] += b
            quantized[key]['count'] += 1
        else:
            quantized[key] = {'sum_r': r, 'sum_g': g, 'sum_b': b, 'count': 1}

    # --- 2. 取 top-5 颜色簇 ---
    sorted_colors = sorted(quantized.values(), key=lambda x: x['count'], reverse=True)
    top_n = min(5, len(sorted_colors))
    dominant_colors = []

    for i in range(top_n):
        c = sorted_colors[i]
        avg_r = c['sum_r'] // c['count']
        avg_g = c['sum_g'] // c['count']
        avg_b = c['sum_b'] // c['count']
        ratio = round(c['count'] / n, 3)
        dominant_colors.append({
            'hex': _rgb_to_hex(avg_r, avg_g, avg_b),
            'ratio': ratio,
        })

    # --- 3. 从所有颜色簇计算加权亮度和饱和度 ---
    brightness_sum = 0.0
    saturation_sum = 0.0
    warm_ratio = 0.0
    cool_ratio = 0.0

    for c in quantized.values():
        r = c['sum_r'] / c['count']
        g = c['sum_g'] / c['count']
        b = c['sum_b'] / c['count']
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        ratio = c['count'] / n
        brightness_sum += v * ratio
        saturation_sum += s * ratio
        # 暖色：红/橙/黄 (h < 0.12 or h > 0.88) 且饱和度 > 0.2
        if (h < 0.12 or h > 0.88) and s > 0.2:
            warm_ratio += ratio
        if 0.45 < h < 0.75 and s > 0.2:
            cool_ratio += ratio

    avg_brightness = round(brightness_sum, 3)
    avg_saturation = round(saturation_sum, 3)

    # --- 4. 情绪分类（纯基于色彩属性，不依赖场景分类）---
    emotion_hint = _classify_tones(avg_brightness, avg_saturation, warm_ratio, cool_ratio)

    return {
        'dominant_colors': dominant_colors,
        'brightness': avg_brightness,
        'saturation': avg_saturation,
        'emotion_hint': emotion_hint,
        # top_categories 不在此处设置，由分类任务完成后回填
    }


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f'#{r:02X}{g:02X}{b:02X}'


def _hex_to_rgb(hex_color: str) -> tuple:
    return int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)


def _empty_result() -> dict:
    return {
        'dominant_colors': [],
        'brightness': None,
        'saturation': None,
        'emotion_hint': None,
    }
