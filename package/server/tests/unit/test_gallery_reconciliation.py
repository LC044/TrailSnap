"""REQ-163: real directory/SQLite contracts for removal and reconciliation."""
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pathlib import Path

from app.core.config_manager import config_manager
from app.db.models.album import Album, AlbumPhoto
from app.db.models.index_log import IndexLog
from app.db.models.photo import Photo, FileType
from app.db.models.task import Task, TaskStatus, TaskType
from app.db.models.user import User
from app.service import gallery_sync
from app.service.gallery_availability import directory_identity
from app.service.gallery_watch import GalleryWatch
from app.service.task_manager import TaskManager
from app.service.tasks.scan import ScanFolderStrategy
from app.service.tasks.basic import BasicTaskStrategy
from app.service.tasks import gallery_removal

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
    (sibling / 'two.jpg').write_bytes(b'keep')
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
    remaining, removal = gallery_sync.queue_gallery_removal(db, user.id, str(root / '..' / root.name) + '/')
    assert str(root) not in remaining
    assert db.get(Photo, doomed_id) is not None
    assert gallery_sync.queue_gallery_removal(db, user.id, str(root))[1].id == removal.id
    assert scan(db, user)['deleted_files'] == 0
    assert db.get(Photo, doomed_id) is not None
    removal.status = TaskStatus.PROCESSING
    db.commit()
    assert gallery_removal.cleanup_gallery(db, removal.id) == {'deleted_photos': 1}
    assert db.get(Photo, doomed_id) is None
    assert db.get(Photo, survivor.id) is not None
    assert db.get(Photo, other_photo.id) is not None
    assert db.query(AlbumPhoto).count() == 0
    db.refresh(album)
    assert album.num_photos == 0
    db.refresh(task)
    assert task.status == TaskStatus.CANCELLED
    assert source.read_bytes() == b'original'
    assert removal.processed_items == removal.total_items == 1


def test_remove_retries_after_cleanup_failure(library, monkeypatch):
    db, user, root, _ = library
    doomed_ids = {photo(db, user, root / name).id for name in ('one.jpg', 'two.jpg')}
    _, task = gallery_sync.queue_gallery_removal(db, user.id, str(root))
    task.status = TaskStatus.PROCESSING
    db.commit()
    monkeypatch.setattr(gallery_removal, 'DELETE_CHUNK_SIZE', 1)
    clean_thumbnails = gallery_removal.clean_thumbnails

    def interrupt(_owner, photo_ids):
        if photo_ids:
            raise RuntimeError('interrupted after commit')

    monkeypatch.setattr(gallery_removal, 'clean_thumbnails', interrupt)
    with pytest.raises(RuntimeError, match='after commit'):
        gallery_removal.cleanup_gallery(db, task.id)
    db.rollback()
    assert task.processed_items == 1
    assert str(root) not in gallery_sync.external_roots(db.get(User, user.id))
    task.status = TaskStatus.FAILED
    db.commit()
    _, retry = gallery_sync.queue_gallery_removal(db, user.id, str(root))
    assert retry.id == task.id
    retry.status = TaskStatus.PROCESSING
    db.commit()
    monkeypatch.setattr(gallery_removal, 'clean_thumbnails', clean_thumbnails)
    assert gallery_removal.cleanup_gallery(db, task.id) == {'deleted_photos': 2}
    assert db.query(Photo).count() == 0
    assert {row.photo_id for row in db.query(IndexLog)} == doomed_ids
    assert db.query(IndexLog).count() == 2


@pytest.mark.parametrize('target', ['relative', 'disk', 'managed', 'parent', 'child'])
def test_remove_rejects_unsafe_scope(library, target):
    db, user, root, _ = library
    targets = {'relative': '.', 'disk': str(root.anchor), 'managed': gallery_sync.managed_roots(user)[0],
               'parent': str(root.parent), 'child': str(root / '2026')}
    with pytest.raises(ValueError):
        gallery_sync.queue_gallery_removal(db, user.id, targets[target])
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


