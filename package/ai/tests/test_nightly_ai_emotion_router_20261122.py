"""Nightly watch 2026-11-22 · package/ai/app/routers/emotion.py::extract_emotion 盲区。

情绪色彩接口对外只暴露一个入口，但它同时承担「入参校验」「服务异常兜底」
和「逐图结果」三件事，任何一处退化为 500 都会让前端整页失败。

本文件覆盖：
- 路由层：空图片列表 -> 400（error）
- 路由层：服务抛异常 -> 500 且透传原因（error）
- 路由层：正常返回逐图结果（happy）
- 服务层：真实 PNG 可解出主色与亮度（happy）
- 服务层：非法 base64 -> 单条 status=error，不影响其它图片（edge）
"""

import asyncio
import base64
import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.routers import emotion as emotion_router
from app.services.emotion_service import emotion_service

pytestmark = [pytest.mark.smoke]


def _png_bytes(color=(220, 120, 60), size=(40, 30)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def emotion_client():
    app = FastAPI(title="TrailSnap AI - emotion tests")
    app.include_router(emotion_router.router)
    return TestClient(app)


def test_extract_emotion_rejects_an_empty_image_list(emotion_client):
    res = emotion_client.post("/", json={"images": []})
    assert res.status_code == 400
    assert res.json()["detail"] == "No images provided"


def test_extract_emotion_maps_a_service_failure_to_500(emotion_client, monkeypatch):
    class Boom:
        async def analyze(self, images):
            raise RuntimeError("emotion backend down")

    monkeypatch.setattr(emotion_router, "emotion_service", Boom())
    res = emotion_client.post("/", json={"images": ["ZmFrZQ=="]})
    assert res.status_code == 500
    assert "emotion backend down" in res.json()["detail"]


def test_extract_emotion_returns_the_service_results(emotion_client, monkeypatch):
    class Fake:
        async def analyze(self, images):
            return [{"status": "success", "dominant_colors": [], "brightness": 0.5,
                     "saturation": 0.4, "emotion_hint": "warm", "top_categories": ["indoor"]}]

    monkeypatch.setattr(emotion_router, "emotion_service", Fake())
    res = emotion_client.post("/", json={"images": ["ZmFrZQ=="]})
    assert res.status_code == 200
    body = res.json()
    assert body["results"][0]["status"] == "success"
    assert body["results"][0]["emotion_hint"] == "warm"


def test_emotion_service_analyzes_a_real_image():
    encoded = base64.b64encode(_png_bytes()).decode()
    results = asyncio.run(emotion_service.analyze([encoded]))

    assert len(results) == 1
    item = results[0]
    assert item["status"] == "success"
    assert item["dominant_colors"]
    assert item["brightness"] is not None
    assert 0.0 <= item["brightness"] <= 1.0
    assert all(color["hex"].startswith("#") for color in item["dominant_colors"])


def test_emotion_service_reports_a_broken_image_without_aborting_the_batch():
    good = base64.b64encode(_png_bytes()).decode()
    results = asyncio.run(emotion_service.analyze(["not-base64!!", good]))

    assert results[0]["status"] == "error"
    assert results[0]["dominant_colors"] == []
    assert results[0]["error"]
    assert results[1]["status"] == "success"
