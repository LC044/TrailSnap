"""Nightly watch 2026-11-12 · app/service/chapter_diary.py 与 app/service/tasks/panorama.py 盲区补测。

被测模块：
- app/service/chapter_diary.py：章节状态不允许生成日记（400）、AI 返回非法 JSON（502）。
- app/service/tasks/panorama.py：照片缺失或不是图片时跳过（skipped）。

依赖均以 MagicMock / patch 打桩，不触网、不连 DB。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.service import chapter_diary
from app.service.tasks import panorama as panorama_task
from app.db.models.photo import FileType

pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


def _request(scope="introduction", version=1):
    from app.schemas.chapter import ChapterDiaryGenerate
    return ChapterDiaryGenerate(scope=scope, version=version)


@pytest.mark.asyncio
async def test_generate_rejects_chapter_not_confirmed():
    db = MagicMock()
    row = SimpleNamespace(status="draft", version=1)
    with patch.object(chapter_diary.chapter, "_owned", return_value=row):
        with pytest.raises(HTTPException) as excinfo:
            await chapter_diary.generate(db, uuid4(), uuid4(), _request())
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "当前章节不能生成日记"


@pytest.mark.asyncio
async def test_generate_wraps_invalid_ai_output_into_502():
    db = MagicMock()
    row = SimpleNamespace(status="confirmed", version=1)
    llm = SimpleNamespace(ainvoke=MagicMock())
    response = SimpleNamespace(content="not-json")

    async def _ainvoke(messages):
        return response

    llm.ainvoke = _ainvoke
    with patch.object(chapter_diary.chapter, "_owned", return_value=row), \
         patch.object(chapter_diary, "collect_facts", return_value={}), \
         patch.object(chapter_diary, "configured_model", return_value=llm):
        with pytest.raises(HTTPException) as excinfo:
            await chapter_diary.generate(db, uuid4(), uuid4(), _request())
    assert excinfo.value.status_code == 502
    assert "格式不完整" in excinfo.value.detail


@pytest.mark.asyncio
async def test_generate_wraps_ai_failure_into_502():
    db = MagicMock()
    row = SimpleNamespace(status="confirmed", version=1)
    llm = SimpleNamespace()

    async def _ainvoke(messages):
        raise RuntimeError("boom")

    llm.ainvoke = _ainvoke
    with patch.object(chapter_diary.chapter, "_owned", return_value=row), \
         patch.object(chapter_diary, "collect_facts", return_value={}), \
         patch.object(chapter_diary, "configured_model", return_value=llm):
        with pytest.raises(HTTPException) as excinfo:
            await chapter_diary.generate(db, uuid4(), uuid4(), _request())
    assert excinfo.value.status_code == 502
    assert "暂时生成失败" in excinfo.value.detail


@pytest.mark.asyncio
async def test_panorama_strategy_skips_non_image_photo():
    db = MagicMock()
    photo = SimpleNamespace(file_type=FileType.video)
    db.query.return_value.filter.return_value.first.return_value = photo
    task = SimpleNamespace(photo_id=str(uuid4()), owner_id=str(uuid4()))
    result = await panorama_task.ScanPanoramaStrategy().process(MagicMock(), task, db)
    assert result == {"skipped": True}


@pytest.mark.asyncio
async def test_panorama_strategy_skips_missing_photo():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    task = SimpleNamespace(photo_id=str(uuid4()), owner_id=str(uuid4()))
    result = await panorama_task.ScanPanoramaStrategy().process(MagicMock(), task, db)
    assert result == {"skipped": True}
