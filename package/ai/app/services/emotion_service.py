"""情绪色彩提取服务 - 使用 PIL/numpy 从缩略图提取主色调、亮度、饱和度及情绪暗示"""

import logging
import base64
import io
import colorsys
from typing import List, Dict, Any

import numpy as np
from PIL import Image

logger = logging.getLogger("app.services.emotion_service")


def _kmeans_colors(pixels: np.ndarray, k: int = 5, max_iter: int = 20) -> tuple:
    """Simple K-Means clustering on pixel colors. Returns (centers, labels)."""
    n = len(pixels)
    if n == 0:
        return np.array([]), np.array([])

    # Initialize centers using k-means++ style
    centers = np.empty((k, 3), dtype=np.float32)
    centers[0] = pixels[np.random.randint(n)]
    for i in range(1, k):
        dists = np.min(np.sum((pixels[:, None] - centers[None, :i]) ** 2, axis=2), axis=1)
        probs = dists / (dists.sum() + 1e-10)
        centers[i] = pixels[np.random.choice(n, p=probs)]

    labels = np.zeros(n, dtype=np.int32)
    for _ in range(max_iter):
        # Assign labels
        dists = np.sum((pixels[:, None] - centers[None]) ** 2, axis=2)
        new_labels = np.argmin(dists, axis=1)
        if np.array_equal(labels, new_labels):
            break
        labels = new_labels
        # Update centers
        for i in range(k):
            mask = labels == i
            if mask.any():
                centers[i] = pixels[mask].mean(axis=0)

    return centers, labels


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02X}{g:02X}{b:02X}"


def _classify_emotion(hue: float, saturation: float, brightness: float, warm_ratio: float) -> str:
    """Classify the overall emotion based on color properties."""
    # hue is 0-1
    # Warm hues: red(0-0.1), orange(0.05-0.12), yellow(0.12-0.2)
    # Cool hues: blue(0.55-0.7), green-blue(0.45-0.55)

    is_high_sat = saturation > 0.5
    is_bright = brightness > 0.55

    if is_high_sat and is_bright:
        return "vibrant"
    if not is_high_sat and not is_bright:
        return "muted"
    if warm_ratio > 0.5:
        return "warm"
    if hue > 0.45 and hue < 0.75:
        return "cool"
    return "neutral"


def _infer_categories_from_color(dominant_colors: List[Dict], brightness: float, saturation: float) -> List[str]:
    """Infer scene categories from color signals."""
    categories = []

    # Check for green tones (nature/outdoor)
    green_score = sum(
        c["ratio"] for c in dominant_colors
        if _is_greenish(c["hex"])
    )
    if green_score > 0.25:
        categories.append("户外")

    # Check for warm skin-tone colors (portrait)
    warm_score = sum(
        c["ratio"] for c in dominant_colors
        if _is_skin_tone(c["hex"])
    )
    if warm_score > 0.3:
        categories.append("人像")

    # Dark + cool = night
    if brightness < 0.35:
        categories.append("夜景")

    # Low saturation + moderate brightness = indoor
    if saturation < 0.25 and 0.3 < brightness < 0.6:
        categories.append("室内")

    if not categories:
        categories.append("日常")

    return categories


def _is_greenish(hex_color: str) -> bool:
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return 0.2 < h < 0.45 and s > 0.2


def _is_skin_tone(hex_color: str) -> bool:
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return 0.02 < h < 0.12 and 0.2 < s < 0.7 and 0.4 < v < 0.9


class EmotionService:
    """Service for extracting emotion-related color features from images."""

    def __init__(self):
        self._initialized = False

    def _ensure_init(self):
        if not self._initialized:
            self._initialized = True

    async def analyze(self, base64_images: List[str]) -> List[Dict[str, Any]]:
        """Analyze a batch of base64-encoded images for emotion color features."""
        self._ensure_init()
        results = []

        for img_b64 in base64_images:
            try:
                result = self._analyze_single(img_b64)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to analyze image: {e}")
                results.append({
                    "status": "error",
                    "dominant_colors": [],
                    "brightness": None,
                    "saturation": None,
                    "emotion_hint": None,
                    "top_categories": [],
                    "error": str(e),
                })

        return results

    def _analyze_single(self, img_b64: str) -> Dict[str, Any]:
        """Analyze a single image."""
        # Decode base64
        img_data = base64.b64decode(img_b64)
        img = Image.open(io.BytesIO(img_data)).convert("RGB")

        # Resize to thumbnail for speed (max 150px on longest side)
        max_size = 150
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

        pixels = np.array(img, dtype=np.float32).reshape(-1, 3)

        # Sample pixels for speed if image is very large
        if len(pixels) > 10000:
            indices = np.random.choice(len(pixels), 10000, replace=False)
            pixels = pixels[indices]

        # K-Means for dominant colors
        k = min(5, len(pixels))
        centers, labels = _kmeans_colors(pixels, k=k)

        # Calculate ratios
        total = len(labels)
        dominant_colors = []
        for i in range(k):
            mask = labels == i
            ratio = mask.sum() / total
            r, g, b = int(centers[i][0]), int(centers[i][1]), int(centers[i][2])
            r = max(0, min(255, r))
            g = max(0, min(255, g))
            b = max(0, min(255, b))
            dominant_colors.append({
                "hex": _rgb_to_hex(r, g, b),
                "ratio": round(ratio, 3),
            })

        # Sort by ratio descending
        dominant_colors.sort(key=lambda x: x["ratio"], reverse=True)

        # Compute overall brightness and saturation (weighted by cluster ratio)
        avg_brightness = 0.0
        avg_saturation = 0.0
        weighted_hue = 0.0
        warm_ratio = 0.0

        for c in dominant_colors:
            r, g, b = int(c["hex"][1:3], 16), int(c["hex"][3:5], 16), int(c["hex"][5:7], 16)
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            avg_brightness += v * c["ratio"]
            avg_saturation += s * c["ratio"]
            weighted_hue += h * c["ratio"]
            # Warm hues: 0-0.12 (red/orange/yellow) and 0.88-1.0 (red)
            if (h < 0.12 or h > 0.88) and s > 0.2:
                warm_ratio += c["ratio"]

        avg_brightness = round(avg_brightness, 3)
        avg_saturation = round(avg_saturation, 3)

        # Classify emotion
        emotion_hint = _classify_emotion(weighted_hue, avg_saturation, avg_brightness, warm_ratio)

        # Infer categories from color signals
        top_categories = _infer_categories_from_color(dominant_colors, avg_brightness, avg_saturation)

        return {
            "status": "success",
            "dominant_colors": dominant_colors,
            "brightness": avg_brightness,
            "saturation": avg_saturation,
            "emotion_hint": emotion_hint,
            "top_categories": top_categories,
        }


emotion_service = EmotionService()