def watched_scan(db, user, root, folders, identity, *, mounts=None, unverified=()):
    scopes = {str(folder): {'root': str(root), 'identity': list(identity),
                            'mounts': mounts or {}, 'unverified': list(unverified)} for folder in folders}
    task = SimpleNamespace(payload={'user_id': str(user.id), 'scan_roots': list(scopes), 'watch_scopes': scopes})
    return asyncio.run(ScanFolderStrategy().process(worker(), task, db))


def test_watched_move_cleans_old_index_and_queues_destination_once(library, monkeypatch):
    db, user, root, _ = library
    source_dir, dest_dir = root / 'source', root / 'destination'
    source_dir.mkdir()
    dest_dir.mkdir()
    original = source_dir / 'old.jpg'
    original.write_bytes(b'photo')
    old_id = photo(db, user, original).id
    destination = dest_dir / 'new.jpg'
    original.rename(destination)
    thumbnails_deleted = []
    monkeypatch.setattr('app.service.storage.delete_thumbnails',
                        lambda owner, photo_id: thumbnails_deleted.append(photo_id))

    identity = directory_identity(str(root))
    assert watched_scan(db, user, root, [source_dir, dest_dir], identity) == {'new_files': 1, 'deleted_files': 1}
    watched_scan(db, user, root, [source_dir, dest_dir], identity)
    db.expire_all()
    assert db.get(Photo, old_id) is None
    assert thumbnails_deleted == [old_id]
    queued = db.query(Task).filter(Task.type == TaskType.PROCESS_BASIC).one()
    assert queued.payload['file_path'] == str(destination)
    assert destination.read_bytes() == b'photo'


def test_watched_scan_preserves_records_when_mount_changes_during_enumeration(library, monkeypatch):
    from app.service.tasks import scan as scanner

    db, user, root, _ = library
    old_id = photo(db, user, root / 'indexed.jpg').id
    identity = directory_identity(str(root))
    observations = iter([identity, (identity[0] + 1, identity[1])])
    monkeypatch.setattr(scanner, 'directory_identity', lambda path: next(observations))

    result = watched_scan(db, user, root, [root], identity)
    assert result['deleted_files'] == 0
    assert result['skipped_roots'][0]['path'] == str(root)
    assert db.get(Photo, old_id) is not None


@pytest.mark.parametrize('disconnect_during_scan', [False, True])
def test_watched_scan_protects_disconnected_submount_and_reconciles_other_files(
    library, monkeypatch, disconnect_during_scan,
):
    from app.service.tasks import scan as scanner

    db, user, root, _ = library
    child = root / 'mount'
    child.mkdir()
    (child / 'placeholder.jpg').touch()
    (root / 'new.jpg').touch()
    old_id = photo(db, user, child / 'indexed.jpg').id
    deleted_id = photo(db, user, root / 'deleted.jpg').id
    mount_key = gallery_sync.path_key(str(child))
    mounts = {mount_key: ['nas:/gallery', 'nfs']}
    observations = iter([mounts if disconnect_during_scan else {}, {}])
    monkeypatch.setattr(scanner, 'mount_inventory', lambda: next(observations))

    result = watched_scan(db, user, root, [root], directory_identity(str(root)), mounts=mounts)
    assert result['deleted_files'] == 1
    assert result['skipped_roots'][0]['path'] == mount_key
    assert db.get(Photo, old_id) is not None
    assert db.get(Photo, deleted_id) is None
    assert db.query(Task).filter(Task.type == TaskType.PROCESS_BASIC).one().payload['file_path'] == str(root / 'new.jpg')


def test_watched_scan_preserves_unverified_legacy_files_in_nonempty_placeholder(library):
    db, user, root, _ = library
    (root / 'placeholder.txt').touch()
    missing = root / 'indexed.jpg'
    old_id = photo(db, user, missing).id
    result = watched_scan(
        db, user, root, [root], directory_identity(str(root)), unverified=[gallery_sync.path_key(str(missing))],
    )
    assert result['deleted_files'] == 0
    assert db.get(Photo, old_id) is not None


