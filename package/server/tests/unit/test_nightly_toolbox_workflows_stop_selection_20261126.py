"""Nightly watch 2026-11-26 · app/api/toolbox_workflows.py 的停止与勾选盲区。

上一轮（2026-11-24）已经覆盖了「清理计划入队 / 重试 / 取消勾选」，但
``POST /plans/{id}/stop`` 这条路由、以及勾选接口的「新增勾选」和
「所选项不属于本计划」两条分支仍然没有断言：

- 停止请求必须只对运行中的计划生效，已结束的计划要给出明确提示
- 勾选要真正写入 CleanupSelection，取消勾选要真正删除
- 传入不属于本计划候选集的 id 时必须拒绝，而不是静默忽略

路由层用假的 session / 假的 plan 驱动，只验证「分发到哪个 service 函数」和
「失败时如何翻译成统一响应」，不触碰扫描与执行实现。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api import toolbox_workflows as workflows
from app.db.models.toolbox import CleanupSelection, ToolboxPlanItem
from app.schemas.toolbox import CleanupSelectionRequest


pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


class _Query:
    """只实现路由用到的查询接口，避免 MagicMock 的 len()/迭代陷阱。"""

    def __init__(self, rows=None):
        self._rows = list(rows or [])
        self.deleted = 0

    def filter(self, *args, **kwargs):
        return self

    def filter_by(self, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def offset(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._rows)

    def count(self):
        return len(self._rows)

    def first(self):
        return None

    def update(self, *args, **kwargs):
        return 1

    def delete(self, synchronize_session=False):
        self.deleted += 1
        removed = len(self._rows)
        self._rows = []
        return removed

    def __iter__(self):
        return iter(self._rows)


class _Session:
    def __init__(self, plan_items=(), selections=()):
        self.plan_items = list(plan_items)
        self.selections = list(selections)
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def query(self, model):
        if model is ToolboxPlanItem or model is ToolboxPlanItem.id:
            return _Query(self.plan_items)
        if model is CleanupSelection:
            return _Query(self.selections)
        return _Query()

    def add_all(self, rows):
        self.added.extend(rows)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def refresh(self, obj):
        return None


def _user():
    return SimpleNamespace(id=uuid4(), settings=None)


def _plan(**kwargs):
    base = {
        "id": uuid4(),
        "kind": "cleanup",
        "status": "preview",
        "version": 3,
        "request": {},
        "summary": {"phase": "done"},
        "task_id": None,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(days=1),
        "finished_at": None,
        "stop_requested": False,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


# --- 停止任务 ---------------------------------------------------------------

@pytest.mark.parametrize("status", ["queued", "running", "scan_queued", "scanning"])
def test_stop_marks_a_running_plan(monkeypatch, status):
    plan = _plan(status=status)
    monkeypatch.setattr(workflows, "get_plan", lambda db, owner_id, plan_id: plan)
    session = _Session()

    result = workflows.stop(plan.id, session, _user())

    assert result.code == 0
    assert plan.stop_requested is True
    assert result.data["stop_requested"] is True
    assert session.commits == 1


def test_stop_rejects_a_plan_that_already_finished(monkeypatch):
    plan = _plan(status="done")
    monkeypatch.setattr(workflows, "get_plan", lambda db, owner_id, plan_id: plan)
    session = _Session()

    result = workflows.stop(plan.id, session, _user())

    assert result.code == 400
    assert result.msg == "此任务已结束"
    assert plan.stop_requested is False
    assert session.rollbacks == 1


# --- 勾选候选 ---------------------------------------------------------------

def test_selection_stores_a_newly_checked_item(monkeypatch):
    plan = _plan(version=3)
    monkeypatch.setattr(workflows, "get_plan", lambda db, owner_id, plan_id: plan)
    session = _Session(plan_items=[7])
    request = CleanupSelectionRequest(version=3, item_ids=[7], selected=True)

    result = workflows.selection(plan.id, request, session, _user())

    assert result.code == 0
    assert result.data["selected_count"] == 0
    assert [row.item_id for row in session.added] == [7]
    assert session.commits == 1


def test_selection_does_not_store_an_item_that_is_already_checked(monkeypatch):
    plan = _plan(version=3)
    monkeypatch.setattr(workflows, "get_plan", lambda db, owner_id, plan_id: plan)
    session = _Session(plan_items=[7], selections=[SimpleNamespace(item_id=7)])
    request = CleanupSelectionRequest(version=3, item_ids=[7], selected=True)

    result = workflows.selection(plan.id, request, session, _user())

    assert result.code == 0
    assert session.added == []
    assert result.data["selected_count"] == 1


def test_selection_rejects_items_that_are_not_candidates_of_this_plan(monkeypatch):
    plan = _plan(version=3)
    monkeypatch.setattr(workflows, "get_plan", lambda db, owner_id, plan_id: plan)
    session = _Session(plan_items=[])
    request = CleanupSelectionRequest(version=3, item_ids=[99], selected=True)

    result = workflows.selection(plan.id, request, session, _user())

    assert result.code == 400
    assert result.msg == "所选项目不属于此计划的候选"
    assert session.added == []


def test_selection_rejects_a_plan_that_is_not_a_cleanup_preview(monkeypatch):
    plan = _plan(version=3, kind="organize")
    monkeypatch.setattr(workflows, "get_plan", lambda db, owner_id, plan_id: plan)
    session = _Session(plan_items=[7])
    request = CleanupSelectionRequest(version=3, item_ids=[7], selected=True)

    result = workflows.selection(plan.id, request, session, _user())

    assert result.code == 400
    assert result.msg == "预览已变化，请刷新"
    assert session.added == []


def test_selection_rejects_an_expired_preview(monkeypatch):
    plan = _plan(version=3, expires_at=datetime.utcnow() - timedelta(minutes=1))
    monkeypatch.setattr(workflows, "get_plan", lambda db, owner_id, plan_id: plan)
    session = _Session(plan_items=[7])
    request = CleanupSelectionRequest(version=3, item_ids=[7], selected=True)

    result = workflows.selection(plan.id, request, session, _user())

    assert result.code == 400
    assert result.msg == "预览已变化，请刷新"
