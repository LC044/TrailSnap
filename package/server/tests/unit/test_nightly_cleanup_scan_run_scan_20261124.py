"""Nightly watch 2026-11-24 · app/service/cleanup_scan.py 的扫描收口与失败分支。

覆盖扫描显示 cleanup_scan.py 还剩几行未覆盖，都在 run_scan 的边界上：

- L294: 计划不存在或不在扫描中 -> 直接返回 completed（幂等重入）
- L316-L322: 扫描过程抛异常 -> 回滚、标记 scan_failed、写入错误摘要后继续抛出

失败分支必须把 plan 落成 scan_failed，否则前端会一直看到 scanning 而永远等不到
「已失败可重试」的提示。
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.service import cleanup_scan

pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


class _FakeDb:
    def __init__(self, plan=None):
        self.plan = plan
        self.commits = 0
        self.rollbacks = 0
        self.refreshed = 0

    def get(self, model, primary_key):
        return self.plan

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def refresh(self, obj):
        self.refreshed += 1


def _plan(**kwargs):
    base = {
        "id": uuid4(),
        "owner_id": uuid4(),
        "status": "scan_queued",
        "stop_requested": False,
        "summary": {"phase": "snapshot", "total": 0},
        "request": {"scope": {"source": "all"}, "config": {"kind": "cleanup"}},
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_run_scan_is_a_noop_for_an_unknown_plan():
    db = _FakeDb(plan=None)
    assert cleanup_scan.run_scan(db, uuid4()) == {"status": "completed"}


def test_run_scan_is_a_noop_for_a_finished_plan():
    plan = _plan(status="preview")
    db = _FakeDb(plan=plan)
    assert cleanup_scan.run_scan(db, plan.id) == {"status": "completed"}


def test_run_scan_marks_the_plan_as_failed_and_reraises(monkeypatch):
    plan = _plan()
    db = _FakeDb(plan=plan)

    def explode(*_args, **_kwargs):
        raise RuntimeError("扫描炸了")

    monkeypatch.setattr(cleanup_scan, "snapshot", explode)

    with pytest.raises(RuntimeError) as failure:
        cleanup_scan.run_scan(db, plan.id)

    assert str(failure.value) == "扫描炸了"
    assert plan.status == "scan_failed"
    assert plan.summary["error"] == "扫描炸了"
    assert db.rollbacks == 1
    assert db.commits >= 1
