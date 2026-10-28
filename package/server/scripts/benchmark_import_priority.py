"""Isolated before/after benchmark: real SQLite enqueue and real JPEG import.

Run with the server venv, --baseline to load the three modules from --ref.
CPU pressure is replayed, not a claim of end-to-end AI inference performance.
All files/databases/thumbnails are generated below a temporary directory.
"""
import argparse
import asyncio
import hashlib
import json
import logging
import os
import statistics
import subprocess
import sys
import tempfile
import time
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[3] / 'tests' / '.env.test')
os.environ.setdefault('DB_URL', os.environ.get('TS_DB_URL', 'sqlite:///:memory:'))
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from PIL import Image
from app.core.config_manager import AppSettings, config_manager
from app.db.base import Base
import app.db.models
from app.db.models.user import User
from app.db.models.photo import Photo
from app.db.models.task import Task, TaskType
from app.service import task_worker, storage
from app.service.tasks import scan
from app.service.disk_budget import disk_budget


def load_baseline(ref):
    modules = {}
    for name, path in [('limiter', 'adaptive_limiter.py'), ('worker', 'task_worker.py'),
                       ('scan', 'tasks/scan.py')]:
        source = subprocess.check_output(['git', 'show', f'{ref}:package/server/app/service/{path}'],
                                         encoding='utf-8')
        module = types.ModuleType(f'import_benchmark_{name}')
        sys.modules[module.__name__] = module
        if name == 'worker':
            source = source.replace('from app.service.adaptive_limiter import AdaptiveResourceLimiter', '')
            module.AdaptiveResourceLimiter = modules['limiter'].AdaptiveResourceLimiter
        exec(compile(source, f'<{ref}/{path}>', 'exec'), module.__dict__)
        modules[name] = module
    return modules['worker'], modules['scan']


def database(path, root):
    engine = create_engine(f'sqlite:///{path}', connect_args={'check_same_thread': False})
    @event.listens_for(engine, 'connect')
    def configure(connection, _):
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA busy_timeout=30000')
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False, autoflush=False)
    uid = uuid4()
    config = AppSettings()
    config.storage.external_directories = [str(root)]
    config.storage.photo_storage_path = str(path.parent / 'media')
    config.filter.enable = False
    with sessions() as db:
        db.add(User(id=uid, username=str(uid), settings=config.model_dump(mode='json')))
        db.commit()
    return engine, sessions, uid, config


def enqueue(scan_module, directory, root, paths):
    engine, sessions, uid, _ = database(directory / 'scan.sqlite', root)
    holds = []
    start_lock = [None]
    @event.listens_for(engine, 'before_cursor_execute')
    def begin_lock(_, __, statement, *args):
        if statement.lstrip().upper().startswith('UPDATE USERS'):
            start_lock[0] = time.perf_counter()
    @event.listens_for(engine, 'commit')
    def end_lock(_):
        if start_lock[0] is not None:
            holds.append(time.perf_counter() - start_lock[0])
            start_lock[0] = None
    start = time.perf_counter()
    with sessions() as db:
        asyncio.run(scan_module.ScanFolderStrategy()._create_tasks_for_new_files(
            str(uid), set(map(str, paths)), None, db))
        seconds = time.perf_counter() - start
        assert db.query(Task).count() == len(paths)
    engine.dispose()
    return {'seconds': seconds, 'max_writer_hold_seconds': max(holds),
            'total_writer_hold_seconds': sum(holds), 'files': len(paths)}


