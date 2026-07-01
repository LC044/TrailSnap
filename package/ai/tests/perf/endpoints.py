"""各 AI 接口的压测配置。

每条配置描述：接口标识、展示名、HTTP 路径、载荷类型。
- payload_kind="images"：请求体 {"images": [base64, ...]}，每请求取 K 张图。
- payload_kind="texts" ：请求体 {"texts": [str, ...]}，每请求取 K 条文本（embedding/text 专用）。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Endpoint:
    key: str            # 唯一标识，用于 --interface / 脚本名
    name: str           # 中文展示名
    path: str           # HTTP 路径（相对 base_url）
    payload_kind: str   # "images" 或 "texts"


# 注意：路径需与 app/main.py 中 include_router 的 prefix + 路由内 path 保持一致。
ENDPOINTS: list[Endpoint] = [
    Endpoint("face",          "人脸识别",       "/face/face-recognition", "images"),
    Endpoint("ocr",           "OCR 文字识别",   "/ocr/predict",            "images"),
    Endpoint("classification","图像分类",       "/classification/",        "images"),
    Endpoint("embedding-image","图像向量(CLIP)", "/embedding/image",       "images"),
    Endpoint("embedding-text", "文本向量(CLIP)", "/embedding/text",        "texts"),
    Endpoint("tickets",       "车票识别",       "/tickets/predict",        "images"),
    Endpoint("emotion",       "情绪色彩提取",   "/emotion/",               "images"),
]

_BY_KEY = {e.key: e for e in ENDPOINTS}


def get_endpoint(key: str) -> Endpoint:
    if key not in _BY_KEY:
        raise ValueError(f"未知接口: {key}，可选: {list(_BY_KEY)}")
    return _BY_KEY[key]


# embedding-text 用的样本文本（每请求从中循环取 K 条）。
SAMPLE_TEXTS: list[str] = [
    "一只橘色的猫趴在窗台上晒太阳",
    "夕阳下的海面与远处的帆船",
    "雪山脚下的湖泊倒影",
    "城市夜景中的霓虹灯街道",
    "森林里的小鹿在吃草",
    "生日蛋糕上的蜡烛",
    "高铁车窗外的田园风光",
    "海边沙滩上的脚印",
]
