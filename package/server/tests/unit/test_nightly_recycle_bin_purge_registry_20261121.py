"""夜间盲区补测：回收站清理任务注册表（TTL 回收 / 归属隔离 / 进度载荷）。

覆盖 app/service/recycle_bin_purge.py 中此前未被任何单测按名引用的
``_reap_expired_locked`` / ``active_job_for_user`` / ``get_job``。
"""
import time
from uuid import uuid4

import pytest

from app.service import recycle_bin_purge as rbp

pytestmark = [pytest.mark.smoke, pytest.mark.regression]


@pytest.fixture(autouse=True)
def _clean_registry():
    """作业注册表是进程级全局状态，用例前后都要清空，避免互相污染。"""
    with rbp._lock:
        rbp._jobs.clear()
    yield
    with rbp._lock:
        rbp._jobs.clear()


def _job(**kwargs):
    defaults = dict(id=str(uuid4()), user_id=str(uuid4()), total=10)
    defaults.update(kwargs)
    return rbp.PurgeJob(**defaults)


def test_reap_drops_only_finished_jobs_older_than_ttl():
    """只有「已完成且早于 TTL」的作业会被回收，进行中与新完成的作业必须保留。"""
    stale = _job(status="completed", finished_at=time.time() - rbp._JOB_TTL_SECONDS - 1)
    fresh = _job(status="completed", finished_at=time.time() - 1)
    running = _job(status="running", finished_at=None)

    with rbp._lock:
        rbp._jobs.update({stale.id: stale, fresh.id: fresh, running.id: running})
        rbp._reap_expired_locked()
        remaining = set(rbp._jobs)

    assert stale.id not in remaining
    assert fresh.id in remaining
    assert running.id in remaining


def test_active_job_for_user_reports_only_in_flight_jobs():
    """同一用户只允许一个在途清理任务，已完成任务不能挡住下一次清理。"""
    user = uuid4()
    pending = _job(user_id=str(user), status="pending")
    done = _job(user_id=str(user), status="completed", finished_at=time.time())
    other = _job(user_id=str(uuid4()), status="running")

    with rbp._lock:
        rbp._jobs.update({pending.id: pending, done.id: done, other.id: other})

    assert rbp.active_job_for_user(user) is pending
    assert rbp.active_job_for_user(uuid4()) is None


def test_get_job_is_scoped_to_its_owner():
    """作业 ID 不得跨用户读取，避免拿到别人的清理进度。"""
    user = uuid4()
    job = _job(user_id=str(user))
    with rbp._lock:
        rbp._jobs[job.id] = job

    assert rbp.get_job(job.id, user) is job
    assert rbp.get_job(job.id, uuid4()) is None
    assert rbp.get_job("does-not-exist", user) is None


def test_purge_job_progress_payload_reports_percentage():
    """进度载荷按已处理比例计算；总数为 0 时完成态仍然报 100%。"""
    running = _job(total=200, processed=50, status="running")
    payload = running.to_dict()
    assert payload["progress"] == 25
    assert payload["job_id"] == running.id
    assert payload["status"] == "running"
    assert payload["total"] == 200

    done = _job(total=0, processed=0, status="completed")
    assert done.to_dict()["progress"] == 100