def test_startup_import_preserves_missing_gallery_records(library):
    db, user, root, sibling = library
    old_id = photo(db, user, root / 'indexed.jpg').id
    (sibling / 'new.jpg').write_bytes(b'new')
    task = SimpleNamespace(payload={'import_only': True})
    result = asyncio.run(ScanFolderStrategy().process(worker(), task, db))
    assert result == {'new_files': 1, 'deleted_files': 0}
    assert db.get(Photo, old_id) is not None
    queued = db.query(Task).filter(Task.type == TaskType.PROCESS_BASIC).one()
    assert queued.payload['file_path'] == str(sibling / 'new.jpg')


def test_watched_scan_respects_mixed_case_excluded_directory(library):
    db, user, root, _ = library
    excluded = root / '@eaDir'
    excluded.mkdir()
    (excluded / 'preview.jpg').write_bytes(b'preview')
    watch = GalleryWatch(str(root))
    watch.mark(str(excluded))

    result = watched_scan(db, user, root, watch.dirty, directory_identity(str(root)))
    assert result == {'new_files': 0, 'deleted_files': 0}
    assert db.query(Task).filter(Task.type == TaskType.PROCESS_BASIC).count() == 0


@pytest.mark.parametrize('status', [TaskStatus.PENDING, TaskStatus.PROCESSING])
def test_automatic_scan_waits_for_manual_scan(library, monkeypatch, status):
    db, user, root, _ = library
    manager = TaskManager()
    monkeypatch.setattr(manager, 'start_worker_if_needed', lambda: None)
    task = manager.add_task(db, TaskType.SCAN_FOLDER, {'user_id': str(user.id), 'scan_roots': [str(root)]})
    task.status = status
    db.commit()
    assert not manager.try_enqueue_gallery_scan(db, {})
    assert not manager.try_enqueue_gallery_scan(db, {'import_only': True})
    assert not manager.try_enqueue_gallery_scan(db, {'user_id': str(user.id), 'scan_roots': [str(root)]})
    assert db.query(Task).filter(Task.type == TaskType.SCAN_FOLDER).count() == 1
    task.status = TaskStatus.COMPLETED
    db.commit()
    assert manager.try_enqueue_gallery_scan(db, {'import_only': True})
    assert manager.try_enqueue_gallery_scan(db, {'import_only': True})
    assert db.query(Task).filter(Task.type == TaskType.SCAN_FOLDER).count() == 2


def test_global_scan_reuses_pending_startup_task_and_enables_cleanup(library, monkeypatch):
    db, _, _, _ = library
    manager = TaskManager()
    monkeypatch.setattr(manager, 'start_worker_if_needed', lambda: None)
    assert manager.try_enqueue_gallery_scan(db, {'import_only': True})
    startup = db.query(Task).filter(Task.type == TaskType.SCAN_FOLDER).one()

    full = manager.add_task(db, TaskType.SCAN_FOLDER, {})

    assert full.id == startup.id
    assert not full.payload.get('import_only')
    assert manager.try_enqueue_gallery_scan(db, {'import_only': True})
    assert db.query(Task).filter(Task.type == TaskType.SCAN_FOLDER).count() == 1


