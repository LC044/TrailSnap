"""Nightly watch 2026-11-24 · app/api/toolbox_workflows.py 的清理（cleanup）分支盲区。

覆盖扫描显示 toolbox_workflows.py 还有 15 行未覆盖，全部落在「清理任务」这条
路线上——也就是最近重构后新加、却还没有路由级测试的部分：

- POST /plans 在 kind == "cleanup" 时改走 enqueue_scan (L49-L54)
- POST /plans/{id}/retry 的两条恢复路径：
  scan_stopped/scan_failed -> queue_scan (L119-L122)，
  cleanup 且 phase == "done" -> prepare_retry (L124-L125)
- PUT /plans/{id}/selection 的版本失效提示 (L139) 与取消勾选分支 (L150)
- GET /plans/{id}/groups/{group_id}/members 的「分组不存在」(L165)

路由层用假的 session / 假的 plan 驱动，只验证「分发到哪个 service 函数」和
「失败时如何翻译成统一响应」，不触碰扫描与执行实现。
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api import toolbox_workflows as workflows
from app.db.models.toolbox import CleanupSelection, ToolboxPlanItem
from app.db.models.user import User
from app.schemas.toolbox import CleanupSelectionRequest, MediaScope, PlanRequest, ToolConfig

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

    def order_by(self, *args):
        return self

    def offset(self, *args):
        return self

    def limit(self, *args):
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


@pytest.fixture
def no_worker(monkeypatch):
    """TaskManager 会真的起线程；路由测试里换成假的。"""
    calls = []

    class _Manager:
        @staticmethod
        def get_instance():
            return SimpleNamespace(start_worker_if_needed=lambda: calls.append("started"))

    monkeypatch.setattr(workflows, "TaskManager", _Manager)
    return calls


def test_preview_queues_a_cleanup_scan(monkeypatch, no_worker):
    from app.service import cleanup_scan

    plan = _plan(status="scan_queued")
    enqueued = []

    def fake_enqueue(db, user, request):
        enqueued.append(request)
        return plan

    monkeypatch.setattr(cleanup_scan, "enqueue_scan", fake_enqueue)
    request = PlanRequest(scope=MediaScope(source="all"), config=ToolConfig(kind="cleanup"))

    result = workflows.preview(request, _Session(), _user())

    assert result.code == 0
    assert result.data["status"] == "scan_queued"
    assert enqueued and enqueued[0].config.kind == "cleanup"
    assert no_worker == ["started"]


def test_retry_requeues_a_stopped_scan(monkeypatch, no_worker):
    from app.service import cleanup_scan

    plan = _plan(status="scan_stopped")
    queued = []
    monkeypatch.setattr(cleanup_scan, "queue_scan", lambda db, target: queued.append(target))
    monkeypatch.setattr(workflows, "get_plan", lambda db, owner_id, plan_id: plan)

    result = workflows.retry(plan.id, _Session(), _user())

    assert result.code == 0
    assert queued == [plan]
    assert no_worker == ["started"]


def test_retry_prepares_a_new_execution_for_a_finished_cleanup(monkeypatch, no_worker):
    from app.service import cleanup_execution

    plan = _plan(status="done", summary={"phase": "done"})
    prepared = _plan(status="queued")
    monkeypatch.setattr(cleanup_execution, "prepare_retry", lambda db, target: prepared)
    monkeypatch.setattr(workflows, "get_plan", lambda db, owner_id, plan_id: plan)

    result = workflows.retry(plan.id, _Session(), _user())

    assert result.code == 0
    assert result.data["status"] == "queued"


def test_selection_rejects_a_stale_preview(monkeypatch):
    plan = _plan(version=3)
    monkeypatch.setattr(workflows, "get_plan", lambda db, owner_id, plan_id: plan)
    session = _Session()
    request = CleanupSelectionRequest(version=2, item_ids=[1], selected=True)

    result = workflows.selection(plan.id, request, session, _user())

    assert result.code == 400
    assert result.msg == "预览已变化，请刷新"
    assert session.rollbacks == 1


def test_selection_removes_a_cancelled_item(monkeypatch):
    plan = _plan(version=3)
    monkeypatch.setattr(workflows, "get_plan", lambda db, owner_id, plan_id: plan)
    session = _Session(plan_items=[1], selections=[SimpleNamespace(item_id=1)])
    request = CleanupSelectionRequest(version=3, item_ids=[1], selected=False)

    result = workflows.selection(plan.id, request, session, _user())

    assert result.code == 0
    assert result.data["selected_count"] == 0
    assert session.added == []


def test_group_members_reports_a_missing_group(monkeypatch):
    plan = _plan()
    monkeypatch.setattr(workflows, "get_plan", lambda db, owner_id, plan_id: plan)

    result = workflows.group_members(plan.id, 7, db=_Session(), user=_user())

    assert result.code == 400
    assert result.msg == "分组不存在"



