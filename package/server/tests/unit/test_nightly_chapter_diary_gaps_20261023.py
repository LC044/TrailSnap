"""Unit tests for the uncovered branches of ``app/service/chapter_diary.py``.

The 2026-10-23 coverage scan showed ``app/service/chapter_diary.py`` at ~85%
(14 missed statements). The missed lines are all *guard rails*:

* ``collect_facts`` -- the ``scope="year"`` date clamping and its two 400s
  (the requested year is outside the chapter window / the window has no
  photos and the user wrote no notes);
* ``configured_model`` -- the "no usable chat model configured" 400 and the
  lazily-imported client construction.

The LLM call itself is never made here: the model client is stubbed, so the
tests stay hermetic (no DB, no network, no API key).
"""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.schemas.chapter import ChapterDiaryGenerate
from app.service import chapter_diary


pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


def _chapter_row(start: date, end: date | None = None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        title="2024 春天",
        start_date=start,
        end_date=end,
    )


def _request(**kwargs) -> ChapterDiaryGenerate:
    payload = {"version": 1, "notes": "", **kwargs}
    return ChapterDiaryGenerate(**payload)


@pytest.fixture
def stub_chapter(monkeypatch):
    """Stub the ``app.service.chapter`` helpers used by ``collect_facts``."""
    from app.service import chapter as chapter_module

    state = SimpleNamespace(samples=[], places_value=[], photo_count=3)
    monkeypatch.setattr(chapter_module, "representative_photos", lambda db, row: state.samples)
    monkeypatch.setattr(chapter_module, "places", lambda db, row: state.places_value)

    def _photo_query(db, owner_id, start, end):
        query = MagicMock()
        query.count.return_value = state.photo_count
        return query

    monkeypatch.setattr(chapter_module, "_photo_query", _photo_query)
    monkeypatch.setattr(chapter_module, "_events_query", lambda db, row, year=None: MagicMock())
    return state


@pytest.fixture
def fake_db():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    return db


def test_collect_facts_clamps_year_scope_to_requested_year(stub_chapter, fake_db):
    """scope=year 时，事实窗口收敛到请求年份与章节窗口的交集。"""
    row = _chapter_row(date(2020, 1, 1), date(2026, 12, 31))
    stub_chapter.samples = []

    facts = chapter_diary.collect_facts(
        fake_db, row, _request(scope="year", year=2024, notes="记得一次春游")
    )

    assert facts["start_date"] == "2024-01-01"
    assert facts["end_date"] == "2024-12-31"
    assert facts["chapter_title"] == row.title
    assert facts["user_notes"] == "记得一次春游"


def test_collect_facts_rejects_year_outside_chapter_window(stub_chapter, fake_db):
    """请求年份完全落在章节窗口之外时直接 400。"""
    row = _chapter_row(date(2020, 1, 1), date(2020, 12, 31))

    with pytest.raises(HTTPException) as excinfo:
        chapter_diary.collect_facts(
            fake_db, row, _request(scope="year", year=2024, notes="记得一次春游")
        )

    assert excinfo.value.status_code == 400
    assert "这一年不在章节时间范围内" in excinfo.value.detail


def test_collect_facts_requires_photos_or_notes(stub_chapter, fake_db):
    """既没有影像也没有用户补充时 400，提示先写下记忆。"""
    row = _chapter_row(date(2020, 1, 1), date(2020, 12, 31))
    stub_chapter.samples = []

    with pytest.raises(HTTPException) as excinfo:
        chapter_diary.collect_facts(fake_db, row, _request(scope="introduction"))

    assert excinfo.value.status_code == 400
    assert "暂无影像" in excinfo.value.detail


def test_collect_facts_uses_notes_when_there_are_no_photos(stub_chapter, fake_db):
    """没有影像但用户写了补充时仍可生成事实包。"""
    row = _chapter_row(date(2020, 1, 1), date(2020, 12, 31))
    stub_chapter.samples = []

    facts = chapter_diary.collect_facts(fake_db, row, _request(notes="只有文字记忆"))

    assert facts["user_notes"] == "只有文字记忆"
    assert facts["photo_count"] == 3
    assert facts["photos"] == []