async def basic(worker_module, directory, root, paths):
    engine, sessions, uid, config = database(directory / 'basic.sqlite', root)
    worker = worker_module.TaskWorker()
    worker.system_pressure = {'cpu': 99.0, 'memory': 50.0}
    worker.import_priority_active = True
    worker._save_system_state = lambda *args: None
    worker._publish = lambda *args: None
    # Reproduce the persisted CPU=1 observed in the installed instance.
    worker.resource_limiters['cpu'] = worker._make_resource_limiter('cpu', 8, 1)
    changes = []
    worker.resource_limiters['cpu']._on_change = lambda _, limit, reason: changes.append([limit, reason])
    tasks = [Task(id=uuid4(), type=TaskType.PROCESS_BASIC, owner_id=uid, priority=99,
                  payload={'file_path': str(p), 'user_id': str(uid)}) for p in paths]
    with sessions() as db:
        db.add_all(tasks)
        db.commit()
    first = [None]
    start = time.perf_counter()
    async def consume():
        for _ in paths:
            item = await worker.result_queue.get()
            await worker._flush_results([item])
            assert item['status'] == 'completed', item
            if first[0] is None:
                first[0] = time.perf_counter() - start
            worker.result_queue.task_done()
    with ThreadPoolExecutor(max_workers=8) as pool, ThreadPoolExecutor(max_workers=12) as batches, \
         patch.object(worker_module, 'SessionLocal', sessions), \
         patch('app.service.task_worker.SessionLocal', sessions), \
         patch.object(storage, '_get_storage_root', return_value=str(directory / 'media')), \
         patch.object(storage, 'update_storage_root_cache'), \
         patch.object(config_manager, 'get_user_config', return_value=config):
        worker.thread_pool = pool
        worker.batch_pool = batches
        consumer = asyncio.create_task(consume())
        await asyncio.gather(*(worker.execute_batch_task_wrapper([
            {'id': t.id, 'type': t.type, 'priority': 99, 'resource_key': 'cpu'} for t in tasks[i:i+4]
        ], 'CPU') for i in range(0, len(tasks), 4)))
        await asyncio.wait_for(consumer, 120)
    seconds = time.perf_counter() - start
    with sessions() as db:
        assert db.query(Photo).count() == len(paths)
        assert db.query(Photo).filter(Photo.md5.is_(None)).count() == 0
    engine.dispose()
    return {'seconds': seconds, 'photos_per_second': len(paths) / seconds,
            'first_visible_seconds': first[0], 'files': len(paths), 'limit_changes': changes,
            'final_cpu_limit': worker.resource_limiters['cpu'].current_limit}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', action='store_true')
    parser.add_argument('--ref', default='5764ed6c')
    parser.add_argument('--scan-files', type=int, default=12000)
    parser.add_argument('--photos', type=int, default=96)
    parser.add_argument('--rounds', type=int, default=3)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    wm, sm = load_baseline(args.ref) if args.baseline else (task_worker, scan)
    disk_budget.configure(4)
    report = {'baseline': args.baseline, 'ref': args.ref, 'pressure_replay': {'cpu': 99, 'memory': 50},
              'scan': [], 'basic': [], 'jpeg_sha256': []}
    with tempfile.TemporaryDirectory(prefix='trailsnap-import-benchmark-') as temp:
        directory = Path(temp)
        root = directory / 'sources'
        root.mkdir()
        paths = [root / f'{i:06}.jpg' for i in range(args.scan_files)]
        for p in paths:
            p.touch()
        # Fixed pseudo-random pixels; no private media or production DB access.
        import numpy as np
        rng = np.random.default_rng(209)
        photo_paths = paths[:args.photos]
        for p in photo_paths:
            image = Image.fromarray(rng.integers(0, 256, (1600, 2400, 3), dtype=np.uint8))
            image.save(p, quality=88)
            report['jpeg_sha256'].append(hashlib.sha256(p.read_bytes()).hexdigest())
        for i in range(args.rounds):
            run = directory / str(i)
            run.mkdir()
            report['scan'].append(enqueue(sm, run, root, paths))
            report['basic'].append(asyncio.run(basic(wm, run, root, photo_paths)))
            print(json.dumps({'round': i, 'scan': report['scan'][-1], 'basic': report['basic'][-1]}), flush=True)
    report['median'] = {kind: {key: statistics.median(r[key] for r in report[kind])
                              for key in report[kind][0] if isinstance(report[kind][0][key], (int, float))}
                        for kind in ('scan', 'basic')}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
