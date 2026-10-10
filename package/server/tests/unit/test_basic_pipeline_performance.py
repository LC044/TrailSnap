"""SQLite integration contracts for the import pipeline, without services."""
import asyncio
import threading
import time
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event

from app.core.config_manager import AppSettings
from app.db.models.album import Album, AlbumPhoto
from app.db.models.photo import Photo, FileType
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.task import Task, TaskType
from app.db.models.user import User
from app.service.tasks import basic, metadata

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def seed(db, count=6):
    uid = uuid4()
    db.add(User(id=uid, username=str(uid), settings={}))
    photos = [Photo(id=uuid4(), owner_id=uid, filename=f'{i}.jpg', file_path=f'/media/{i}.jpg',
                    file_type=FileType.image, width=320, height=240, processed_tasks={})
              for i in range(count)]
    db.add_all(photos)
    db.commit()
    return uid, photos


def test_metadata_batch_owns_thread_session_and_commits_once(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    uid, photos = seed(db)
    album = Album(owner_id=uid, name='All imported', type='conditional', condition={'time_range': {}})
    db.add(album)
    db.commit()
    ids = [p.id for p in photos]
    commits, threads = [], []
    event.listen(db.get_bind(), 'commit', lambda _: commits.append(True))
    main_thread = threading.get_ident()
    def extract(path, pid):
        threads.append(threading.get_ident())
        time.sleep(.025)
        return {'success': True, 'meta': {'exif_info': {'Make': 'Camera'}, 'photo_time': datetime(2020, 1, 1)}}
    monkeypatch.setattr(metadata, 'rebuild_metadata_cpu_job', extract)
    tasks = [Task(id=uuid4(), type=TaskType.EXTRACT_METADATA, payload={'photo_id': str(pid)}) for pid in ids]
    async def run():
        ticks = 0
        done = False
        async def heartbeat():
            nonlocal ticks
            while not done:
                ticks += 1
                await asyncio.sleep(.005)
        heartbeat_task = asyncio.create_task(heartbeat())
        try:
            results = await metadata.ExtractMetadataStrategy().process_batch(None, tasks, db)
        finally:
            done = True
            await heartbeat_task
        assert ticks >= 5
        return results
    results = asyncio.run(run())
    assert all(r['status'] == 'completed' for r in results)
    assert len(commits) == 1
    assert all(thread != main_thread for thread in threads)
    db.expire_all()
    assert all(db.get(Photo, pid).processed_tasks['metadata'] for pid in ids)
    assert db.query(PhotoMetadata).count() == len(ids)
    assert db.query(AlbumPhoto).filter(AlbumPhoto.album_id == album.id).count() == len(ids)
    assert db.get(Album, album.id).num_photos == len(ids)
    assert db.get(Album, album.id).cover_id in ids


def test_basic_completion_preserves_hash_and_reuses_metadata(face_sqlite_session):
    from app.schemas.photo import PhotoCreate
    from app.schemas.metadata import PhotoMetadataCreate
    db = face_sqlite_session
    uid, photos = seed(db, count=1)
    pid = photos[0].id
    data = {'photo_id': pid, 'file_path': photos[0].file_path, 'user_id': str(uid),
            'photo': PhotoCreate(filename='0.jpg', file_type=FileType.live_photo, size=123,
                                 width=320, height=240, md5='a'*32),
            'metadata': PhotoMetadataCreate(exif_info='{"Make":"Camera"}'),
            'is_pre_created': True, 'color_info': None}
    worker = SimpleNamespace(scan_status={'added': 0, 'processed_files': 0})
    items = [{'status': 'completed', 'result': {'photo_create_data': data}}] * 2
    asyncio.run(basic.BasicTaskStrategy().handle_completion(worker, items, db))
    db.commit()
    assert db.get(Photo, pid).md5 == 'a'*32
    assert db.get(Photo, pid).file_type == FileType.live_photo
    assert db.query(PhotoMetadata).filter(PhotoMetadata.photo_id == pid).count() == 1


def test_basic_precheck_is_one_query_for_a_batch(face_sqlite_session, monkeypatch, tmp_path):
    db = face_sqlite_session
    uid, photos = seed(db)
    paths = []
    for i, photo in enumerate(photos):
        path = tmp_path / f'{i}.jpg'
        path.touch()
        photo.file_path = str(path)
        paths.append(str(path))
    db.commit()
    expected_ids = {p.id for p in photos}
    tasks = [Task(id=uuid4(), type=TaskType.PROCESS_BASIC, owner_id=uid,
                  payload={'user_id': str(uid), 'file_path': path}) for path in paths]
    config = AppSettings()
    config.filter.enable = False
    monkeypatch.setattr(basic.config_manager, 'get_user_config', lambda *_: config)
    monkeypatch.setattr(basic.storage, '_get_storage_root', lambda *_: str(tmp_path))
    def cpu(jobs):
        return [dict(success=True, file_name='photo.jpg', width=320, height=240, size=1,
                     duration=None, meta={'photo_time': None, 'exif_info': None}) for _ in jobs]
    monkeypatch.setattr(basic, 'process_basic_cpu_batch_job', cpu)
    queries = []
    event.listen(db.get_bind(), 'before_cursor_execute', lambda conn, cursor, sql, *args: queries.append(sql))
    worker = SimpleNamespace(thread_pool=None)
    results = asyncio.run(basic.BasicTaskStrategy().process_batch(worker, tasks, db))
    assert {r['result']['photo_create_data']['photo_id'] for r in results} == expected_ids
    assert all(r['result']['photo_create_data']['is_pre_created'] for r in results)
    assert len(queries) == 1
