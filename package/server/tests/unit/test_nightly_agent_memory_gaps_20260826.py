"""Unit tests for app/service/agent/memory.py (2026-08-26 round).

The module owns the photo-anchored long-term memory for the AI agent. The
functions under test fall into three buckets:

1. Pure helpers (no I/O): ``_parse_extraction_result``, ``_collect_photo_ids``
2. DB-bound read/write paths we drive with ``MagicMock`` dbs
   (``load_raw_memory``, ``get_valid_memory_anchors``, ``add_memory_anchor``,
    ``remove_memory_anchor``, ``build_memory_prompt``)
3. The background extraction task which talks to an LLM and a real session;
   we short-circuit the LLM and the session to assert the per-photo dedup
   and self-healing behaviors.
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.service.agent import memory
from app.service.agent.memory import (
    MAX_MEMORY_ANCHORS,
    MIN_MEMORY_SCORE,
    _collect_photo_ids,
    _parse_extraction_result,
    add_memory_anchor,
    build_memory_prompt,
    extract_and_store_memory_task,
    get_valid_memory_anchors,
    load_raw_memory,
    remove_memory_anchor,
)


pytestmark = [pytest.mark.smoke]


_PID_A = "11111111-1111-1111-1111-111111111111"
_PID_B = "22222222-2222-2222-2222-222222222222"
_PID_C = "33333333-3333-3333-3333-333333333333"


# -------------------------------------------------------------------------
# load_raw_memory / _empty_memory
# -------------------------------------------------------------------------


def test_load_raw_memory_returns_empty_when_no_message():
    db = MagicMock()
    with patch.object(memory.agent_crud, "get_memory_message", return_value=None):
        assert load_raw_memory(db, "u1") == {"version": memory.MEMORY_VERSION, "anchors": []}


def test_load_raw_memory_returns_empty_when_content_ext_not_dict():
    db = MagicMock()
    msg = SimpleNamespace(content_ext=["not", "a", "dict"])
    with patch.object(memory.agent_crud, "get_memory_message", return_value=msg):
        assert load_raw_memory(db, "u1") == {"version": memory.MEMORY_VERSION, "anchors": []}


def test_load_raw_memory_returns_empty_when_no_anchors_key():
    db = MagicMock()
    msg = SimpleNamespace(content_ext={"foo": "bar"})
    with patch.object(memory.agent_crud, "get_memory_message", return_value=msg):
        assert load_raw_memory(db, "u1") == {"version": memory.MEMORY_VERSION, "anchors": []}


def test_load_raw_memory_returns_payload_when_present():
    db = MagicMock()
    payload = {"version": 1, "anchors": [{"photo_id": _PID_A, "note": "n"}]}
    msg = SimpleNamespace(content_ext=payload)
    with patch.object(memory.agent_crud, "get_memory_message", return_value=msg):
        assert load_raw_memory(db, "u1") is payload


# -------------------------------------------------------------------------
# get_valid_memory_anchors
# -------------------------------------------------------------------------


def test_get_valid_memory_anchors_returns_empty_when_no_anchors():
    db = MagicMock()
    with patch.object(memory, "load_raw_memory", return_value={"version": 1, "anchors": []}):
        assert get_valid_memory_anchors(db, "u1") == []


def test_get_valid_memory_anchors_filters_out_deleted_photos():
    db = MagicMock()
    anchors = [
        {"photo_id": _PID_A, "note": "n1"},
        {"photo_id": _PID_B, "note": "n2"},
    ]
    db.query.return_value.filter.return_value.all.return_value = [(_PID_A,)]
    with patch.object(memory, "load_raw_memory", return_value={"version": 1, "anchors": anchors}):
        result = get_valid_memory_anchors(db, "u1")
    assert result == [{"photo_id": _PID_A, "note": "n1"}]


def test_get_valid_memory_anchors_self_heals_on_partial_loss():
    db = MagicMock()
    anchors = [
        {"photo_id": _PID_A, "note": "n1"},
        {"photo_id": _PID_B, "note": "n2"},
        {"photo_id": _PID_C, "note": "n3"},
    ]
    db.query.return_value.filter.return_value.all.return_value = [(_PID_A,), (_PID_C,)]
    with patch.object(memory, "load_raw_memory", return_value={"version": 1, "anchors": anchors}), \
         patch.object(memory.agent_crud, "upsert_memory_message") as upsert:
        result = get_valid_memory_anchors(db, "u1")
    assert len(result) == 2
    assert {a["photo_id"] for a in result} == {_PID_A, _PID_C}
    # The cleaned-up payload should be written back so the next call is fast.
    upsert.assert_called_once()
    call_args = upsert.call_args.args
    assert call_args[1] == "u1"
    assert {a["photo_id"] for a in call_args[2]["anchors"]} == {_PID_A, _PID_C}


def test_get_valid_memory_anchors_swallows_upsert_failure():
    db = MagicMock()
    anchors = [
        {"photo_id": _PID_A, "note": "n1"},
        {"photo_id": _PID_B, "note": "n2"},
    ]
    db.query.return_value.filter.return_value.all.return_value = [(_PID_A,)]
    with patch.object(memory, "load_raw_memory", return_value={"version": 1, "anchors": anchors}), \
         patch.object(memory.agent_crud, "upsert_memory_message", side_effect=RuntimeError("db down")):
        result = get_valid_memory_anchors(db, "u1")
    # Even if persistence fails, in-memory filter still applies.
    assert result == [{"photo_id": _PID_A, "note": "n1"}]


# -------------------------------------------------------------------------
# _parse_extraction_result
# -------------------------------------------------------------------------


def test_parse_extraction_result_handles_empty_string():
    assert _parse_extraction_result("") == []
    assert _parse_extraction_result(None) == []


def test_parse_extraction_result_handles_plain_json():
    text = '{"memories": [{"photo_id": "x", "note": "y"}]}'
    assert _parse_extraction_result(text) == [{"photo_id": "x", "note": "y"}]


def test_parse_extraction_result_handles_markdown_fence():
    text = '```json\n{"memories": [{"photo_id": "x", "note": "y"}]}\n```'
    assert _parse_extraction_result(text) == [{"photo_id": "x", "note": "y"}]


def test_parse_extraction_result_handles_garbage_around_json():
    text = 'Here you go: {"memories": [{"photo_id": "x", "note": "y"}]} cheers!'
    assert _parse_extraction_result(text) == [{"photo_id": "x", "note": "y"}]


def test_parse_extraction_result_returns_empty_on_broken_json():
    assert _parse_extraction_result("not json at all") == []
    assert _parse_extraction_result('{"foo": 1}') == []  # missing memories key
    assert _parse_extraction_result('{"memories": "not a list"}') == []


# -------------------------------------------------------------------------
# _collect_photo_ids
# -------------------------------------------------------------------------


def test_collect_photo_ids_extracts_from_medias_url():
    reply = f"Here is your photo: /medias/{_PID_A} and another /medias/{_PID_B}"
    assert _collect_photo_ids(reply, None) == {_PID_A, _PID_B}


def test_collect_photo_ids_extracts_from_tool_return_string():
    reply = ""
    tool_calls = [{"tool_return": f'{{"photo_id": "{_PID_A}"}},{{"photo_id":"{_PID_B}"}}'}]
    assert _collect_photo_ids(reply, tool_calls) == {_PID_A, _PID_B}


def test_collect_photo_ids_extracts_from_tool_return_dict():
    reply = ""
    tool_calls = [{"tool_return": {"photo_id": _PID_A}}]
    assert _collect_photo_ids(reply, tool_calls) == {_PID_A}


def test_collect_photo_ids_returns_empty_when_no_inputs():
    assert _collect_photo_ids("", None) == set()
    assert _collect_photo_ids(None, []) == set()
    assert _collect_photo_ids("nothing here", None) == set()


def test_collect_photo_ids_dedupes():
    reply = f"/medias/{_PID_A}\n/medias/{_PID_A}\n/medias/{_PID_A}"
    assert _collect_photo_ids(reply, None) == {_PID_A}


# -------------------------------------------------------------------------
# build_memory_prompt
# -------------------------------------------------------------------------


def test_build_memory_prompt_returns_empty_string_when_no_anchors():
    db = MagicMock()
    with patch.object(memory, "get_valid_memory_anchors", return_value=[]):
        assert build_memory_prompt(db, "u1") == ""


def test_build_memory_prompt_includes_each_anchor_line():
    db = MagicMock()
    anchors = [
        {
            "photo_id": _PID_A,
            "note": " 登顶那天  ",
            "photo_time": "2024-05-01 10:00:00",
            "location": "珠穆朗玛峰",
        },
        {
            "photo_id": _PID_B,
            "note": "生日聚会",
            "photo_time": None,
            "location": None,
        },
    ]
    with patch.object(memory, "get_valid_memory_anchors", return_value=anchors):
        prompt = build_memory_prompt(db, "u1")
    assert "【关于这位用户的长期记忆】" in prompt
    assert "登顶那天" in prompt  # whitespace stripped
    assert _PID_A in prompt
    assert "时间未知" in prompt
    assert "地点未知" in prompt
    assert _PID_B in prompt
    assert prompt.endswith("\n")


# -------------------------------------------------------------------------
# add_memory_anchor
# -------------------------------------------------------------------------


def _photo_row(photo_id=_PID_A, memory_score=80, narrative="n", address="上海"):
    photo = SimpleNamespace(id=photo_id, photo_time=datetime(2024, 5, 1, 10, 0, 0))
    meta = SimpleNamespace(address=address)
    desc = SimpleNamespace(memory_score=memory_score, narrative=narrative)
    return photo, meta, desc


def test_add_memory_anchor_returns_false_when_photo_missing():
    db = MagicMock()
    db.query.return_value.outerjoin.return_value.outerjoin.return_value.filter.return_value.first.return_value = None
    assert add_memory_anchor(db, "u1", _PID_A, "n") is False


def test_add_memory_anchor_rejects_low_memory_score():
    db = MagicMock()
    photo, meta, desc = _photo_row(memory_score=MIN_MEMORY_SCORE - 1)
    db.query.return_value.outerjoin.return_value.outerjoin.return_value.filter.return_value.first.return_value = (
        photo, meta, desc
    )
    assert add_memory_anchor(db, "u1", _PID_A, "n") is False


def test_add_memory_anchor_rejects_missing_memory_score():
    db = MagicMock()
    photo, meta, desc = _photo_row(memory_score=None)
    db.query.return_value.outerjoin.return_value.outerjoin.return_value.filter.return_value.first.return_value = (
        photo, meta, desc
    )
    assert add_memory_anchor(db, "u1", _PID_A, "n") is False


def test_add_memory_anchor_appends_and_dedupes():
    db = MagicMock()
    photo, meta, desc = _photo_row()
    db.query.return_value.outerjoin.return_value.outerjoin.return_value.filter.return_value.first.return_value = (
        photo, meta, desc
    )
    existing = {
        "version": memory.MEMORY_VERSION,
        "anchors": [
            {"photo_id": _PID_A, "note": "old note", "photo_time": "x", "location": "y"},
            {"photo_id": _PID_B, "note": "kept", "photo_time": "x", "location": "y"},
        ],
    }
    with patch.object(memory, "load_raw_memory", return_value=existing), \
         patch.object(memory.agent_crud, "upsert_memory_message") as upsert:
        ok = add_memory_anchor(db, "u1", _PID_A, "  new note  ")
    assert ok is True
    payload = upsert.call_args.args[2]
    # _PID_A entry replaced with the new note; _PID_B kept
    by_pid = {a["photo_id"]: a for a in payload["anchors"]}
    assert set(by_pid.keys()) == {_PID_A, _PID_B}
    assert by_pid[_PID_A]["note"] == "new note"
    assert by_pid[_PID_B]["note"] == "kept"
    # new entry carries the snapshot fields
    assert by_pid[_PID_A]["photo_time"] == "2024-05-01 10:00:00"
    assert by_pid[_PID_A]["location"] == "上海"
    assert "created_at" in by_pid[_PID_A]


def test_add_memory_anchor_evicts_oldest_when_over_cap():
    db = MagicMock()
    photo, meta, desc = _photo_row()
    db.query.return_value.outerjoin.return_value.outerjoin.return_value.filter.return_value.first.return_value = (
        photo, meta, desc
    )
    anchors = [
        {"photo_id": f"pid-{i}", "note": f"n{i}", "photo_time": "t", "location": "L"}
        for i in range(MAX_MEMORY_ANCHORS)
    ]
    existing = {"version": memory.MEMORY_VERSION, "anchors": list(anchors)}
    with patch.object(memory, "load_raw_memory", return_value=existing), \
         patch.object(memory.agent_crud, "upsert_memory_message") as upsert:
        ok = add_memory_anchor(db, "u1", _PID_A, "new")
    assert ok is True
    payload = upsert.call_args.args[2]
    assert len(payload["anchors"]) == MAX_MEMORY_ANCHORS
    # The oldest anchor (pid-0) was evicted, the rest are FIFO-kept, and _PID_A is the new tail.
    ids = [a["photo_id"] for a in payload["anchors"]]
    assert ids[0] == "pid-1"
    assert ids[-1] == _PID_A


# -------------------------------------------------------------------------
# remove_memory_anchor
# -------------------------------------------------------------------------


def test_remove_memory_anchor_returns_false_when_not_found():
    db = MagicMock()
    with patch.object(memory, "load_raw_memory",
                       return_value={"version": 1, "anchors": [{"photo_id": _PID_A, "note": "n"}]}):
        assert remove_memory_anchor(db, "u1", _PID_B) is False


def test_remove_memory_anchor_removes_and_persists():
    db = MagicMock()
    anchors = [
        {"photo_id": _PID_A, "note": "n1"},
        {"photo_id": _PID_B, "note": "n2"},
    ]
    with patch.object(memory, "load_raw_memory",
                       return_value={"version": 1, "anchors": list(anchors)}), \
         patch.object(memory.agent_crud, "upsert_memory_message") as upsert:
        ok = remove_memory_anchor(db, "u1", _PID_A)
    assert ok is True
    payload = upsert.call_args.args[2]
    assert payload["anchors"] == [{"photo_id": _PID_B, "note": "n2"}]


# -------------------------------------------------------------------------
# extract_and_store_memory_task (background)
# -------------------------------------------------------------------------


class _FakeResp:
    def __init__(self, content):
        self.content = content


def test_extract_task_returns_early_when_no_photo_ids_in_reply():
    with patch.object(memory, "_collect_photo_ids", return_value=set()), \
         patch.object(memory, "SessionLocal") as sl:
        extract_and_store_memory_task("u1", "hi", "hello there")
    sl.assert_not_called()


def test_extract_task_returns_early_when_llm_not_configured():
    db = MagicMock()
    db.__enter__.return_value = db
    db.__exit__.return_value = False
    with patch.object(memory, "_collect_photo_ids", return_value={_PID_A}), \
         patch.object(memory, "SessionLocal", return_value=db), \
         patch.object(memory, "_get_extraction_llm", return_value=(None, False)):
        extract_and_store_memory_task("u1", "hi", f"see /medias/{_PID_A}")
    # No LLM configured => no anchor side-effects
    assert db.add.call_count == 0


def test_extract_task_persists_each_anchor_through_add_memory_anchor():
    db = MagicMock()
    db.__enter__.return_value = db
    db.__exit__.return_value = False
    llm = MagicMock()
    llm.invoke.return_value = _FakeResp(
        f'{{"memories": [{{"photo_id": "{_PID_A}", "note": "first"}}, '
        f'{{"photo_id": "{_PID_B}", "note": "second"}}, '
        f'{{"photo_id": "fake-id-not-in-reply", "note": "ignored"}}]}}'
    )
    reply = f"first /medias/{_PID_A} then /medias/{_PID_B}"
    with patch.object(memory, "_collect_photo_ids", return_value={_PID_A, _PID_B}), \
         patch.object(memory, "SessionLocal", return_value=db), \
         patch.object(memory, "_get_extraction_llm", return_value=(llm, True)), \
         patch.object(memory, "add_memory_anchor") as add_anchor:
        extract_and_store_memory_task("u1", "hi", reply)
    # Only the in-reply photo_ids are persisted
    persisted_pids = [call.args[2] for call in add_anchor.call_args_list]
    assert persisted_pids == [_PID_A, _PID_B]


def test_extract_task_swallows_exception():
    with patch.object(memory, "_collect_photo_ids",
                       side_effect=RuntimeError("regex engine broken")):
        # The background task must not raise.
        extract_and_store_memory_task("u1", "hi", f"/medias/{_PID_A}")
