"""Run AI batches with a thread-owned session and coordinated SQLite writes."""
import asyncio
import logging
import threading
import time

from sqlalchemy.orm import Session

from app.crud import task as crud_task

_sqlite_writer = threading.RLock()


class AIBatchSession(Session):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.write_seconds = 0.0
        self.commit_count = 0
        self.writer_wait_seconds = 0.0
        self._writer_owned = False

    def _admit_writer(self):
        if self.get_bind().dialect.name == 'sqlite' and not self._writer_owned:
            started = time.perf_counter()
            _sqlite_writer.acquire()
            self.writer_wait_seconds += time.perf_counter() - started
            self._writer_owned = True

    def _release_writer(self):
        if self._writer_owned:
            self._writer_owned = False
            _sqlite_writer.release()

    def execute(self, statement, *args, **kwargs):
        if any(getattr(statement, name, False) for name in ('is_insert', 'is_update', 'is_delete')):
            self._admit_writer()
        return super().execute(statement, *args, **kwargs)

    def flush(self, *args, **kwargs):
        if self.new or self.dirty or self.deleted:
            self._admit_writer()
        return super().flush(*args, **kwargs)

    def commit(self):
        started = time.perf_counter()
        try:
            super().commit()
            self.commit_count += 1
        finally:
            self.write_seconds += time.perf_counter() - started
            self._release_writer()

    def rollback(self):
        try:
            super().rollback()
        finally:
            self._release_writer()

    def close(self):
        try:
            super().close()
        finally:
            self._release_writer()


def run_ai_batch(bind, strategy, worker, task_ids):
    started = time.perf_counter()
    with AIBatchSession(bind=bind, expire_on_commit=False, autoflush=False) as db:
        tasks = crud_task.get_tasks_by_ids(db, task_ids)
        async def run():
            return await asyncio.wait_for(strategy.process_batch(worker, tasks, db), strategy.timeout)
        try:
            return asyncio.run(run())
        finally:
            logging.info(
                'AI batch timing: type=%s photos=%d total_ms=%.1f commit_ms=%.1f writer_wait_ms=%.1f commits=%d',
                strategy.resource_key, len(tasks), (time.perf_counter() - started) * 1000,
                db.write_seconds * 1000, db.writer_wait_seconds * 1000, db.commit_count,
            )
