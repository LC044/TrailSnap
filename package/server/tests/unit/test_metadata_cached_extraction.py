"""Import tasks reuse durable metadata and prefer generated thumbnails."""
import asyncio
import json
import hashlib
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image

from app.db.models.photo import FileType
from app.db.models.photo_color import PhotoColor
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.task import Task, TaskType
from app.service.tasks import basic, metadata
from app.schemas.photo import PhotoCreate
from app.schemas.metadata import PhotoMetadataCreate
from app.core.config_manager import ImageSettings
from app.utils import exif, hash as hash_utils, motion_photo
from test_basic_pipeline_performance import seed

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def test_basic_dispatch_persists_complete_metadata_and_batch_never_reads_source(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    uid, photos = seed(db, count=1)
    photo = photos[0]
    raw = json.loads(json.dumps({
        'exif_info': '{"Make":"Camera","FNumber":"2.8"}',
        'photo_time': datetime(2020, 1, 1),
        'location': {'latitude': 30.0, 'longitude': 120.0},
        'duration': 4.2, 'fps': 30, 'codec': 'h264', 'rotation': 90,
    }, default=str))
    data = {'photo_id': photo.id, 'file_path': photo.file_path, 'user_id': str(uid),
            'photo': PhotoCreate(filename=photo.filename, file_type=FileType.image, size=1),
            'metadata': PhotoMetadataCreate(exif_info=raw['exif_info']),
            'is_pre_created': True, 'raw_metadata': raw}
    asyncio.run(basic.BasicTaskStrategy().handle_completion(None, [
        {'status': 'completed', 'result': {'photo_create_data': data}}], db))
    db.commit()
    db.expire_all()
    task = db.query(Task).filter(Task.type == TaskType.EXTRACT_METADATA).one()
    assert task.payload['raw_metadata'] == raw
    monkeypatch.setattr(metadata, 'rebuild_metadata_cpu_job', lambda *_: pytest.fail('Source was read again'))
    monkeypatch.setattr(metadata.exif, 'reverse_geocode', lambda *_: {'city': 'Hangzhou'})
    monkeypatch.setattr(metadata.storage, 'get_preview_path', lambda *_: None)
    result = asyncio.run(metadata.ExtractMetadataStrategy().process_batch(None, [task], db))
    assert result[0]['status'] == 'completed'
    db.expire_all()
    stored = db.get(PhotoMetadata, photo.id)
    assert stored.make == 'Camera'
    assert stored.shooting_params['fps'] == 30
    assert stored.shooting_params['f_number'] == '2.8'
    assert stored.city == 'Hangzhou'
    assert float(stored.latitude) == 30
    assert photo.photo_time == datetime(2020, 1, 1)


def test_legacy_and_rebuild_tasks_read_original(monkeypatch):
    photo = SimpleNamespace(id=uuid4(), file_path='original.jpg')
    calls = []
    monkeypatch.setattr(metadata, 'rebuild_metadata_cpu_job', lambda *args: calls.append(args) or {'success': True})
    assert metadata.extract_task_metadata({}, photo)['success']
    assert calls == [('original.jpg', photo.id)]


def test_color_uses_small_thumbnail_and_retry_is_idempotent(face_sqlite_session, tmp_path, monkeypatch):
    db = face_sqlite_session
    _, photos = seed(db, count=1)
    photo = photos[0]
    # The source doesn't exist, and the preview is blue; only the red thumb counts.
    preview = tmp_path / 'preview.webp'
    Image.new('RGB', (500, 500), 'blue').save(preview)
    Image.new('RGB', (50, 50), 'red').save(tmp_path / 'preview-thumb.webp')
    monkeypatch.setattr(metadata.storage, 'get_preview_path', lambda *_: str(preview))
    metadata.update_photo_color_from_thumbnail(db, photo)
    db.commit()
    record = db.query(PhotoColor).one()
    assert record.dominant_colors[0]['hex'].lower().startswith('#ff')
    monkeypatch.setattr(metadata, 'extract_color_info', lambda *_: pytest.fail('Already analyzed'))
    metadata.update_photo_color_from_thumbnail(db, photo)
    db.commit()
    assert db.query(PhotoColor).count() == 1


def test_missing_thumbnail_and_original_skip_color(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    _, photos = seed(db, count=1)
    monkeypatch.setattr(metadata.storage, 'get_preview_path', lambda *_: None)
    monkeypatch.setattr(metadata, 'budgeted_open', lambda *_: pytest.fail('Must not open original'))
    metadata.update_photo_color_from_thumbnail(db, photos[0])
    assert db.query(PhotoColor).count() == 0


def test_basic_reads_original_once_including_hash_and_motion_video(tmp_path, monkeypatch):
    original = tmp_path / '20200101_120000.jpg'
    Image.new('RGB', (4000, 3000), 'red').save(original)
    video = (24).to_bytes(4, 'big') + b'ftypisom' + b'\x00' * 4 + b'isommp42' + b'video-data'
    with original.open('ab') as stream:
        stream.write(video)
    expected_hash = hashlib.md5(original.read_bytes()).hexdigest()
    opens = []
    actual_open = basic.budgeted_open
    @contextmanager
    def tracked_open(path, *args, **kwargs):
        if str(path) == str(original):
            opens.append(path)
        with actual_open(path, *args, **kwargs) as stream:
            yield stream
    for module in (basic, basic.storage, exif, hash_utils, motion_photo):
        monkeypatch.setattr(module, 'budgeted_open', tracked_open)
    monkeypatch.setattr(basic.storage, '_get_storage_root', lambda *_: str(tmp_path))
    result = basic.process_basic_cpu_job(str(original), uuid4(), str(tmp_path), str(uuid4()), ImageSettings())
    assert result['success'], result
    assert len(opens) == 1
    assert result['md5_hash'] == expected_hash
    assert (result['width'], result['height']) == (4000, 3000)
    assert result['raw_metadata']['photo_time'].startswith('2020-01-01')
    assert result['is_motion_photo']
    assert (tmp_path / result['thumb_path']).with_suffix('.mp4').read_bytes() == video


def test_analysis_path_falls_back_to_original_after_generation_failure(tmp_path, monkeypatch):
    original = tmp_path / 'original.jpg'
    original.write_bytes(b'original')
    monkeypatch.setattr(metadata.storage, 'get_preview_path', lambda *_: None)
    assert metadata.storage.get_available_photo_path(uuid4(), uuid4(), str(original)) == str(original)


def test_color_falls_back_to_original_after_generation_failure(face_sqlite_session, tmp_path, monkeypatch):
    db = face_sqlite_session
    _, photos = seed(db, count=1)
    original = tmp_path / 'original.png'
    Image.new('RGB', (60, 40), 'red').save(original)
    photos[0].file_path = str(original)
    monkeypatch.setattr(metadata.storage, 'get_preview_path', lambda *_: None)
    metadata.update_photo_color_from_thumbnail(db, photos[0])
    db.commit()
    assert db.query(PhotoColor).count() == 1