def test_manual_scan_queues_one_followup_and_worker_waits_for_running_startup(library, monkeypatch):
    from sqlalchemy.orm import Session
    from app.service import task_worker

    db, user, _, _ = library
    manager = TaskManager()
    monkeypatch.setattr(manager, 'start_worker_if_needed', lambda: None)
    assert manager.try_enqueue_gallery_scan(db, {'import_only': True})
    startup = db.query(Task).filter(Task.type == TaskType.SCAN_FOLDER).one()
    startup.status = TaskStatus.PROCESSING
    db.commit()
    payload = {'user_id': str(user.id), 'reconcile': True}
    manual = manager.add_task(db, TaskType.SCAN_FOLDER, payload, owner_id=user.id)
    assert manager.add_task(db, TaskType.SCAN_FOLDER, payload, owner_id=user.id).id == manual.id
    assert manual.id != startup.id

    bind = db.get_bind()
    monkeypatch.setattr(task_worker, 'SessionLocal', lambda: Session(bind))
    scan_worker = task_worker.TaskWorker.__new__(task_worker.TaskWorker)
    scan_worker.paused_categories = set()
    scan_worker.import_priority_active = False
    scan_worker.scan_status = worker().scan_status
    monkeypatch.setattr(scan_worker, '_publish_task_row', lambda task: None)
    infos = [{'id': manual.id, 'type': TaskType.SCAN_FOLDER}]
    assert scan_worker._execute_batch_sync(infos) == ([], None)
    db.refresh(manual)
    assert manual.status == TaskStatus.PENDING

    startup.status = TaskStatus.COMPLETED
    db.commit()
    results, _ = scan_worker._execute_batch_sync(infos)
    assert results[0]['status'] == TaskStatus.COMPLETED


def test_sqlite_manual_scan_can_enqueue_while_automatic_scan_waits_for_writer(library, monkeypatch):
    from sqlalchemy.orm import Session
    from app.crud import task as crud_task

    db, user, _, _ = library
    owner_id = user.id
    bind = db.get_bind()
    manager = TaskManager()
    monkeypatch.setattr(manager, 'start_worker_if_needed', lambda: None)
    gallery_sync.lock_user(db, owner_id)
    automatic_waiting = threading.Event()
    lock_queue = crud_task.lock_gallery_scan_queue

    def signal_lock(session):
        if session is not db:
            automatic_waiting.set()
        lock_queue(session)

    def submit_automatic():
        with Session(bind) as other:
            other.connection().exec_driver_sql('PRAGMA busy_timeout=1000')
            return manager.try_enqueue_gallery_scan(other, {'import_only': True})

    monkeypatch.setattr(crud_task, 'lock_gallery_scan_queue', signal_lock)
    with ThreadPoolExecutor(max_workers=1) as executor:
        automatic = executor.submit(submit_automatic)
        assert automatic_waiting.wait(2)
        manager.add_task(db, TaskType.SCAN_FOLDER, {'user_id': str(owner_id), 'reconcile': True}, owner_id=owner_id)
        assert automatic.result(timeout=3) is False
    assert db.query(Task).filter(Task.type == TaskType.SCAN_FOLDER).count() == 1


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
                gallery_sync.queue_gallery_removal(other, user.id, str(root))
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
    gallery_sync.queue_gallery_removal(db, uid, str(root))
    item = {'task_id': uuid4(), 'status': TaskStatus.COMPLETED,
            'result': {'photo_create_data': {'user_id': str(uid), 'photo_id': uuid4(), 'file_path': str(source)}}}
    asyncio.run(BasicTaskStrategy().handle_completion(worker(), [item], db))
    db.commit()
    assert item['result']['status'] == 'skipped'
    assert db.query(Photo).count() == 0
    assert db.query(Task).filter(Task.type == TaskType.PROCESS_BASIC).count() == 0


def test_large_enqueue_only_resolves_files_before_writer_lock(library, monkeypatch):
    db, user, root, _ = library
    paths = {str(root / f'{i}.jpg') for i in range(1100)}
    original_key = gallery_sync.path_key
    original_lock = gallery_sync.lock_user
    locked = [False]
    calls = []
    def key(path):
        if str(path) in paths:
            calls.append(str(path))
            assert not locked[0], 'file resolution held SQLite writer lock'
        return original_key(path)
    def lock(*args):
        locked[0] = True
        return original_lock(*args)
    original_commit = db.commit
    def commit():
        original_commit()
        locked[0] = False
    monkeypatch.setattr(gallery_sync, 'path_key', key)
    monkeypatch.setattr(gallery_sync, 'lock_user', lock)
    monkeypatch.setattr(db, 'commit', commit)
    asyncio.run(ScanFolderStrategy()._create_tasks_for_new_files(str(user.id), paths, None, db))
    assert db.query(Task).count() == 1100
    assert len(calls) == 1100
    # Repeated scan and alternate lexical spelling still deduplicate.
    aliases = {str(root / '..' / root.name / f'{i}.jpg') for i in range(1100)}
    asyncio.run(ScanFolderStrategy()._create_tasks_for_new_files(str(user.id), aliases, None, db))
    assert db.query(Task).count() == 1100


