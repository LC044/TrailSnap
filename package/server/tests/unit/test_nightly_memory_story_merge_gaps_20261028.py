"""Nightly coverage for the AI-story path in ``app/service/memory.py``.

The 2026-10-28 backend coverage scan ranked ``service/memory.py`` at 81.3%
(77 missed statements).  The largest untouched block was the LLM-backed
story generation and the merge/split lifecycle:

* ``generate_story``  -- the whole "ask the model, then persist" cycle,
  including the concurrency guard, the "AI is not configured" guards, the
  grounding prompt and the failure bookkeeping;
* ``merge``          -- merging several memories into one;
* ``split``          -- splitting a memory back into several.

``generate_story`` is the one place in the app where a model writes prose
that the user then sees as *their own* memory, so the guards around it
(only confirmed memories, only configured connections, grounded prompt,
failure state) are exactly what needs pinning down.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.face import FaceIdentity
from app.db.models.image_description import ImageDescription
from app.db.models.memory import Memory, MemoryPhoto, MemoryStatus
from app.db.models.photo import FileType, Photo
from app.db.models.user import User
from app.service import memory as memory_service


def _config_manager_singleton():
    """The ``config_manager`` singleton used by ``generate_story``.

    ``generate_story`` imports the singleton inside the function, so the test
    has to patch that object.  The *instance* attribute has to be patched -
    ``tests/unit/test_gallery_service.py`` permanently assigns a mock to
    ``config_manager.get_user_config``, and an instance attribute shadows the
    class attribute, so patching the class alone would silently do nothing
    whenever the whole suite runs.
    """
    from app.core.config_manager import config_manager

    return config_manager


pytestmark = [pytest.mark.smoke]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _owner(db, username="owner"):
    user = User(id=uuid4(), username=username, hashed_password="x")
    db.add(user)
    db.commit()
    return user.id


def _photo(db, owner_id, filename="p.jpg"):
    photo = Photo(
        id=uuid4(), owner_id=owner_id, filename=filename, file_path=filename,
        file_type=FileType.image, is_deleted=False, size=1, width=10, height=10,
        photo_time=datetime(2026, 5, 1, 10, 0),
    )
    db.add(photo)
    db.commit()
    return photo


def _memory(db, owner_id, status=MemoryStatus.CONFIRMED, title="一次旅行"):
    memory = Memory(
        id=uuid4(), owner_id=owner_id, status=status, title=title,
        story_generation_status="idle", story_source="system",
        cover_source="system", time_source="inferred", version=1,
    )
    db.add(memory)
    db.commit()
    return memory


def _ai_settings(connection_id="conn-1", model_name="gpt-test"):
    connection = SimpleNamespace(
        id=connection_id, enable=True, api_key="key", api_base="https://example.invalid",
    )
    return SimpleNamespace(
        chat_connection_id=connection_id, chat_model_name=model_name,
        analysis_connection_id="", analysis_model_name="",
        connections=[connection],
    )


def _patch_llm(monkeypatch, content="这是一段来自模型的故事。"):
    """Replace the chat model with a stub that returns ``content``."""
    llm = MagicMock()

    async def ainvoke(_messages):
        return SimpleNamespace(content=content)

    llm.ainvoke = ainvoke
    monkeypatch.setattr("app.service.agent.service.FixedChatOpenAI", lambda **kwargs: llm)
    return llm


# ---------------------------------------------------------------------------
# generate_story -- guards
# ---------------------------------------------------------------------------


def test_generate_story_requires_a_confirmed_memory(db):
    """Error: a candidate memory has no confirmed facts to write about."""
    owner = _owner(db)
    memory = _memory(db, owner, status=MemoryStatus.CANDIDATE)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(memory_service.generate_story(db, memory, owner, tone="温柔"))
    assert exc.value.status_code == 400
    assert "已确认" in exc.value.detail


def test_generate_story_requires_a_configured_chat_model(db, monkeypatch):
    """Error: without a chat connection the story cannot be generated."""
    owner = _owner(db)
    memory = _memory(db, owner)

    settings = SimpleNamespace(
        chat_connection_id="", chat_model_name="",
        analysis_connection_id="", analysis_model_name="",
        connections=[],
    )
    monkeypatch.setattr(
        _config_manager_singleton(), "get_user_config",
        lambda *args, **kwargs: SimpleNamespace(ai=settings),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(memory_service.generate_story(db, memory, owner, tone="温柔"))
    assert exc.value.status_code == 400
    assert "配置 AI 对话模型" in exc.value.detail


def test_generate_story_rejects_an_unusable_connection(db, monkeypatch):
    """Error: a disabled or key-less connection is not usable."""
    owner = _owner(db)
    memory = _memory(db, owner)

    settings = _ai_settings()
    settings.connections[0].enable = False
    monkeypatch.setattr(
        _config_manager_singleton(), "get_user_config",
        lambda *args, **kwargs: SimpleNamespace(ai=settings),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(memory_service.generate_story(db, memory, owner, tone="温柔"))
    assert exc.value.status_code == 400
    assert "AI 连接不可用" in exc.value.detail


def test_generate_story_refuses_a_concurrent_run(db, monkeypatch):
    """Error: a story that is already being generated is not regenerated."""
    owner = _owner(db)
    memory = _memory(db, owner)
    memory.story_generation_status = "generating"
    memory.story_generation_started_at = datetime.now() - timedelta(minutes=1)
    db.commit()

    monkeypatch.setattr(
        _config_manager_singleton(), "get_user_config",
        lambda *args, **kwargs: SimpleNamespace(ai=_ai_settings()),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(memory_service.generate_story(db, memory, owner, tone="温柔"))
    assert exc.value.status_code == 409
    assert "正在生成" in exc.value.detail


def test_generate_story_allows_a_stale_generation_to_restart(db, monkeypatch):
    """Edge: a run older than five minutes is considered abandoned."""
    owner = _owner(db)
    memory = _memory(db, owner)
    memory.story_generation_status = "generating"
    memory.story_generation_started_at = datetime.now() - timedelta(minutes=30)
    db.commit()

    monkeypatch.setattr(
        _config_manager_singleton(), "get_user_config",
        lambda *args, **kwargs: SimpleNamespace(ai=_ai_settings()),
    )
    _patch_llm(monkeypatch)

    result = asyncio.run(memory_service.generate_story(db, memory, owner, tone="温柔"))
    assert result.story_generation_status == "idle"


# ---------------------------------------------------------------------------
# generate_story -- happy path and grounding
# ---------------------------------------------------------------------------


def test_generate_story_persists_the_story_and_clears_the_state(db, monkeypatch):
    """Happy path: the model text is stored and the status returns to idle."""
    owner = _owner(db)
    memory = _memory(db, owner)

    monkeypatch.setattr(
        _config_manager_singleton(), "get_user_config",
        lambda *args, **kwargs: SimpleNamespace(ai=_ai_settings()),
    )
    _patch_llm(monkeypatch, "模型写下的一段故事。")

    result = asyncio.run(memory_service.generate_story(db, memory, owner, tone="温柔"))

    db.expire_all()
    refreshed = db.query(Memory).filter(Memory.id == memory.id).one()
    assert refreshed.story == "模型写下的一段故事。"
    assert refreshed.story_source == "system"
    assert refreshed.story_generation_status == "idle"
    assert refreshed.story_generation_started_at is None
    assert refreshed.story_generation_error is None
    assert refreshed.version == 2
    assert result.story == "模型写下的一段故事。"


def test_generate_story_prompt_contains_only_grounded_facts(db, monkeypatch):
    """The prompt must carry the memory facts, not invented relations."""
    owner = _owner(db)
    memory = _memory(db, owner, title="青岛的海边")
    photo = _photo(db, owner)
    db.add(MemoryPhoto(memory_id=memory.id, photo_id=photo.id, role="normal",
                           source="inferred", confidence=1.0, is_confirmed=True))
    db.add(ImageDescription(photo_id=photo.id, narrative="海边的黄昏"))
    db.commit()

    captured = {}

    def _capture(monkeypatch, content="故事正文。"):
        llm = MagicMock()

        async def ainvoke(messages):
            captured["messages"] = messages
            return SimpleNamespace(content=content)

        llm.ainvoke = ainvoke
        monkeypatch.setattr("app.service.agent.service.FixedChatOpenAI", lambda **kwargs: llm)

    monkeypatch.setattr(
        _config_manager_singleton(), "get_user_config",
        lambda *args, **kwargs: SimpleNamespace(ai=_ai_settings()),
    )
    _capture(monkeypatch)

    asyncio.run(memory_service.generate_story(db, memory, owner, tone="温柔"))

    prompt = captured["messages"][-1].content
    assert "青岛的海边" in prompt
    assert "海边的黄昏" in prompt
    assert "温柔" in prompt
    # The system prompt forbids inventing facts.
    assert "不得虚构" in captured["messages"][0].content


def test_generate_story_marks_the_failure_when_the_model_returns_nothing(db, monkeypatch):
    """Error: an empty model reply is recorded as a failure, not a silent success."""
    owner = _owner(db)
    memory = _memory(db, owner)

    monkeypatch.setattr(
        _config_manager_singleton(), "get_user_config",
        lambda *args, **kwargs: SimpleNamespace(ai=_ai_settings()),
    )
    _patch_llm(monkeypatch, "   ")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(memory_service.generate_story(db, memory, owner, tone="温柔"))
    assert exc.value.status_code == 502

    db.expire_all()
    refreshed = db.query(Memory).filter(Memory.id == memory.id).one()
    assert refreshed.story_generation_status == "failed"
    assert refreshed.story_generation_started_at is None
    assert refreshed.story_generation_error


def test_generate_story_records_a_model_error(db, monkeypatch):
    """Error: an exception from the model leaves the memory in the failed state."""
    owner = _owner(db)
    memory = _memory(db, owner)

    monkeypatch.setattr(
        _config_manager_singleton(), "get_user_config",
        lambda *args, **kwargs: SimpleNamespace(ai=_ai_settings()),
    )
    llm = MagicMock()

    async def ainvoke(_messages):
        raise RuntimeError("model offline")

    llm.ainvoke = ainvoke
    monkeypatch.setattr("app.service.agent.service.FixedChatOpenAI", lambda **kwargs: llm)

    with pytest.raises(RuntimeError):
        asyncio.run(memory_service.generate_story(db, memory, owner, tone="温柔"))

    db.expire_all()
    refreshed = db.query(Memory).filter(Memory.id == memory.id).one()
    assert refreshed.story_generation_status == "failed"
    assert "model offline" in refreshed.story_generation_error


def test_generate_story_strips_think_tags_and_headings(db, monkeypatch):
    """The raw model output is normalised before it is stored."""
    owner = _owner(db)
    memory = _memory(db, owner)

    monkeypatch.setattr(
        _config_manager_singleton(), "get_user_config",
        lambda *args, **kwargs: SimpleNamespace(ai=_ai_settings()),
    )
    _patch_llm(monkeypatch, "<think>推理过程</think>\n# 标题\n真正的故事正文。")

    asyncio.run(memory_service.generate_story(db, memory, owner, tone="温柔"))

    db.expire_all()
    refreshed = db.query(Memory).filter(Memory.id == memory.id).one()
    assert refreshed.story == "真正的故事正文。"


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------


def test_merge_requires_at_least_two_memories(db):
    """Error: a single memory cannot be merged."""
    owner = _owner(db)
    memory = _memory(db, owner)

    with pytest.raises(HTTPException) as exc:
        memory_service.merge(db, owner, [memory.id], title=None, story=None, cover_photo_id=None)
    assert exc.value.status_code == 400
    assert "至少选择两段" in exc.value.detail


def test_merge_refuses_memories_that_are_not_owned(db):
    """Error: another user's memory cannot be merged into ours."""
    owner, stranger = _owner(db, "owner"), _owner(db, "stranger")
    mine = _memory(db, owner)
    theirs = _memory(db, stranger)

    with pytest.raises(HTTPException) as exc:
        memory_service.merge(db, owner, [mine.id, theirs.id], title=None, story=None, cover_photo_id=None)
    assert exc.value.status_code == 400
    assert "部分记忆不存在" in exc.value.detail


