"""Nightly watch 2026-10-29 · 覆盖盲区补测（app/service/moment/day_caption_service.py）。

被测模块：app/service/moment/day_caption_service.py 的朋友圈文案生成上下文与流式输出。
覆盖点（相对 2026-10-29-r2 的覆盖率基线，此前完全未触达）：
- _prepare_context：scope 不支持时 ValueError；命中缓存直接返回缓存文案；
  当天没有照片时 ValueError；正常路径组装出 materials（含 _photo_count /
  _connection / _model_name / _system_prompt / _user_prompt）。
- generate_caption_stream：_prepare_context 抛 ValueError 时输出 error 事件并结束；
  抛其它异常时输出「内部错误」事件并结束；命中缓存时输出 cached 事件；
  正常流式输出 content / reasoning / 收尾缓冲。
- _fetch_clustered_photo_ids：只返回当天有向量记录的照片 ID。

LLM 与连接解析全部 mock，不发起真实网络请求。
"""

import asyncio
import json
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.service.moment import day_caption_service as caption_service

pytestmark = [pytest.mark.smoke, pytest.mark.module_moment]

DAY = date(2022, 3, 4)


def _photo(owner_id, when):
    from app.db.models.photo import Photo, FileType
    return Photo(id=uuid4(), owner_id=owner_id, filename="a.jpg", file_path="a.jpg",
                 file_type=FileType.image, photo_time=when, is_deleted=False)


# ---------------------------------------------------------------------------
# _prepare_context
# ---------------------------------------------------------------------------


def test_prepare_context_rejects_unsupported_scope():
    with pytest.raises(ValueError, match="目前只支持全部照片视图"):
        caption_service._prepare_context(uuid4(), MagicMock(), DAY, "Asia/Shanghai",
                                         "album", None, None, None, None, False)


def test_prepare_context_returns_cached_caption():
    existing = SimpleNamespace(caption="昨天写好的文案")
    with patch.object(caption_service.moment_crud, "get_caption", return_value=existing), \
         patch.object(caption_service, "_fetch_day_photos") as fetch:
        cached, materials = caption_service._prepare_context(
            uuid4(), MagicMock(), DAY, "Asia/Shanghai", "all", None, None, None, None, False)
    assert cached == "昨天写好的文案"
    assert materials == {}
    fetch.assert_not_called()


def test_prepare_context_rejects_day_without_photos():
    with patch.object(caption_service.moment_crud, "get_caption", return_value=None), \
         patch.object(caption_service, "_fetch_day_photos", return_value=[]):
        with pytest.raises(ValueError, match="这一天没有照片"):
            caption_service._prepare_context(uuid4(), MagicMock(), DAY, "Asia/Shanghai",
                                             "all", None, None, None, None, False)


def test_prepare_context_builds_materials():
    owner_id = uuid4()
    photos = [_photo(owner_id, datetime(2022, 3, 4, 10, 0))]
    connection = SimpleNamespace(id="conn-1")
    with patch.object(caption_service.moment_crud, "get_caption", return_value=None), \
         patch.object(caption_service, "_fetch_day_photos", return_value=photos), \
         patch.object(caption_service, "_dedup_similar_photos", return_value=(photos, 1)), \
         patch.object(caption_service, "_build_materials", return_value={"counts": {"image": 1, "video": 0}}), \
         patch.object(caption_service, "_resolve_connection_and_model",
                      return_value=(connection, "gpt-test", "system-prompt")), \
         patch.object(caption_service, "_format_materials_for_prompt", return_value="user-prompt"):
        cached, materials = caption_service._prepare_context(
            owner_id, MagicMock(), DAY, "Asia/Shanghai", "all", None, "简约", None, None, False)
    assert cached is None
    assert materials["_photo_count"] == 1
    assert materials["_connection"] is connection
    assert materials["_model_name"] == "gpt-test"
    assert materials["_system_prompt"] == "system-prompt"
    assert materials["_user_prompt"] == "user-prompt"


# ---------------------------------------------------------------------------
# generate_caption_stream
# ---------------------------------------------------------------------------


async def _collect(stream):
    return [item async for item in stream]


@pytest.mark.asyncio
async def test_stream_reports_value_error_from_prepare_context():
    with patch.object(caption_service, "_prepare_context", side_effect=ValueError("这一天没有照片，无法生成文案。")):
        events = await _collect(caption_service.generate_caption_stream(
            uuid4(), MagicMock(), DAY, "Asia/Shanghai"))
    payloads = [json.loads(item[len("data: "):]) for item in events if item.startswith("data: {")]
    assert payloads[0]["error"] == "这一天没有照片，无法生成文案。"
    assert events[-1].strip() == "data: [DONE]"