def test_removal_between_enqueue_chunks_stops_later_imports(library, monkeypatch):
    db, user, root, _ = library
    paths = {str(root / f'{i}.jpg') for i in range(1100)}
    original = gallery_sync.lock_user
    calls = [0]
    def lock(*args):
        calls[0] += 1
        result = original(*args)
        if calls[0] == 2:
            result.settings = dict(result.settings, storage=dict(result.settings['storage'], external_directories=[]))
            db.flush()
        return result
    monkeypatch.setattr(gallery_sync, 'lock_user', lock)
    asyncio.run(ScanFolderStrategy()._create_tasks_for_new_files(str(user.id), paths, None, db))
    assert db.query(Task).count() == 500


def test_concurrent_scan_alias_is_deduplicated_after_snapshot(library, monkeypatch):
    db, user, root, _ = library
    path = str(root / 'one.jpg')
    alias = str(root / '..' / root.name / 'one.jpg')
    original = gallery_sync.lock_user
    def lock(*args):
        # Another scan commits after our initial snapshot, before our lock.
        db.add(Task(type=TaskType.PROCESS_BASIC, owner_id=user.id, status=TaskStatus.PENDING,
                    payload={'file_path': alias, 'scan_path_key': gallery_sync.path_key(alias)}))
        db.commit()
        return original(*args)
    monkeypatch.setattr(gallery_sync, 'lock_user', lock)
    asyncio.run(ScanFolderStrategy()._create_tasks_for_new_files(str(user.id), {path}, None, db))
    assert db.query(Task).count() == 1


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


def test_removal_api_returns_a_persisted_job_and_reports_progress(library, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session
    from app.api import settings

    db, admin, root, _ = library
    admin.is_superuser = True
    db.commit()
    owner_id = admin.id
    photo_id = photo(db, admin, root / 'intact.jpg').id
    bind = db.get_bind()
    db.commit()
    app = FastAPI()
    app.include_router(settings.router)
    app.dependency_overrides[settings.get_db] = lambda: db
    app.dependency_overrides[settings.get_current_user] = lambda: admin
    monkeypatch.setattr(settings.TaskManager, 'start_worker_if_needed', lambda self: None)

    with TestClient(app) as client:
        response = client.request('DELETE', '/directories', json={'path': str(root)})
        assert response.status_code == 200
        task_id = response.json()['data']['task_id']
        assert client.request('DELETE', '/directories', json={'path': str(root)}).json()['data']['task_id'] == task_id
        jobs = client.get('/directories/removals').json()['data']
        assert [(job['id'], job['status']) for job in jobs] == [(task_id, 'pending')]
        assert client.get(f'/directories/removals?user_id={uuid4()}').json()['data'] == []
        db.commit()

        with Session(bind) as worker_db:
            assert worker_db.get(Photo, photo_id) is not None
            task = gallery_sync.removal_tasks(worker_db, owner_id).one()
            task_uuid = task.id
            task.status = TaskStatus.PROCESSING
            worker_db.commit()
        assert gallery_removal.run_gallery_removal(bind, task_uuid) == {'deleted_photos': 1}
        jobs = client.get('/directories/removals').json()['data']
        assert [(job['id'], job['processed_items'], job['total_items']) for job in jobs] == [(task_id, 1, 1)]


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
