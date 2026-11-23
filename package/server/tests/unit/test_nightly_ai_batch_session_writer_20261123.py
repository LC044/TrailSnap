"""Nightly watch 2026-11-23 - app/service/tasks/ai_runtime.py 的写者锁盲区。

AIBatchSession 是 AI 批处理专用的 SQLAlchemy Session 子类。在 SQLite 后端上，
所有写操作都必须先拿到进程级的 _sqlite_writer 锁，否则会与 API 进程争抢
SQLite 的单一写者而抛 database is locked。

本文件用真实 SQLite 引擎覆盖：

- 首次 _admit_writer 取得写者锁并记录等待耗时（happy）
- 重复 _admit_writer 不会二次加锁（edge）
- _release_writer 归还写者锁（happy）
- 非 SQLite 方言完全不参与写者锁（edge）
- execute 写语句会自动触发 _admit_writer（happy）
- commit / rollback / close 三条收尾路径都会归还写者锁（error）
"""

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, insert

from app.service.tasks import ai_runtime
from app.service.tasks.ai_runtime import AIBatchSession

pytestmark = [pytest.mark.smoke]

_METADATA = MetaData()
_PROBE = Table(
    "nightly_writer_probe",
    _METADATA,
    Column("id", Integer, primary_key=True),
    Column("value", String(32)),
)


def _lock_owned(lock):
    """RLock 在 CPython 上暴露 _is_owned()，用于确认锁是否仍被持有。"""
    probe = getattr(lock, "_is_owned", None)
    return probe() if callable(probe) else None


class _FakeDialect:
    name = "postgresql"


class _FakeBind:
    dialect = _FakeDialect()


@pytest.fixture()
def probe_engine(tmp_path):
    engine = create_engine(
        "sqlite:///" + (tmp_path / "ai.sqlite").as_posix(),
        connect_args={"check_same_thread": False},
    )
    _METADATA.create_all(engine)
    yield engine
    engine.dispose()


def test_admit_writer_takes_the_lock_and_records_the_wait(probe_engine):
    session = AIBatchSession(bind=probe_engine)
    assert session._writer_owned is False
    assert session.writer_wait_seconds == 0.0

    session._admit_writer()

    assert session._writer_owned is True
    assert session.writer_wait_seconds >= 0.0
    assert _lock_owned(ai_runtime._sqlite_writer) is True

    session._release_writer()


def test_admit_writer_is_idempotent_while_already_owned(probe_engine):
    session = AIBatchSession(bind=probe_engine)
    session._admit_writer()
    session._admit_writer()

    assert session._writer_owned is True
    assert _lock_owned(ai_runtime._sqlite_writer) is True

    session._release_writer()
    assert _lock_owned(ai_runtime._sqlite_writer) is False


def test_release_writer_returns_the_global_lock(probe_engine):
    session = AIBatchSession(bind=probe_engine)
    session._admit_writer()
    session._release_writer()

    assert session._writer_owned is False
    assert _lock_owned(ai_runtime._sqlite_writer) is False

    # 未持有时再次 release 是空操作，不应抛错。
    session._release_writer()
    assert session._writer_owned is False


def test_non_sqlite_dialect_never_takes_the_writer_lock():
    session = AIBatchSession()
    session.get_bind = lambda: _FakeBind()

    session._admit_writer()

    assert session._writer_owned is False
    assert session.writer_wait_seconds == 0.0


def test_execute_of_an_insert_admits_the_writer(probe_engine):
    session = AIBatchSession(bind=probe_engine)

    session.execute(insert(_PROBE).values(id=1, value="a"))

    assert session._writer_owned is True

    session.rollback()


def test_commit_counts_and_releases_the_writer(probe_engine):
    session = AIBatchSession(bind=probe_engine)
    session.execute(insert(_PROBE).values(id=1, value="a"))

    session.commit()

    assert session.commit_count == 1
    assert session.write_seconds >= 0.0
    assert session._writer_owned is False


def test_rollback_releases_the_writer(probe_engine):
    session = AIBatchSession(bind=probe_engine)
    session.execute(insert(_PROBE).values(id=1, value="a"))

    session.rollback()

    assert session._writer_owned is False


def test_close_releases_the_writer(probe_engine):
    session = AIBatchSession(bind=probe_engine)
    session.execute(insert(_PROBE).values(id=1, value="a"))

    session.close()

    assert session._writer_owned is False
