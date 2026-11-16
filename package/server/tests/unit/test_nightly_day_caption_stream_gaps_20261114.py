# -*- coding: utf-8 -*-
"""Nightly watch 2026-11-14 round2 · 覆盖盲区补测（app/service/moment/day_caption_service.py）。

相对 2026-11-13 覆盖率基线，此前完全未触达或仅部分触达的分支：
- _fetch_day_photos：按 naive [day 00:00, day+1 00:00) 边界筛选当天照片。
- _resolve_tz：模块级 ZoneInfo 不可用（Python < 3.9）时回退 UTC。
- _ThinkStripper.feed：思考态缓冲超过 4 倍闭合标签长度时只保留末尾窗口。
- _build_materials：地点去重后达到 5 条即停止扫描。
- generate_caption_stream：
  * list content 中非 dict 元素被跳过；
  * LLM 没有产出任何正文时的空文案报错；
  * LLM 抛异常时的失败事件；
  * 思考通道 summary 为空 dict / 空文本时不产出 reasoning 帧。
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.db.models.photo import FileType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.user import User
from app.service.moment import day_caption_service as caption_service

pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]

DAY = date(2024, 5, 20)


async def _collect(agen):
    return [chunk async for chunk in agen]


def _payloads(events):
    return [json.loads(item[len("data: "):]) for item in events if item.startswith("data: {")]


class _FakeLLM:
    def __init__(self, chunks):
        self._chunks = chunks

    async def astream(self, messages):
        for chunk in self._chunks:
            yield chunk


class _BoomLLM:
    async def astream(self, messages):
        raise RuntimeError("llm exploded")
        yield  # pragma: no cover - generator marker


# --------------------------------------------------------------------------- #
# _fetch_day_photos
# --------------------------------------------------------------------------- #


def test_fetch_day_photos_only_returns_the_requested_day(face_sqlite_session):
    db = face_sqlite_session
    owner = User(id=uuid4(), username="caption-day-owner", hashed_password="x", is_active=True)
    db.add(owner)
    db.flush()

    same_day = Photo(id=uuid4(), owner_id=owner.id, filename="a.jpg", file_path="a.jpg",
                     file_type=FileType.image, photo_time=datetime(2024, 5, 20, 9, 0), is_deleted=False)
    late_day = Photo(id=uuid4(), owner_id=owner.id, filename="b.jpg", file_path="b.jpg",
                     file_type=FileType.image, photo_time=datetime(2024, 5, 20, 23, 59, 59), is_deleted=False)
    next_day = Photo(id=uuid4(), owner_id=owner.id, filename="c.jpg", file_path="c.jpg",
                     file_type=FileType.image, photo_time=datetime(2024, 5, 21, 0, 0), is_deleted=False)
    no_time = Photo(id=uuid4(), owner_id=owner.id, filename="d.jpg", file_path="d.jpg",
                    file_type=FileType.image, photo_time=None, is_deleted=False)
    deleted = Photo(id=uuid4(), owner_id=owner.id, filename="e.jpg", file_path="e.jpg",
                    file_type=FileType.image, photo_time=datetime(2024, 5, 20, 10, 0), is_deleted=True)
    db.add_all([same_day, late_day, next_day, no_time, deleted])
    db.commit()

    photos = caption_service._fetch_day_photos(db, owner.id, DAY, "Asia/Shanghai")

    assert {p.id for p in photos} == {same_day.id, late_day.id}


# --------------------------------------------------------------------------- #
# _resolve_tz
# --------------------------------------------------------------------------- #


def test_resolve_tz_falls_back_to_utc_when_zoneinfo_is_unavailable(monkeypatch):
    monkeypatch.setattr(caption_service, "ZoneInfo", None)
    assert caption_service._resolve_tz("Asia/Shanghai") is caption_service._tz.utc


def test_resolve_tz_falls_back_to_utc_for_an_unknown_zone():
    assert caption_service._resolve_tz("Not/AZone") is caption_service._tz.utc


# --------------------------------------------------------------------------- #
# _ThinkStripper
# --------------------------------------------------------------------------- #


def test_think_stripper_keeps_only_the_tail_of_an_overlong_think_buffer():
    stripper = caption_service._ThinkStripper()
    assert stripper.feed("<think>" + "x" * 200) == ""
    # 缓冲被裁剪到只剩闭合标签长度的窗口，后续闭合标签仍能命中
    stripper.feed("</think>")
    assert stripper.flush() == ""


# --------------------------------------------------------------------------- #
# _build_materials
# --------------------------------------------------------------------------- #


def test_build_materials_stops_collecting_locations_after_five_entries(face_sqlite_session):
    db = face_sqlite_session
    owner = User(id=uuid4(), username="caption-loc-owner", hashed_password="x", is_active=True)
    db.add(owner)
    db.flush()

    photos = []
    for index in range(7):
        photo = Photo(id=uuid4(), owner_id=owner.id, filename=f"p{index}.jpg", file_path=f"p{index}.jpg",
                      file_type=FileType.image, photo_time=datetime(2024, 5, 20, 8, index), is_deleted=False)
        db.add(photo)
        photos.append(photo)
    db.flush()

    for index, photo in enumerate(photos):
        db.add(PhotoMetadata(photo_id=photo.id, city=f"城市{index}"))
    db.commit()

    materials = caption_service._build_materials(db, photos)

    assert len(materials["locations"]) == 5
    assert all(item.startswith("城市") for item in materials["locations"])


# --------------------------------------------------------------------------- #
# generate_caption_stream
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_stream_skips_content_items_that_are_not_dicts():
    materials = {"_connection": SimpleNamespace(), "_model_name": "m",
                 "_system_prompt": "sys", "_user_prompt": "usr"}
    chunks = [
        SimpleNamespace(content=["非字典", {"type": "text", "text": "正文"}], additional_kwargs={}),
    ]
    with patch.object(caption_service, "_prepare_context", return_value=(None, materials)), \
         patch.object(caption_service, "_build_llm", return_value=_FakeLLM(chunks)), \
         patch.object(caption_service.moment_crud, "upsert_caption",
                      return_value=SimpleNamespace(caption="正文", source="ai",
                                                   updated_at=datetime(2024, 5, 20))), \
         patch.object(caption_service, "_strip_think_blocks", side_effect=lambda text: text):
        events = await _collect(caption_service.generate_caption_stream(
            uuid4(), MagicMock(), DAY, "Asia/Shanghai"))
    payloads = _payloads(events)
    assert [p["content"] for p in payloads if "content" in p] == ["正文"]
    assert events[-1].strip() == "data: [DONE]"


@pytest.mark.asyncio
async def test_stream_reports_an_error_when_the_model_returns_nothing():
    materials = {"_connection": SimpleNamespace(), "_model_name": "m",
                 "_system_prompt": "sys", "_user_prompt": "usr"}
    with patch.object(caption_service, "_prepare_context", return_value=(None, materials)), \
         patch.object(caption_service, "_build_llm", return_value=_FakeLLM([])), \
         patch.object(caption_service, "_strip_think_blocks", side_effect=lambda text: text):
        events = await _collect(caption_service.generate_caption_stream(
            uuid4(), MagicMock(), DAY, "Asia/Shanghai"))
    payloads = _payloads(events)
    assert payloads[0]["error"] == "LLM 返回为空，请稍后重试。"
    assert events[-1].strip() == "data: [DONE]"


@pytest.mark.asyncio
async def test_stream_reports_a_failure_when_the_model_raises():
    materials = {"_connection": SimpleNamespace(), "_model_name": "m",
                 "_system_prompt": "sys", "_user_prompt": "usr"}
    with patch.object(caption_service, "_prepare_context", return_value=(None, materials)), \
         patch.object(caption_service, "_build_llm", return_value=_BoomLLM()):
        events = await _collect(caption_service.generate_caption_stream(
            uuid4(), MagicMock(), DAY, "Asia/Shanghai"))
    payloads = _payloads(events)
    assert "生成失败" in payloads[0]["error"]
    assert "llm exploded" in payloads[0]["error"]
    assert events[-1].strip() == "data: [DONE]"


@pytest.mark.asyncio
async def test_stream_ignores_reasoning_summaries_without_text():
    materials = {"_connection": SimpleNamespace(), "_model_name": "m",
                 "_system_prompt": "sys", "_user_prompt": "usr"}
    chunks = [
        SimpleNamespace(content="", additional_kwargs={"summary": [{}, "字符串", {"text": ""}]}),
        SimpleNamespace(content=[{"type": "reasoning", "summary": [{"text": ""}]}], additional_kwargs={}),
    ]
    with patch.object(caption_service, "_prepare_context", return_value=(None, materials)), \
         patch.object(caption_service, "_build_llm", return_value=_FakeLLM(chunks)), \
         patch.object(caption_service, "_strip_think_blocks", side_effect=lambda text: text):
        events = await _collect(caption_service.generate_caption_stream(
            uuid4(), MagicMock(), DAY, "Asia/Shanghai"))
    payloads = _payloads(events)
    assert not [p for p in payloads if "reasoning" in p]

# --------------------------------------------------------------------------- #
# 追加：残留正文补发 / 取消传播
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_stream_flushes_the_leftover_text_buffer():
    materials = {"_connection": SimpleNamespace(), "_model_name": "m",
                 "_system_prompt": "sys", "_user_prompt": "usr"}
    chunks = [SimpleNamespace(content="<", additional_kwargs={})]
    with patch.object(caption_service, "_prepare_context", return_value=(None, materials)), \
         patch.object(caption_service, "_build_llm", return_value=_FakeLLM(chunks)), \
         patch.object(caption_service.moment_crud, "upsert_caption",
                      return_value=SimpleNamespace(caption="<", source="ai",
                                                   updated_at=datetime(2024, 5, 20))), \
         patch.object(caption_service, "_strip_think_blocks", side_effect=lambda text: text):
        events = await _collect(caption_service.generate_caption_stream(
            uuid4(), MagicMock(), DAY, "Asia/Shanghai"))
    payloads = _payloads(events)
    assert any(p.get("content") == "<" for p in payloads)


@pytest.mark.asyncio
async def test_stream_propagates_a_cancellation():
    materials = {"_connection": SimpleNamespace(), "_model_name": "m",
                 "_system_prompt": "sys", "_user_prompt": "usr"}

    class _CancelledLLM:
        async def astream(self, messages):
            raise asyncio.CancelledError()
            yield  # pragma: no cover - generator marker

    with patch.object(caption_service, "_prepare_context", return_value=(None, materials)), \
         patch.object(caption_service, "_build_llm", return_value=_CancelledLLM()):
        with pytest.raises(asyncio.CancelledError):
            await _collect(caption_service.generate_caption_stream(
                uuid4(), MagicMock(), DAY, "Asia/Shanghai"))
