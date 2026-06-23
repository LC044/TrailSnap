"""照片色彩提取工具 - 纯 PIL 实现，无需 numpy

只提取主色调、亮度、饱和度、情绪暗示。
top_categories 由分类任务完成后回填，不在此处猜测。
"""

import colorsys
from PIL import Image


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

    # --- 3. 计算加权亮度和饱和度 ---
    brightness_sum = 0.0
    saturation_sum = 0.0
    weighted_hue = 0.0
    warm_ratio = 0.0

    for c in dominant_colors:
        r, g, b = _hex_to_rgb(c['hex'])
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        brightness_sum += v * c['ratio']
        saturation_sum += s * c['ratio']
        weighted_hue += h * c['ratio']
        # 暖色：红/橙/黄 (h < 0.12 or h > 0.88) 且饱和度 > 0.2
        if (h < 0.12 or h > 0.88) and s > 0.2:
            warm_ratio += c['ratio']

    avg_brightness = round(brightness_sum, 3)
    avg_saturation = round(saturation_sum, 3)

    # --- 4. 情绪分类（纯基于色彩属性，不依赖场景分类）---
    is_high_sat = avg_saturation > 0.5
    is_bright = avg_brightness > 0.55

    if is_high_sat and is_bright:
        emotion_hint = 'vibrant'
    elif not is_high_sat and not is_bright:
        emotion_hint = 'muted'
    elif warm_ratio > 0.5:
        emotion_hint = 'warm'
    elif 0.45 < weighted_hue < 0.75:
        emotion_hint = 'cool'
    else:
        emotion_hint = 'neutral'

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
