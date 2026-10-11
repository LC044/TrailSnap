"""Compare basic processing on fixed media and an isolated SQLite WAL database.

Run from package/server with its Python environment. Never writes to the library.
"""
import argparse
import asyncio
import hashlib
import json
import statistics
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.core.config_manager import AppSettings
from app.db.base import Base
import app.db.models
from app.db.models.user import User
from app.db.models.photo import Photo
from app.db.models.task import Task, TaskType
from app.service import storage
from app.service.tasks.basic import BasicTaskStrategy
from app.service.tasks.metadata import ExtractMetadataStrategy


def select_files(root):
    files = list(root.rglob('*'))
    selected = []
    for extension, count in [('.jpg', 12), ('.mp4', 6), ('.png', 6)]:
        group = sorted((p for p in files if p.is_file() and p.suffix.lower() == extension),
                       key=lambda p: (p.stat().st_size, str(p)))
        if group:
            selected.extend(group[min(len(group) - 1, int(len(group) * (i + .5) / count))]
                            for i in range(min(count, len(group))))
    return selected


async def run_round(files, temporary, round_number):
    temporary = temporary / f'round-{round_number}'
    temporary.mkdir()
    engine = create_engine(f'sqlite:///{temporary / (str(round_number) + ".sqlite")}',
                           connect_args={'check_same_thread': False})
    @event.listens_for(engine, 'connect')
    def configure(connection, _):
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA busy_timeout=30000')
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False, autoflush=False)
    uid = uuid4()
    with sessions() as db:
        db.add(User(id=uid, username='benchmark', settings={}))
        db.commit()
    counts = {'sql': 0, 'commits': 0}
    @event.listens_for(engine, 'before_cursor_execute')
    def sql(*_):
        counts['sql'] += 1
    @event.listens_for(engine, 'commit')
    def commit(*_):
        counts['commits'] += 1
    config = AppSettings()
    config.filter.enable = False
    tasks = [Task(id=uuid4(), type=TaskType.PROCESS_BASIC, owner_id=uid,
                  payload={'file_path': str(p), 'user_id': str(uid)}) for p in files]
    lags = []
    async def heartbeat():
        previous = time.perf_counter()
        while True:
            await asyncio.sleep(.01)
            now = time.perf_counter()
            lags.append(max(0, now - previous - .01))
            previous = now
    heartbeat_task = asyncio.create_task(heartbeat())
    await asyncio.sleep(0)
    try:
        with ThreadPoolExecutor(max_workers=4) as pool, \
             patch.object(storage, '_get_storage_root', return_value=str(temporary / 'media')), \
             patch.object(storage, 'update_storage_root_cache'), \
             patch('app.core.config_manager.config_manager.get_user_config', return_value=config):
            worker = SimpleNamespace(thread_pool=pool,
                                     scan_status={'added': 0, 'processed_files': 0})
            basic = BasicTaskStrategy()
            start = time.perf_counter()
            # Fixed batch size/concurrency for both versions; scheduler tuning is separate.
            async def batch(chunk):
                with sessions() as db:
                    results = await basic.process_batch(worker, chunk, db)
                    assert all(r['status'] == 'completed' for r in results), results
                    await basic.handle_completion(worker, results, db)
                    db.commit()
            await asyncio.gather(*(batch(tasks[i:i+8]) for i in range(0, len(tasks), 8)))
            basic_seconds = time.perf_counter() - start
            with sessions() as db:
                photos = db.query(Photo).all()
                assert len(photos) == len(files)
                hashes_saved = sum(bool(p.md5) for p in photos)
                metadata_tasks = db.query(Task).filter(Task.type == TaskType.EXTRACT_METADATA).all()
                start = time.perf_counter()
                results = await ExtractMetadataStrategy().process_batch(worker, metadata_tasks, db)
                assert all(r['status'] == 'completed' for r in results), results
                db.commit()
                metadata_seconds = time.perf_counter() - start
                measured_counts = dict(counts)
                db.expire_all()
                assert all(p.processed_tasks.get('metadata') for p in photos)
            await asyncio.sleep(.02)
            preview_bytes = sum(p.stat().st_size for p in (temporary / 'media').rglob('*.webp'))
        return {'basic_seconds': basic_seconds, 'metadata_seconds': metadata_seconds,
                'pipeline_seconds': basic_seconds + metadata_seconds,
                'max_event_loop_lag_seconds': max(lags, default=0),
                'hashes_saved': hashes_saved, 'preview_bytes': preview_bytes, **measured_counts}
    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
        engine.dispose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rounds', type=int, default=3)
    args = parser.parse_args()
    files = select_files(args.root)
    assert files, 'No supported media'
    manifest = [{'path': str(p), 'size': p.stat().st_size, 'mtime_ns': p.stat().st_mtime_ns} for p in files]
    rows = []
    with tempfile.TemporaryDirectory(prefix='trailsnap-benchmark-') as directory:
        for i in range(args.rounds):
            row = asyncio.run(run_round(files, Path(directory), i))
            rows.append(row)
            print(json.dumps(row), flush=True)
    report = {'files': len(files), 'workers': 4, 'batch_size': 8,
              'manifest_sha256': hashlib.sha256(json.dumps(manifest).encode()).hexdigest(),
              'extensions': {ext: sum(p.suffix.lower() == ext for p in files) for ext in ('.jpg', '.mp4', '.png')},
              'rounds': rows, 'median': {key: statistics.median(row[key] for row in rows) for key in rows[0]}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
