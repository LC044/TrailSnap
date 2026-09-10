"""2026-09-11 nightly tests for the five highest-priority backend gaps.

Coverage targets selected from the current Cobertura report:
agent context-window trimming, agent action-plan wrappers, task queue
priority accounting, day-caption material aggregation, and photo filter
option aggregation.
"""
import asyncio
import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

pytestmark = [pytest.mark.smoke]


def _ctx(db):
    @contextmanager
    def _cm():
        yield db

    return MagicMock(side_effect=_cm)


def _tool(name, user_id, session_id="session-1"):
    from app.service.agent.tools import get_agent_tools

    for tool in get_agent_tools(user_id, session_id):
        if tool.name == name:
            return tool
    raise AssertionError(f"tool {name} not found")


# ---------------------------------------------------------------------------
# app/service/agent/service.py -- configured context-window trimming
# ---------------------------------------------------------------------------


def test_trim_history_messages_honors_context_window_budget():
    from app.service.agent.service import trim_history_messages

    messages = [SystemMessage(content="album assistant")]
    for _ in range(6):
        messages.append(HumanMessage(content="历史问题" * 600))
        messages.append(AIMessage(content="历史回答" * 600))
    messages.append(HumanMessage(content="latest question"))

    trimmed = trim_history_messages(messages, context_window=1024)

    assert trimmed[0] is messages[0]
    assert trimmed[-1].content == "latest question"
    assert len(trimmed) < len(messages)


