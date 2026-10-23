"""REQ-163: real directory/SQLite contracts for removal and reconciliation."""
import asyncio
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pathlib import Path

from app.core.config_manager import config_manager
from app.db.models.album import Album, AlbumPhoto
from app.db.models.photo import Photo, FileType
from app.db.models.task import Task, TaskStatus, TaskType
from app.db.models.user import User
from app.service import gallery_sync
from app.service.tasks.scan import ScanFolderStrategy
from app.service.tasks.basic import BasicTaskStrategy

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


@pytest.fixture
def library(face_sqlite_session, tmp_path, monkeypatch):
    db = face_sqlite_session
    # The production connection enables cascades too.
    db.connection().exec_driver_sql('PRAGMA foreign_keys=ON')
    root = tmp_path / 'family'
    root.mkdir()
    sibling = tmp_path / 'family2'
    sibling.mkdir()
    user = User(id=uuid4(), username=str(uuid4()), settings={
        'storage': {'external_directories': [str(root), str(sibling)],
                    'photo_storage_path': str(tmp_path / 'managed')},
        'filter': {'enable': False},
    })
    db.add(user)
    db.commit()
    monkeypatch.setattr('app.service.user_storage.write_user_config', lambda *args: None)
    monkeypatch.setattr('app.service.storage.delete_thumbnails', lambda *args: None)
    config_manager._user_cache.clear()
    yield db, user, root, sibling
    config_manager._user_cache.clear()


def photo(db, user, path):
    row = Photo(id=uuid4(), owner_id=user.id, file_path=str(path), filename=path.name,
                file_type=FileType.image, photo_time=datetime.now())
    db.add(row)
    db.commit()
    return row


def worker():
    return SimpleNamespace(scan_status={'message': '', 'total_files': 0, 'deleted': 0, 'added': 0, 'processed_files': 0})


def scan(db, user):
    return asyncio.run(ScanFolderStrategy().process(worker(), SimpleNamespace(
        payload={'user_id': str(user.id), 'reconcile': True}), db))


def test_remove_normalized_path_cascades_and_preserves_originals_and_other_users(library):
    db, user, root, sibling = library
    source = root / 'one.jpg'
    source.write_bytes(b'original')
    doomed = photo(db, user, source)
    doomed_id = doomed.id
    survivor = photo(db, user, sibling / 'two.jpg')
    other = User(id=uuid4(), username=str(uuid4()), settings={})
    db.add(other)
    db.commit()
    other_photo = photo(db, other, source)
    album = Album(id=uuid4(), owner_id=user.id, name='album', num_photos=1)
    db.add(album)
    db.flush()
    db.add(AlbumPhoto(album_id=album.id, photo_id=doomed.id))
    task = Task(type=TaskType.PROCESS_BASIC, payload={'file_path': str(source), 'user_id': str(user.id)})
    db.add(task)
    db.commit()
    result = gallery_sync.remove_gallery(db, user.id, str(root / '..' / root.name) + '/')
    assert result['deleted_photos'] == 1
    assert str(root) not in result['external']
    assert db.get(Photo, doomed_id) is None
    assert db.get(Photo, survivor.id) is not None
    assert db.get(Photo, other_photo.id) is not None
    assert db.query(AlbumPhoto).count() == 0
    db.refresh(album)
    assert album.num_photos == 0
    db.refresh(task)
    assert task.status == TaskStatus.CANCELLED
    assert source.read_bytes() == b'original'
    assert gallery_sync.remove_gallery(db, user.id, str(root))['deleted_photos'] == 0


def test_remove_retries_after_cleanup_failure(library, monkeypatch):
    db, user, root, _ = library
    row_id = photo(db, user, root / 'one.jpg').id
    original = gallery_sync.delete_index
    monkeypatch.setattr(gallery_sync, 'delete_index', lambda *args: (_ for _ in ()).throw(RuntimeError('interrupted')))
    with pytest.raises(RuntimeError):
        gallery_sync.remove_gallery(db, user.id, str(root))
    db.rollback()
    assert str(root) not in gallery_sync.external_roots(db.get(User, user.id))
    monkeypatch.setattr(gallery_sync, 'delete_index', original)
    assert gallery_sync.remove_gallery(db, user.id, str(root))['deleted_photos'] == 1
    assert db.get(Photo, row_id) is None


