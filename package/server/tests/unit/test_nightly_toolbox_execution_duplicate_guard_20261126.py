"""Nightly watch 2026-11-26 · app/service/toolbox_execution.py 的清理执行前置校验盲区。

覆盖率报告里 ``start_plan`` 的两条清理前置校验从未被执行：

- 「重复组必须至少保留一项」（第 64-65 行）：把重复组里的照片全删掉之后，
  剩下的那张就是最后一份副本，不能被一起删掉。
- 「没有需要执行的变更」（第 71-72 行）：勾选了候选但没有任何可执行项时，
  必须明确报错而不是静默创建一个空任务。

本文件用假的 session / 假的 plan 驱动 ``start_plan``，只验证校验分支。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.models.photo import Photo
from app.db.models.toolbox import ToolboxPlanItem
from app.schemas.toolbox import ExecuteRequest
from app.service import toolbox_execution


pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


class _Query:
    def __init__(self, rows=None):
        self._rows = list(rows or [])

    def filter(self, *args, **kwargs):
        return self

    def filter_by(self, **kwargs):
        return self

    def join(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def offset(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def update(self, *args, **kwargs):
        return 1

    def __iter__(self):
        return iter(self._rows)


class _Session:
    """按模型分派查询结果；ToolboxPlanItem 的多次查询按顺序出栈。"""

    def __init__(self, item_queries, photos=()):
        self.item_queries = list(item_queries)
        self.photos = list(photos)
        self.added = []
        self.commits = 0

    def query(self, model):
        if model is ToolboxPlanItem:
            rows = self.item_queries.pop(0) if self.item_queries else []
            return _Query(rows)
        if model is Photo or model is Photo.id:
            return _Query(self.photos)
        return _Query()

    def add(self, row):
        self.added.append(row)

    def flush(self):
        return None

    def commit(self):
        self.commits += 1

    def rollback(self):
        return None

    def refresh(self, obj):
        return None


def _user():
    return SimpleNamespace(id=uuid4(), settings={})


def _plan(**kwargs):
    base = {
        "id": uuid4(),
        "kind": "cleanup",
        "status": "preview",
        "version": 3,
        "request": {"config": {"cleanup_mode": "duplicate"}},
        "summary": {},
        "task_id": None,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(days=1),
        "finished_at": None,
        "stop_requested": False,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def _candidate(item_id, photo_id, group, md5):
    return SimpleNamespace(id=item_id, photo_id=photo_id, detail={"group": group, "md5": md5},
                           status="candidate", reason="", source="/a.jpg", target="/b.jpg",
                           fingerprint={})


def test_duplicate_group_must_keep_at_least_one_photo(monkeypatch):
    plan = _plan()
    monkeypatch.setattr(toolbox_execution, "get_plan", lambda db, owner_id, plan_id: plan)
    candidate = _candidate(1, uuid4(), "group-1", "md5-1")
    # 没有剩余的同 md5 照片：整组都要被删掉。
    session = _Session(item_queries=[[candidate]], photos=[])
    request = ExecuteRequest(version=3, confirmed=True, selected_items=[1])

    with pytest.raises(ValueError, match="重复组必须至少保留一项"):
        toolbox_execution.start_plan(session, _user(), plan.id, request)


def test_a_group_with_a_surviving_photo_may_be_cleaned(monkeypatch):
    plan = _plan()
    monkeypatch.setattr(toolbox_execution, "get_plan", lambda db, owner_id, plan_id: plan)
    candidate = _candidate(1, uuid4(), "group-1", "md5-1")
    survivor = SimpleNamespace(id=uuid4())
    session = _Session(item_queries=[[candidate], []], photos=[survivor])
    request = ExecuteRequest(version=3, confirmed=True, selected_items=[1])

    # 候选校验通过后，没有 ready 明细 -> 明确报错而不是空跑。
    with pytest.raises(ValueError, match="没有需要执行的变更"):
        toolbox_execution.start_plan(session, _user(), plan.id, request)


def test_the_candidate_must_be_selected_before_the_plan_can_start(monkeypatch):
    plan = _plan()
    monkeypatch.setattr(toolbox_execution, "get_plan", lambda db, owner_id, plan_id: plan)
    candidate = _candidate(1, uuid4(), "group-1", "md5-1")
    session = _Session(item_queries=[[candidate]], photos=[])
    request = ExecuteRequest(version=3, confirmed=True, selected_items=[])

    with pytest.raises(ValueError, match="请手动勾选范围内的清理候选"):
        toolbox_execution.start_plan(session, _user(), plan.id, request)
