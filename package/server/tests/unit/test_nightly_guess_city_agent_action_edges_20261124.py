"""Nightly watch 2026-11-24 — app/api/guess_city.py 与 app/api/agent_action.py 补测。

* guess_city：存在高频城市时会排除该城市，且当没有一年以上的老照片时
  回退到全部候选里随机挑一张。
* agent_action：各路由的「成功路径」——之前只锁定了错误码映射，成功时的
  返回值与后台 worker 唤醒逻辑没有覆盖。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.api import agent_action as agent_action_api
from app.api import guess_city as guess_city_api


pytestmark = [pytest.mark.smoke]


# --------------------------------------------------------------------------- #
# guess_city
# --------------------------------------------------------------------------- #

def _query_mock(*, all_values=None, first_value=None):
    q = MagicMock()
    q.all.return_value = all_values if all_values is not None else []
    q.first.return_value = first_value
    q.filter.return_value = q
    q.group_by.return_value = q
    q.order_by.return_value = q
    q.join.return_value = q
    return q


def _photo_query_chain(*, old_photos, all_photos):
    """构造照片候选查询的 filter 链。

    路由里的调用顺序是：join -> filter(未删除) -> filter(城市非空) ->
    filter(排除 top city) -> filter(一年以上) 得到 old_photos，
    回退时则在「排除 top city」那层上直接 .all()。
    """
    old_level = MagicMock()
    old_level.all.return_value = old_photos

    top_city_level = MagicMock()
    top_city_level.filter.return_value = old_level
    top_city_level.all.return_value = all_photos

    city_level = MagicMock()
    city_level.filter.return_value = top_city_level

    deleted_level = MagicMock()
    deleted_level.filter.return_value = city_level

    root = MagicMock()
    root.join.return_value = root
    root.filter.return_value = deleted_level
    return root


def test_random_photo_excludes_the_top_city_and_falls_back_to_any_photo(monkeypatch):
    """存在高频城市时应排除它；没有老照片时从剩余候选里随机选一张。"""
    photo = SimpleNamespace(id=uuid.uuid4(), photo_time=datetime(2026, 7, 1))
    top_city_row = SimpleNamespace(city="上海")

    # base query -> is_deleted -> city 非空 -> 排除 top city -> 一年以上的老照片
    old_photos_chain = _photo_query_chain(old_photos=[], all_photos=[photo])
    db = MagicMock()
    db.query.side_effect = [
        _query_mock(first_value=top_city_row),   # top city 统计
        old_photos_chain,                        # 照片候选查询
    ]

    monkeypatch.setattr(
        guess_city_api.random, "choice", lambda items: items[0]
    )

    response = guess_city_api.get_random_photo(db=db)

    assert response.code == 0
    assert response.data["id"] == str(photo.id)


# --------------------------------------------------------------------------- #
# agent_action 成功路径
# --------------------------------------------------------------------------- #

def _user():
    return SimpleNamespace(id=uuid.uuid4())


def _plan_row(status="pending", plan_type="album_metadata_repair"):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
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


def _patch_task_manager(monkeypatch):
    """替换 TaskManager，记录后台 worker 是否被唤醒。"""
    calls = []
    manager = SimpleNamespace(start_worker_if_needed=lambda: calls.append("started"))
    monkeypatch.setattr(
        agent_action_api.TaskManager, "get_instance", staticmethod(lambda: manager)
    )
    return calls


def test_confirm_action_plan_starts_the_worker_for_metadata_repair(monkeypatch):
    """相册元数据修复计划执行成功后应唤醒后台 worker。"""
    row = _plan_row()
    monkeypatch.setattr(agent_action_api, "execute_plan", lambda db, owner_id, plan_id: row)
    calls = _patch_task_manager(monkeypatch)

    result = agent_action_api.confirm_action_plan("plan-1", _user(), MagicMock())

    assert result.code == 0
    assert result.data["plan_type"] == "album_metadata_repair"
    assert calls == ["started"]


def test_confirm_action_plan_does_not_start_the_worker_for_other_plan_types(monkeypatch):
    """非元数据修复的计划不应唤醒修复 worker。"""
    row = _plan_row(plan_type="photo_organize")
    monkeypatch.setattr(agent_action_api, "execute_plan", lambda db, owner_id, plan_id: row)
    calls = _patch_task_manager(monkeypatch)

    agent_action_api.confirm_action_plan("plan-1", _user(), MagicMock())

    assert calls == []


def test_get_action_plan_progress_returns_the_progress_payload(monkeypatch):
    """进度接口成功时直接返回业务层给出的进度。"""
    monkeypatch.setattr(
        agent_action_api, "get_metadata_repair_progress",
        lambda db, owner_id, plan_id: {"total": 10, "done": 4},
    )

    result = agent_action_api.get_action_plan_progress("plan-1", _user(), MagicMock())

    assert result.code == 0
    assert result.data == {"total": 10, "done": 4}


def test_retry_action_plan_tasks_starts_the_worker(monkeypatch):
    """重试失败项成功后应唤醒后台 worker。"""
    row = _plan_row(status="running")
    monkeypatch.setattr(
        agent_action_api, "retry_metadata_repair_tasks", lambda db, owner_id, plan_id: row
    )
    calls = _patch_task_manager(monkeypatch)

    result = agent_action_api.retry_action_plan_tasks("plan-1", _user(), MagicMock())

    assert result.code == 0
    assert result.data["status"] == "running"
    assert calls == ["started"]


def test_cancel_action_plan_tasks_returns_the_cancel_result(monkeypatch):
    """取消接口返回业务层的取消结果。"""
    monkeypatch.setattr(
        agent_action_api, "cancel_metadata_repair_tasks",
        lambda db, owner_id, plan_id: {"cancelled": 2},
    )

    result = agent_action_api.cancel_action_plan_tasks("plan-1", _user(), MagicMock())

    assert result.code == 0
    assert result.data == {"cancelled": 2}


def test_continue_action_plan_returns_the_next_batch(monkeypatch):
    """续跑接口返回新一批的计划内容。"""
    row = _plan_row(status="pending")
    monkeypatch.setattr(
        agent_action_api, "continue_metadata_repair_plan", lambda db, owner_id, plan_id: row
    )

    result = agent_action_api.continue_action_plan("plan-1", _user(), MagicMock())

    assert result.code == 0
    assert result.data["status"] == "pending"


def test_update_action_plan_returns_the_updated_plan(monkeypatch):
    """调整修复范围后返回更新后的计划。"""
    row = _plan_row()
    captured = {}

    def fake_update(db, owner_id, plan_id, selected_repair_ids):
        captured["selected"] = selected_repair_ids
        return row

    monkeypatch.setattr(agent_action_api, "update_repair_plan_selection", fake_update)
    payload = SimpleNamespace(selected_repair_ids=["a", "b"])

    result = agent_action_api.update_action_plan("plan-1", payload, _user(), MagicMock())

    assert result.code == 0
    assert captured["selected"] == ["a", "b"]
    assert result.data["id"] == str(row.id)


def test_undo_action_plan_returns_the_undone_plan(monkeypatch):
    """撤销接口返回撤销后的计划。"""
    row = _plan_row(status="undone")
    monkeypatch.setattr(agent_action_api, "undo_plan", lambda db, owner_id, plan_id: row)

    result = agent_action_api.undo_action_plan("plan-1", _user(), MagicMock())

    assert result.code == 0
    assert result.data["status"] == "undone"