def test_estimate_message_tokens_handles_string_and_structured_content():
    from app.service.agent.service import _estimate_message_tokens

    estimated = _estimate_message_tokens(
        [
            HumanMessage(content="abc"),
            AIMessage(content=[{"type": "text", "text": "bar"}]),
        ]
    )
    assert estimated >= 18  # each message contributes at least the +8 overhead
    assert estimated == (1 + 8) + (len(json.dumps([{"type": "text", "text": "bar"}], ensure_ascii=False)) // 3 + 8)


# ---------------------------------------------------------------------------
# app/service/agent/tools.py -- action-plan and read-only wrappers
# ---------------------------------------------------------------------------


def test_agent_action_plan_wrappers_delegate_and_serialize_payload():
    from app.service.agent import tools as tools_module

    user_id = str(uuid4())
    db = MagicMock()
    row = SimpleNamespace(
        id=uuid4(), plan_type="album_repair", title="修复相册",
        summary="预览修复", status="PENDING", preview=[{"change": "cover"}],
    )
    cases = [
        ("propose_album_repairs", "propose_album_repair_plan"),
        ("propose_album_metadata_repairs", "propose_album_metadata_repair_plan"),
        ("propose_photo_context_repairs", "propose_photo_context_repair_plan"),
        ("propose_album_cleanup", "propose_album_cleanup_plan"),
    ]

    for tool_name, helper_name in cases:
        with (
            patch.object(tools_module, "SessionLocal", _ctx(db)),
            patch.object(tools_module, helper_name, return_value=row) as helper,
        ):
            payload = json.loads(
                _tool(tool_name, user_id).func("album-1", ["repair-1"], "摘要")
            )

        helper.assert_called_once_with(
            db, user_id, session_id="session-1", album_id="album-1",
            repair_ids=["repair-1"], summary="摘要",
        )
        assert payload["action_plan"] == {
            "id": str(row.id), "plan_type": row.plan_type, "title": row.title,
            "summary": row.summary, "status": row.status, "preview": row.preview,
        }


def test_agent_memory_and_person_timeline_wrappers_return_errors_safely():
    from app.service.agent import tools as tools_module

    user_id = str(uuid4())
    db = MagicMock()
    memory = {"events": [{"title": "西湖散步"}]}
    timeline = {"years": [{"year": 2026, "events": 2}]}

    with (
        patch.object(tools_module, "SessionLocal", _ctx(db)),
        patch.object(tools_module, "investigate_memory_clues", return_value=memory) as memory_mock,
        patch.object(tools_module, "build_person_timeline", return_value=timeline) as timeline_mock,
    ):
        memory_payload = json.loads(
            _tool("investigate_memory", user_id).func("西湖", "2026-01-01", "2026-12-31")
        )
        timeline_payload = json.loads(
            _tool("get_person_timeline", user_id).func("person-1", max_events=3)
        )

    assert memory_payload == memory
    assert memory_mock.call_args.args[-1] == 8
    assert timeline_payload == timeline
    assert timeline_mock.call_args.args[-1] == 3

    with (
        patch.object(tools_module, "SessionLocal", _ctx(db)),
        patch.object(tools_module, "investigate_memory_clues", side_effect=ValueError("bad date")),
    ):
        error = json.loads(_tool("investigate_memory", user_id).func("线索", "bad"))
    assert error == {"error": "bad date"}


# ---------------------------------------------------------------------------
# app/service/task_worker.py -- priority queue accounting
# ---------------------------------------------------------------------------


def test_task_queue_manager_reports_lowest_priority_and_item_counts():
    from app.service.task_worker import TaskQueueManager

    manager = TaskQueueManager()
    assert manager.get_lowest_priority("CPU") == -9999
    assert manager.get_lowest_priority("UNKNOWN") == -9999

    asyncio.run(manager.put_batch("CPU", [{"id": "low"}], priority=1))
    asyncio.run(manager.put_batch("CPU", [{"id": "high-a"}, {"id": "high-b"}], priority=5))

    assert manager.qsize("CPU") == 2
    assert manager.item_count("CPU") == 3
    assert manager.get_lowest_priority("CPU") == 1

    first = asyncio.run(manager.get_batch("CPU"))
    second = asyncio.run(manager.get_batch("CPU"))
    assert first == [{"id": "high-a"}, {"id": "high-b"}]
    assert second == [{"id": "low"}]
    assert manager.item_count("CPU") == 0

    manager.task_done("CPU")  # both items have been consumed


# ---------------------------------------------------------------------------
# app/service/moment/day_caption_service.py -- material aggregation
# ---------------------------------------------------------------------------


def test_build_materials_aggregates_dedupes_and_ranks_day_evidence():
    from app.db.models.photo import FileType
    from app.service.moment.day_caption_service import _build_materials

    db = MagicMock()
    p1, p2, p3 = uuid4(), uuid4(), uuid4()
    photos = [
        SimpleNamespace(id=p1, file_type=FileType.image),
        SimpleNamespace(id=p2, file_type=FileType.video),
        SimpleNamespace(id=p3, file_type=FileType.image),
    ]

    metadata_query, face_query, description_query = MagicMock(), MagicMock(), MagicMock()
    metadata_query.outerjoin.return_value.filter.return_value.all.return_value = [
        (SimpleNamespace(city="杭州", district="西湖", address=None), "西湖景区"),
        (SimpleNamespace(city="杭州", district="西湖", address=None), None),
        (SimpleNamespace(city="上海", district=None, address=None), None),
    ]
    face_query.join.return_value.filter.return_value.all.return_value = [("Bob",), ("Bob",), ("Alice",)]
    description_query.filter.return_value.all.return_value = [
        SimpleNamespace(narrative=None, description="老描述", tags=["旅行", "海边"]),
        SimpleNamespace(narrative="新叙述", description="fallback", tags=["旅行"]),
    ]
    db.query.side_effect = [metadata_query, face_query, description_query]

    materials = _build_materials(db, photos, image_original_count=5)

    assert materials["locations"] == ["西湖景区", "杭州 · 西湖", "上海"]
    assert materials["people"] == ["Bob", "Alice"]
    assert materials["descriptions"] == ["老描述", "新叙述"]
    assert materials["tags"] == ["旅行", "海边"]
    assert materials["counts"] == {"image": 2, "video": 1, "image_original": 5}


def test_build_materials_empty_photos_returns_zero_counts_without_query():
    from app.service.moment.day_caption_service import _build_materials

    db = MagicMock()
    materials = _build_materials(db, [], image_original_count=None)

    assert materials == {
        "locations": [], "people": [], "descriptions": [], "tags": [],
        "counts": {"image": 0, "video": 0, "image_original": 0},
    }
    db.query.assert_not_called()


# ---------------------------------------------------------------------------
# app/crud/photo.py -- filter option aggregation
# ---------------------------------------------------------------------------


def test_get_filter_options_dedupes_and_sorts_database_facets():
    from app.crud.photo import get_filter_options

    db = MagicMock()
    db.query.return_value.outerjoin.return_value.filter.return_value.distinct.return_value.all.return_value = [
        SimpleNamespace(year=2026.0, city="杭州", make="Apple", model="iPhone 15"),
        SimpleNamespace(year=2025.0, city=None, make=None, model=None),
        SimpleNamespace(year=2026.0, city="上海", make="Canon", model="EOS R5"),
    ]

    options = get_filter_options(db, uuid4())

    assert options["years"] == [2026, 2025]
    assert options["cities"] == ["上海", "杭州"]
    assert options["makes"] == ["Apple", "Canon"]
    assert options["models"] == ["EOS R5", "iPhone 15"]
    assert options["image_types"] == ["Screenshot", "Camera", "Other"]
    assert "video" in options["file_types"]