def test_collect_facts_keeps_open_ended_chapter(stub_chapter, fake_db):
    """章节没有结束日期时，事实包的 end_date 记作「持续中」。"""
    row = _chapter_row(date(2020, 1, 1), None)
    stub_chapter.samples = []

    facts = chapter_diary.collect_facts(fake_db, row, _request(notes="还在继续"))

    assert facts["end_date"] == "持续中"


def _settings(*, model_name="gpt-4o", connection_id="conn-1", enable=True, api_key="sk-test"):
    connection = SimpleNamespace(
        id=connection_id,
        enable=enable,
        api_key=api_key,
        api_base="https://example.invalid/v1",
    )
    return SimpleNamespace(
        chat_connection_id=connection_id,
        analysis_connection_id="",
        chat_model_name=model_name,
        analysis_model_name="",
        connections=[connection],
    )


def test_configured_model_requires_a_model_name(monkeypatch, fake_db):
    """没有选模型时 400，提示先在系统设置里配置。"""
    monkeypatch.setattr(
        chapter_diary.config_manager, "get_user_config",
        lambda owner_id, db: SimpleNamespace(ai=_settings(model_name="")),
    )

    with pytest.raises(HTTPException) as excinfo:
        chapter_diary.configured_model(fake_db, uuid.uuid4())

    assert excinfo.value.status_code == 400
    assert "请先在系统设置中配置可用的 AI 对话模型" in excinfo.value.detail


def test_configured_model_requires_an_enabled_connection_with_api_key(monkeypatch, fake_db):
    """连接被禁用或缺少 api_key 时同样 400。"""
    for settings in (_settings(enable=False), _settings(api_key="")):
        monkeypatch.setattr(
            chapter_diary.config_manager, "get_user_config",
            lambda owner_id, db: SimpleNamespace(ai=settings),
        )
        with pytest.raises(HTTPException) as excinfo:
            chapter_diary.configured_model(fake_db, uuid.uuid4())
        assert excinfo.value.status_code == 400
        assert "请先在系统设置中配置可用的 AI 对话模型" in excinfo.value.detail


def test_configured_model_builds_client_from_chat_connection(monkeypatch, fake_db):
    """配置齐全时构造模型客户端，并把连接参数带过去。"""
    from app.service.agent import service as agent_service

    captured = {}

    class _FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        chapter_diary.config_manager, "get_user_config",
        lambda owner_id, db: SimpleNamespace(ai=_settings()),
    )
    monkeypatch.setattr(agent_service, "FixedChatOpenAI", _FakeClient, raising=False)

    client = chapter_diary.configured_model(fake_db, uuid.uuid4())

    assert isinstance(client, _FakeClient)
    assert captured["model"] == "gpt-4o"
    assert captured["api_key"] == "sk-test"
    assert captured["base_url"] == "https://example.invalid/v1"


def test_configured_model_falls_back_to_analysis_connection(monkeypatch, fake_db):
    """没配对话模型时，回退到分析模型对应的连接。"""
    from app.service.agent import service as agent_service

    settings = _settings(model_name="", connection_id="conn-9")
    settings.analysis_connection_id = "conn-9"
    settings.analysis_model_name = "gpt-4o-mini"
    settings.chat_model_name = ""

    class _FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(
        chapter_diary.config_manager, "get_user_config",
        lambda owner_id, db: SimpleNamespace(ai=settings),
    )
    monkeypatch.setattr(agent_service, "FixedChatOpenAI", _FakeClient, raising=False)

    client = chapter_diary.configured_model(fake_db, uuid.uuid4())

    assert client.kwargs["model"] == "gpt-4o-mini"
    assert client.kwargs["api_key"] == "sk-test"
