"""Nightly watch 2026-11-22 · app/service/cleanup_scan.py::process_scan 盲区。

process_scan 是「全量照片清理」后台 worker 的入口：它从任务 payload 里取出
plan id，另开一个会话在线程中执行 run_scan，从而不阻塞事件循环（停止/进度
仍然可用）。这条路径若在真实 worker 中跑偏，轻则任务永远不结束，
重则把失败写进错误的 plan。

本文件覆盖：
- 正常完成：返回 completed 与 plan_id（happy）
- 使用独立的会话执行，且能读到同一个数据库（happy）
- run_scan 抛错时错误向上抛出，不吞异常（error）
- payload 缺少 cleanup_scan_id 时立即失败（error）
- payload 中的 plan_id 非法时失败而不是静默完成（error）
"""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.service import cleanup_scan

pytestmark = [pytest.mark.smoke]


def _task(plan_id):
    return SimpleNamespace(payload={"cleanup_scan_id": str(plan_id)})


def test_process_scan_returns_the_scan_result(face_sqlite_session, monkeypatch):
    plan_id = uuid4()
    seen = {}

    def fake_run_scan(db, pid):
        seen["plan_id"] = pid
        seen["session"] = db
        return {"status": "completed", "plan_id": str(pid)}

    monkeypatch.setattr(cleanup_scan, "run_scan", fake_run_scan)

    result = asyncio.run(cleanup_scan.process_scan(_task(plan_id), face_sqlite_session))

    assert result == {"status": "completed", "plan_id": str(plan_id)}
    assert seen["plan_id"] == plan_id


def test_process_scan_runs_in_a_separate_session(face_sqlite_session, monkeypatch):
    seen = {}

    def fake_run_scan(db, pid):
        seen["session"] = db
        return {"status": "completed"}

    monkeypatch.setattr(cleanup_scan, "run_scan", fake_run_scan)

    asyncio.run(cleanup_scan.process_scan(_task(uuid4()), face_sqlite_session))

    assert seen["session"] is not face_sqlite_session
    assert seen["session"].bind is face_sqlite_session.get_bind()


def test_process_scan_propagates_a_scan_failure(face_sqlite_session, monkeypatch):
    def fake_run_scan(db, pid):
        raise RuntimeError("scan exploded")

    monkeypatch.setattr(cleanup_scan, "run_scan", fake_run_scan)

    with pytest.raises(RuntimeError, match="scan exploded"):
        asyncio.run(cleanup_scan.process_scan(_task(uuid4()), face_sqlite_session))


def test_process_scan_rejects_a_task_without_a_plan_id(face_sqlite_session, monkeypatch):
    monkeypatch.setattr(cleanup_scan, "run_scan", lambda db, pid: {"status": "completed"})
    task = SimpleNamespace(payload={})

    with pytest.raises(KeyError):
        asyncio.run(cleanup_scan.process_scan(task, face_sqlite_session))


def test_process_scan_rejects_a_malformed_plan_id(face_sqlite_session, monkeypatch):
    monkeypatch.setattr(cleanup_scan, "run_scan", lambda db, pid: {"status": "completed"})
    task = SimpleNamespace(payload={"cleanup_scan_id": "not-a-uuid"})

    with pytest.raises(ValueError):
        asyncio.run(cleanup_scan.process_scan(task, face_sqlite_session))
