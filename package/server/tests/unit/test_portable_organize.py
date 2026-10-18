"""Real file/DB regressions for portable organize destinations and failed commits."""
import asyncio
import json
import uuid
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine

from app.db.base import Base
from app.db.models import Photo, StorageRoot, Task, User
from app.db.models.task import TaskType
from app.db.session import SessionLocal
from app.service import storage_paths
from app.service.tasks.organize import OrganizePhotosStrategy

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


@pytest.fixture
def library(tmp_path, monkeypatch):
    root = tmp_path / 'library'
    root.mkdir()
    (root / 'library.json').write_text(json.dumps({'libraryId': str(uuid.uuid4())}))
    monkeypatch.setenv('TS_DESKTOP', '1')
    monkeypatch.setenv('TS_DESKTOP_PORTABLE', '1')
    monkeypatch.setenv('TS_DESKTOP_ROOT', str(root))
    monkeypatch.setattr(storage_paths, '_roots', {})
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with SessionLocal(bind=engine) as db:
        owner = uuid.uuid4()
        db.add(User(id=owner, username='organize', email='organize@example.com', hashed_password='unused'))
        db.commit()
        source = root / f'data/users/{owner}/uploads/photo.jpg'
        source.parent.mkdir(parents=True)
        source.write_bytes(b'original photo')
        photo = Photo(id=uuid.uuid4(), owner_id=owner, file_path=str(source), filename='photo.jpg',
                      file_type='image', photo_time=datetime(2024, 5, 7))
        db.add(photo)
        db.commit()
        yield db, owner, photo.id, source
    engine.dispose()


@pytest.mark.parametrize('action', ['move', 'copy'])
def test_organize_registers_new_external_destination(library, tmp_path, action):
    db, owner, photo_id, source = library
    target = tmp_path / 'organized'
    task = Task(type=TaskType.ORGANIZE_PHOTOS, owner_id=owner,
                payload={'target_root_path': str(target), 'strategy': 'time', 'action': action})
    db.add(task)
    db.commit()
    worker = MagicMock()
    result = asyncio.run(OrganizePhotosStrategy().process(worker, task, db))
    assert result['success_count'] == 1
    destination = target / '2024-05/photo.jpg'
    assert destination.read_bytes() == b'original photo'
    assert source.exists() == (action == 'copy')
    photos = db.query(Photo).all()
    assert len(photos) == (2 if action == 'copy' else 1)
    organized = next(photo for photo in photos if photo.file_path == str(destination.resolve()))
    registered = db.get(StorageRoot, organized.storage_root_id)
    assert registered.owner_id == owner
    assert registered.kind == 'external'
    # Loading a fresh process cache must still resolve the registered root.
    storage_paths._roots.clear()
    assert db.get(Photo, organized.id).file_path == str(destination.resolve())


@pytest.mark.parametrize('action', ['move', 'copy'])
def test_organize_restores_files_after_database_commit_failure(library, tmp_path, monkeypatch, action):
    db, owner, photo_id, source = library
    target = tmp_path / 'organized'
    task = Task(type=TaskType.ORGANIZE_PHOTOS, owner_id=owner,
                payload={'target_root_path': str(target), 'strategy': 'time', 'action': action})
    db.add(task)
    db.commit()
    destination = target / '2024-05/photo.jpg'
    original_commit = db.commit

    def fail_after_file_transfer():
        if destination.exists():
            raise RuntimeError('injected disk/commit failure')
        original_commit()

    monkeypatch.setattr(db, 'commit', fail_after_file_transfer)
    worker = MagicMock()
    with pytest.raises(RuntimeError, match='injected disk/commit failure'):
        asyncio.run(OrganizePhotosStrategy().process(worker, task, db))
    assert source.read_bytes() == b'original photo'
    assert not destination.exists()
    assert db.get(Photo, photo_id).file_path == str(source.resolve())
    assert db.query(Photo).count() == 1
    worker.get_instance.return_value.add_task.assert_not_called()