@pytest.mark.asyncio
async def test_stream_reports_internal_error_from_prepare_context():
    with patch.object(caption_service, "_prepare_context", side_effect=RuntimeError("db down")):
        events = await _collect(caption_service.generate_caption_stream(
            uuid4(), MagicMock(), DAY, "Asia/Shanghai"))
    payloads = [json.loads(item[len("data: "):]) for item in events if item.startswith("data: {")]
    assert "内部错误" in payloads[0]["error"]
    assert events[-1].strip() == "data: [DONE]"


@pytest.mark.asyncio
async def test_stream_returns_cached_caption():
    with patch.object(caption_service, "_prepare_context", return_value=("缓存文案", {})):
        events = await _collect(caption_service.generate_caption_stream(
            uuid4(), MagicMock(), DAY, "Asia/Shanghai"))
    payloads = [json.loads(item[len("data: "):]) for item in events if item.startswith("data: {")]
    assert payloads[0] == {"content": "缓存文案", "cached": True}
    assert events[-1].strip() == "data: [DONE]"


class _FakeLLM:
    def __init__(self, chunks):
        self._chunks = chunks

    async def astream(self, messages):
        for chunk in self._chunks:
            yield chunk


@pytest.mark.asyncio
async def test_stream_emits_content_reasoning_and_tail():
    materials = {"_connection": SimpleNamespace(), "_model_name": "m",
                 "_system_prompt": "sys", "_user_prompt": "usr"}
    chunks = [
        SimpleNamespace(content="正文", additional_kwargs={}),
        SimpleNamespace(content="", additional_kwargs={"summary": [{"text": "思考"}]}),
        SimpleNamespace(content=[{"type": "text", "text": "更多"}], additional_kwargs={}),
        SimpleNamespace(content=[{"type": "reasoning", "summary": [{"text": "推理"}]}], additional_kwargs={}),
    ]
    llm = _FakeLLM(chunks)
    with patch.object(caption_service, "_prepare_context", return_value=(None, materials)), \
         patch.object(caption_service, "_build_llm", return_value=llm), \
         patch.object(caption_service.moment_crud, "upsert_caption",
                      return_value=SimpleNamespace(caption="正文更多", source="ai",
                                                   updated_at=datetime(2022, 3, 4))), \
         patch.object(caption_service, "_strip_think_blocks", side_effect=lambda text: text):
        events = await _collect(caption_service.generate_caption_stream(
            uuid4(), MagicMock(), DAY, "Asia/Shanghai"))
    payloads = [json.loads(item[len("data: "):]) for item in events if item.startswith("data: {")]
    contents = [p["content"] for p in payloads if "content" in p]
    reasonings = [p["reasoning"] for p in payloads if "reasoning" in p]
    assert "正文" in contents
    assert "更多" in contents
    assert "思考" in reasonings
    assert "推理" in reasonings


# ---------------------------------------------------------------------------
# _fetch_clustered_photo_ids
# ---------------------------------------------------------------------------


def test_fetch_clustered_photo_ids_returns_only_vectorized_photos(face_sqlite_session):
    from app.db.models.image_vector import ImageVector
    from app.db.models.photo import Photo, FileType
    from app.db.models.user import User

    db = face_sqlite_session
    owner = User(id=uuid4(), username="vector-owner", hashed_password="x", is_active=True)
    db.add(owner)
    db.commit()
    with_vector = Photo(id=uuid4(), owner_id=owner.id, filename="v.jpg", file_path="v.jpg",
                        file_type=FileType.image, photo_time=datetime(2022, 3, 4, 9, 0), is_deleted=False)
    without_vector = Photo(id=uuid4(), owner_id=owner.id, filename="n.jpg", file_path="n.jpg",
                            file_type=FileType.image, photo_time=datetime(2022, 3, 4, 10, 0), is_deleted=False)
    other_day = Photo(id=uuid4(), owner_id=owner.id, filename="o.jpg", file_path="o.jpg",
                      file_type=FileType.image, photo_time=datetime(2022, 3, 5, 10, 0), is_deleted=False)
    db.add_all([with_vector, without_vector, other_day])
    db.flush()
    db.add(ImageVector(photo_id=with_vector.id, embedding=[0.1] * 512))
    db.add(ImageVector(photo_id=other_day.id, embedding=[0.3] * 512))
    db.commit()

    ids = caption_service._fetch_clustered_photo_ids(db, owner.id, DAY)
    assert ids == {with_vector.id}
