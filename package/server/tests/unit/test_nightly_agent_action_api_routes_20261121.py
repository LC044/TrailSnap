"""Nightly watch 2026-11-21 · app/api/agent_action.py 的路由盲区。

被测模块：app/api/agent_action.py。上一轮静态扫描显示该 router 有 10 个顶层
函数没有任何测试引用（list_action_plans / get_action_plan /
confirm_action_plan / get_action_plan_progress / retry_action_plan_tasks /
cancel_action_plan_tasks / continue_action_plan / update_action_plan /
reject_action_plan / undo_action_plan）。

这个 router 的价值几乎全在「错误码映射」上：业务层统一抛 ValueError，
路由层要把它翻译成 409，并把内部异常藏成 500 而不是把栈泄给前端。
本文件替换 service 协作者，逐条验证这条映射链路。
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import agent_action as agent_action_api

pytestmark = [pytest.mark.smoke]


def _user():
    return SimpleNamespace(id=uuid4())


def _plan_row(status="pending", plan_type="album_metadata_repair"):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        session_id=None,
        plan_type=plan_type,
        title="修复相册",
        summary=None,
        status=status,
        operations={},
        preview={},
        result=None,
        attempt_count=0,
        error_message=None,
        created_at=now,
        updated_at=now,
        expires_at=None,
        executed_at=None,
        failed_at=None,
        undone_at=None,
    )


def _fail_with_value_error(monkeypatch, name):
    def explode(*_args, **_kwargs):
        raise ValueError("计划状态已变化")

    monkeypatch.setattr(agent_action_api, name, explode)


def test_list_action_plans_serializes_the_owned_plans(monkeypatch):
    rows = [_plan_row()]
    captured = {}

    def fake_list_owned_plans(db, owner_id, session_id, status, limit):
        captured.update({"owner_id": owner_id, "session_id": session_id, "status": status, "limit": limit})
        return rows

    monkeypatch.setattr(agent_action_api, "list_owned_plans", fake_list_owned_plans)
    user = _user()
    result = agent_action_api.list_action_plans("s1", "pending", 10, user, MagicMock())

    assert result.code == 0
    assert result.data[0]["plan_type"] == "album_metadata_repair"
    assert captured == {"owner_id": user.id, "session_id": "s1", "status": "pending", "limit": 10}


def test_get_action_plan_expires_the_stale_plans_first(monkeypatch):
    calls = []
    monkeypatch.setattr(agent_action_api, "expire_stale_plans",
                        lambda db, owner_id: calls.append(owner_id))
    monkeypatch.setattr(agent_action_api, "get_owned_plan", lambda db, owner_id, plan_id: _plan_row())

    user = _user()
    result = agent_action_api.get_action_plan("plan-1", user, MagicMock())

    assert result.code == 0
    assert calls == [user.id]


def test_get_action_plan_reports_a_missing_plan_as_404(monkeypatch):
    monkeypatch.setattr(agent_action_api, "expire_stale_plans", lambda db, owner_id: None)
    monkeypatch.setattr(agent_action_api, "get_owned_plan", lambda db, owner_id, plan_id: None)

    with pytest.raises(HTTPException) as failure:
        agent_action_api.get_action_plan("missing", _user(), MagicMock())
    assert failure.value.status_code == 404
    assert failure.value.detail == "Action plan not found"


def test_confirm_action_plan_maps_a_value_error_to_409(monkeypatch):
    db = MagicMock()
    failed = []
    _fail_with_value_error(monkeypatch, "execute_plan")
    monkeypatch.setattr(agent_action_api, "mark_plan_failed",
                        lambda db, owner_id, plan_id, message: failed.append(message))

    with pytest.raises(HTTPException) as failure:
        agent_action_api.confirm_action_plan("plan-1", _user(), db)

    assert failure.value.status_code == 409
    assert failure.value.detail == "计划状态已变化"
    assert failed == ["计划状态已变化"]
    assert db.rollback.called


def test_confirm_action_plan_hides_an_internal_error_as_500(monkeypatch):
    db = MagicMock()
    failed = []

    def explode(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(agent_action_api, "execute_plan", explode)
    monkeypatch.setattr(agent_action_api, "mark_plan_failed",
                        lambda db, owner_id, plan_id, message: failed.append(message))

    with pytest.raises(HTTPException) as failure:
        agent_action_api.confirm_action_plan("plan-1", _user(), db)

    assert failure.value.status_code == 500
    assert failure.value.detail == "Action plan execution failed"
    # 内部异常详情不能泄漏到客户端
    assert "boom" not in failure.value.detail
    assert failed == ["执行过程中发生内部错误"]


def test_get_action_plan_progress_maps_a_value_error_to_409(monkeypatch):
    _fail_with_value_error(monkeypatch, "get_metadata_repair_progress")
    with pytest.raises(HTTPException) as failure:
        agent_action_api.get_action_plan_progress("plan-1", _user(), MagicMock())
    assert failure.value.status_code == 409


def test_retry_action_plan_tasks_maps_a_value_error_to_409(monkeypatch):
    db = MagicMock()
    _fail_with_value_error(monkeypatch, "retry_metadata_repair_tasks")
    with pytest.raises(HTTPException) as failure:
        agent_action_api.retry_action_plan_tasks("plan-1", _user(), db)
    assert failure.value.status_code == 409
    assert db.rollback.called


def test_cancel_action_plan_tasks_maps_a_value_error_to_409(monkeypatch):
    db = MagicMock()
    _fail_with_value_error(monkeypatch, "cancel_metadata_repair_tasks")
    with pytest.raises(HTTPException) as failure:
        agent_action_api.cancel_action_plan_tasks("plan-1", _user(), db)
    assert failure.value.status_code == 409
    assert db.rollback.called


def test_continue_action_plan_maps_a_value_error_to_409(monkeypatch):
    db = MagicMock()
    _fail_with_value_error(monkeypatch, "continue_metadata_repair_plan")
    with pytest.raises(HTTPException) as failure:
        agent_action_api.continue_action_plan("plan-1", _user(), db)
    assert failure.value.status_code == 409
    assert db.rollback.called


def test_update_action_plan_maps_a_value_error_to_409(monkeypatch):
    from app.schemas.agent_action import AgentRepairSelectionUpdate

    db = MagicMock()
    _fail_with_value_error(monkeypatch, "update_repair_plan_selection")
    payload = AgentRepairSelectionUpdate(selected_repair_ids=["r1"])
    with pytest.raises(HTTPException) as failure:
        agent_action_api.update_action_plan("plan-1", payload, _user(), db)
    assert failure.value.status_code == 409
    assert db.rollback.called


def test_reject_action_plan_maps_a_value_error_to_409(monkeypatch):
    db = MagicMock()
    _fail_with_value_error(monkeypatch, "reject_plan")
    with pytest.raises(HTTPException) as failure:
        agent_action_api.reject_action_plan("plan-1", _user(), db)
    assert failure.value.status_code == 409
    assert db.rollback.called


def test_undo_action_plan_maps_a_value_error_to_409(monkeypatch):
    db = MagicMock()
    _fail_with_value_error(monkeypatch, "undo_plan")
    with pytest.raises(HTTPException) as failure:
        agent_action_api.undo_action_plan("plan-1", _user(), db)
    assert failure.value.status_code == 409
    assert db.rollback.called


def test_reject_action_plan_returns_the_serialized_plan(monkeypatch):
    row = _plan_row(status="rejected")
    monkeypatch.setattr(agent_action_api, "reject_plan", lambda db, owner_id, plan_id: row)
    result = agent_action_api.reject_action_plan("plan-1", _user(), MagicMock())
    assert result.code == 0
    assert result.data["status"] == "rejected"