@pytest.mark.parametrize('target', ['relative', 'disk', 'managed', 'parent', 'child'])
def test_remove_rejects_unsafe_scope(library, target):
    db, user, root, _ = library
    targets = {'relative': '.', 'disk': str(root.anchor), 'managed': gallery_sync.managed_roots(user)[0],
               'parent': str(root.parent), 'child': str(root / '2026')}
    with pytest.raises(ValueError):
        gallery_sync.remove_gallery(db, user.id, targets[target])
    db.rollback()
    assert str(root) in gallery_sync.external_roots(user)


def test_full_scan_adds_missing_deletes_stale_and_orphans_and_deduplicates_tasks(library):
    db, user, root, sibling = library
    (root / 'new.jpg').write_bytes(b'new')
    (sibling / 'another.png').write_bytes(b'new')
    missing_id = photo(db, user, root / 'missing.jpg').id
    orphan_id = photo(db, user, root.parent / 'removed' / 'old.jpg').id
    managed = photo(db, user, Path(gallery_sync.managed_roots(user)[0]) / 'uploads' / 'keep.jpg')
    managed_id = managed.id
    result = scan(db, user)
    assert result == {'new_files': 2, 'deleted_files': 2}
    assert db.get(Photo, missing_id) is None
    assert db.get(Photo, orphan_id) is None
    assert db.get(Photo, managed_id) is not None
    tasks = db.query(Task).filter(Task.type == TaskType.PROCESS_BASIC).all()
    assert {t.payload['file_path'] for t in tasks} == {str(root / 'new.jpg'), str(sibling / 'another.png')}
    scan(db, user)
    assert db.query(Task).filter(Task.type == TaskType.PROCESS_BASIC).count() == 2


def test_empty_config_still_cleans_orphans(library):
    db, user, root, _ = library
    pid = photo(db, user, root / 'old.jpg').id
    user.settings = dict(user.settings, storage=dict(user.settings['storage'], external_directories=[]))
    db.commit()
    assert scan(db, user)['deleted_files'] == 1
    assert db.get(Photo, pid) is None


@pytest.mark.parametrize('offline', [True, False])
def test_failed_root_preserves_records_and_other_roots_continue(library, monkeypatch, offline):
    db, user, root, sibling = library
    nested = root / 'nested'
    nested.mkdir()
    row_id = photo(db, user, nested / 'old.jpg').id
    gone_id = photo(db, user, sibling / 'gone.jpg').id
    (sibling / 'new.jpg').write_bytes(b'new')
    from app.service.tasks import scan as scanner
    original = scanner.os.scandir
    def failure(path):
        if str(path) == str(root if offline else nested):
            raise PermissionError('offline or unreadable')
        return original(path)
    monkeypatch.setattr(scanner.os, 'scandir', failure)
    result = scan(db, user)
    assert db.get(Photo, row_id) is not None
    assert db.get(Photo, gone_id) is None
    assert result['new_files'] == 1
    assert result['skipped_roots'][0]['path'] == str(root)


def test_directory_removed_during_scan_cannot_queue_imports(library, monkeypatch):
    db, user, root, _ = library
    (root / 'new.jpg').write_bytes(b'new')
    from app.service.tasks import scan as scanner
    original = scanner.scan_directory_recursive
    removed = False
    def remove_while_reading(path, *args, **kwargs):
        nonlocal removed
        result = original(path, *args, **kwargs)
        if not removed:
            removed = True
            from sqlalchemy.orm import Session
            with Session(bind=db.get_bind()) as other:
                gallery_sync.remove_gallery(other, user.id, str(root))
        return result
    db.rollback()
    monkeypatch.setattr(scanner, 'scan_directory_recursive', remove_while_reading)
    scan(db, user)
    assert db.query(Task).filter(Task.type == TaskType.PROCESS_BASIC).count() == 0


def test_late_completion_is_skipped_after_removal(library, monkeypatch):
    db, user, root, _ = library
    source = root / 'one.jpg'
    source.write_bytes(b'original')
    uid = user.id
    gallery_sync.remove_gallery(db, uid, str(root))
    item = {'task_id': uuid4(), 'status': TaskStatus.COMPLETED,
            'result': {'photo_create_data': {'user_id': str(uid), 'photo_id': uuid4(), 'file_path': str(source)}}}
    asyncio.run(BasicTaskStrategy().handle_completion(worker(), [item], db))
    db.commit()
    assert item['result']['status'] == 'skipped'
    assert db.query(Photo).count() == 0
    assert db.query(Task).count() == 0