def test_merge_creates_one_memory_from_several(db):
    """Happy path: two memories become one with all their photos."""
    owner = _owner(db)
    first = _memory(db, owner, title="第一天")
    second = _memory(db, owner, title="第二天")
    photo_a = _photo(db, owner, "a.jpg")
    photo_b = _photo(db, owner, "b.jpg")
    db.add(MemoryPhoto(memory_id=first.id, photo_id=photo_a.id, role="normal",
                           source="inferred", confidence=1.0, is_confirmed=True))
    db.add(MemoryPhoto(memory_id=second.id, photo_id=photo_b.id, role="normal",
                           source="inferred", confidence=1.0, is_confirmed=True))
    db.commit()

    merged = memory_service.merge(db, owner, [first.id, second.id],
                                  title="合并的旅行", story=None, cover_photo_id=None)

    db.expire_all()
    assert merged.title == "合并的旅行"
    assert {link.photo_id for link in merged.photo_links} == {photo_a.id, photo_b.id}
    # The sources are superseded, not deleted: the history stays reachable.
    sources = db.query(Memory).filter(Memory.id.in_([first.id, second.id])).all()
    assert all(row.status == MemoryStatus.SUPERSEDED for row in sources)
    assert all(row.version == 2 for row in sources)


def test_merge_refuses_a_cover_that_is_not_part_of_the_merge(db):
    """Error: the cover must be one of the merged photos."""
    owner = _owner(db)
    first = _memory(db, owner)
    second = _memory(db, owner)
    outsider = _photo(db, owner, "outsider.jpg")

    with pytest.raises(HTTPException) as exc:
        memory_service.merge(db, owner, [first.id, second.id], title=None, story=None,
                             cover_photo_id=outsider.id)
    assert exc.value.status_code == 400
    assert "封面必须属于合并后的照片" in exc.value.detail