def test_import_completion_and_second_scan_converge_without_duplicates(library):
    from app.schemas.photo import PhotoCreate
    from app.schemas.metadata import PhotoMetadataCreate
    db, user, root, _ = library
    path = root / 'one.jpg'
    path.write_bytes(b'original')
    assert scan(db, user)['new_files'] == 1
    queued = db.query(Task).filter(Task.type == TaskType.PROCESS_BASIC).one()
    pid = uuid4()
    item = {'task_id': queued.id, 'status': TaskStatus.COMPLETED, 'result': {'photo_create_data': {
        'user_id': str(user.id), 'photo_id': pid, 'file_path': str(path),
        'photo': PhotoCreate(filename=path.name, file_type=FileType.image, photo_time=datetime.now(), size=8),
        'metadata': PhotoMetadataCreate(exif_info='{}'),
    }}}
    asyncio.run(BasicTaskStrategy().handle_completion(worker(), [item], db))
    db.delete(queued)
    db.commit()
    assert db.query(Photo).count() == 1
    assert scan(db, user) == {'new_files': 0, 'deleted_files': 0}
    assert db.query(Task).filter(Task.type == TaskType.PROCESS_BASIC).count() == 0
    assert path.read_bytes() == b'original'


@pytest.mark.parametrize('status, full, new_root, reuse', [
    (TaskStatus.PENDING, False, False, True),
    (TaskStatus.PROCESSING, False, False, False),
    (TaskStatus.PROCESSING, True, True, False),
    (TaskStatus.PROCESSING, True, False, True),
])
def test_scan_request_never_reuses_a_narrower_running_scan(library, monkeypatch, status, full, new_root, reuse):
    from app.service.task_manager import TaskManager
    db, user, root, sibling = library
    old_payload = {'user_id': str(user.id)}
    old_payload.update({'reconcile': True} if full else {'scan_roots': [str(root)]})
    old = Task(type=TaskType.SCAN_FOLDER, payload=old_payload, status=status)
    db.add(old)
    db.commit()
    old_id = old.id
    manager = object.__new__(TaskManager)
    monkeypatch.setattr(manager, 'start_worker_if_needed', lambda: None)
    monkeypatch.setattr(manager, 'publish_task_update', lambda *args, **kwargs: None)
    payload = {'user_id': str(user.id)}
    payload.update({'scan_roots': [str(sibling)]} if new_root else {'reconcile': True})
    result = manager.add_task(db, TaskType.SCAN_FOLDER, payload, owner_id=user.id)
    assert (result.id == old_id) is reuse
    if reuse:
        assert result.payload['reconcile'] is True
        assert not result.payload.get('scan_roots')


def test_scan_all_api_enforces_admin_and_targets_selected_user(library, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import settings
    db, user, _, _ = library
    app = FastAPI()
    app.include_router(settings.router)
    app.dependency_overrides[settings.get_db] = lambda: db
    app.dependency_overrides[settings.get_current_user] = lambda: user
    user.is_superuser = False
    db.commit()
    calls = []
    manager = SimpleNamespace(add_task=lambda *args, **kwargs: (calls.append((args, kwargs)) or SimpleNamespace(id=uuid4())))
    monkeypatch.setattr(settings.TaskManager, 'get_instance', lambda: manager)
    with TestClient(app) as client:
        assert client.post('/directories/scan-all', json={}).status_code == 403
        user.is_superuser = True
        db.commit()
        response = client.post('/directories/scan-all', json={'user_id': str(user.id)})
        assert response.status_code == 200
        assert response.json()['code'] == 0
        assert calls[0][0][2] == {'user_id': str(user.id), 'reconcile': True}


def test_completed_scan_summary_is_available_through_task_api(library):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import tasks
    db, user, root, _ = library
    summary = {'new_files': 3, 'deleted_files': 2, 'skipped_roots': [{'path': str(root), 'reason': 'offline'}]}
    task = Task(type=TaskType.SCAN_FOLDER, owner_id=user.id, status=TaskStatus.COMPLETED, result=summary)
    db.add(task)
    db.commit()
    app = FastAPI()
    app.include_router(tasks.router, prefix='/tasks')
    app.dependency_overrides[tasks.get_db] = lambda: db
    with TestClient(app) as client:
        response = client.get(f'/tasks/{task.id}')
        assert response.status_code == 200
        assert response.json()['data']['result'] == summary
