"""Task-management bulk actions must expand into scoped, executable photo jobs."""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api import tasks as tasks_api
from app.core.config_manager import AppSettings
from app.crud import task as crud_task
from app.db.models.photo import FileType, ImageType, Photo
from app.db.models.task import Task, TaskType
from app.service.tasks import basic, metadata, visual_description
from app.service.tasks.classification import ClassifyImageStrategy
from app.service.tasks.face import RecognizeFaceStrategy
from app.service.tasks.image_embedding import ImageEmbeddingStrategy
from app.service.tasks.ocr import OcrStrategy
from app.service.tasks.thumbnail import GenerateThumbnailStrategy
from app.service.tasks.tickets import RecognizeTicketStrategy
from test_basic_pipeline_performance import seed

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


@pytest.mark.parametrize('force', [False, True])
@pytest.mark.parametrize('kind,strategy,status_key,include_video', [
    (TaskType.PROCESS_BASIC, basic.BasicTaskStrategy, 'basic', True),
    (TaskType.EXTRACT_METADATA, metadata.ExtractMetadataStrategy, 'metadata', True),
    (TaskType.REBUILD_METADATA, metadata.RebuildMetadataStrategy, 'metadata', True),
    (TaskType.GENERATE_THUMBNAIL, GenerateThumbnailStrategy, 'thumbnail', True),
    (TaskType.RECOGNIZE_FACE, RecognizeFaceStrategy, 'face', False),
    (TaskType.CLASSIFY_IMAGE, ClassifyImageStrategy, 'classification', False),
    (TaskType.OCR, OcrStrategy, 'ocr', False),
    (TaskType.IMAGE_EMBEDDING, ImageEmbeddingStrategy, 'image_embedding', False),
    (TaskType.RECOGNIZE_TICKET, RecognizeTicketStrategy, 'tickets', False),
    (TaskType.VISUAL_DESCRIPTION, visual_description.VisualDescriptionStrategy, 'visual_description', False),
])
def test_bulk_action_from_api_scopes_and_propagates_force(
    face_sqlite_session, monkeypatch, force, kind, strategy, status_key, include_video,
):
    db = face_sqlite_session
    owner_id, photos = seed(db, count=6)
    _, foreign = seed(db, count=1)
    pending, done, removed, video, live, screenshot = photos
    done.processed_tasks = {status_key: True}
    removed.is_deleted = True
    video.file_type = FileType.video
    live.file_type = FileType.live_photo
    screenshot.image_type = ImageType.SCREENSHOT
    db.commit()
    # Match the task-management request, including its authenticated owner.
    manager = SimpleNamespace(add_task=crud_task.add_task)
    monkeypatch.setattr(tasks_api.TaskManager, 'get_instance', lambda: manager)
    task = tasks_api.create_task(
        tasks_api.TaskCreate(type=kind, payload={'scope': 'all', 'force': force}),
        db=db, current_user=SimpleNamespace(id=owner_id),
    ).data
    monkeypatch.setenv('CI', '')
    settings = SimpleNamespace(ai=SimpleNamespace(
        analysis_connection_id='test', analysis_model_name='test',
        connections=[SimpleNamespace(id='test', enable=True, api_key='test')],
    ))
    monkeypatch.setattr(visual_description.config_manager, 'get_user_config', lambda *_: settings)
    worker = SimpleNamespace(add_tasks=crud_task.add_tasks)
    results = asyncio.run(strategy().process_batch(worker, [task], db))

    child_kind = TaskType.EXTRACT_METADATA if kind == TaskType.REBUILD_METADATA else kind
    children = db.query(Task).filter(Task.id != task.id).all()
    expected = {pending.id, live.id, screenshot.id}
    if force:
        expected.add(done.id)
    if include_video:
        expected.add(video.id)
    if kind == TaskType.VISUAL_DESCRIPTION:
        expected.remove(screenshot.id)
    assert results[0]['status'] == 'completed'
    assert results[0]['result']['generated_tasks'] == len(expected)
    assert {row.photo_id for row in children} == expected
    assert all(row.type == child_kind and row.owner_id == owner_id for row in children)
    assert all(row.payload['force'] is force and row.payload['file_path'] for row in children)
    assert foreign[0].id not in expected and removed.id not in expected
    if kind == TaskType.PROCESS_BASIC:
        live_task = next(row for row in children if row.photo_id == live.id)
        assert live_task.payload['is_live_photo'] is True


def test_metadata_force_rereads_source_and_refreshes_panorama(face_sqlite_session, tmp_path, monkeypatch):
    from test_panorama import fixture_photo
    from app.utils.panorama import full_geometry

    db = face_sqlite_session
    owner, photo = fixture_photo(db, tmp_path)
    photo.panorama_override = 'ordinary'
    photo.processed_tasks = {'metadata': True}
    db.commit()
    # A forced job must ignore a stale durable extraction as well as the status flag.
    task = Task(id=uuid4(), type=TaskType.EXTRACT_METADATA, owner_id=owner.id, payload={
        'photo_id': str(photo.id), 'force': True,
        'raw_metadata_version': 1, 'raw_metadata': {'panorama': None},
    })
    monkeypatch.setattr(metadata, 'update_photo_color_from_thumbnail', lambda *a, **kw: None)
    result = asyncio.run(metadata.ExtractMetadataStrategy().process_batch(None, [task], db))
    assert result[0]['status'] == 'completed'
    db.refresh(photo)
    assert photo.panorama_projection == 'equirectangular'
    assert photo.panorama_detected == full_geometry(800, 400)
    assert photo.panorama_override is None


def test_basic_rebuild_child_reuses_photo_and_records_completion(face_sqlite_session, tmp_path, monkeypatch):
    from PIL import Image

    db = face_sqlite_session
    owner_id, photos = seed(db, count=1)
    photo = photos[0]
    source = tmp_path / 'original.jpg'
    Image.new('RGB', (320, 240), 'red').save(source)
    photo.file_path = str(source)
    db.commit()
    settings = AppSettings()
    settings.filter.enable = False
    monkeypatch.setattr(basic.config_manager, 'get_user_config', lambda *_: settings)
    monkeypatch.setattr(basic.storage, '_get_storage_root', lambda *_: str(tmp_path / 'cache'))
    task = Task(id=uuid4(), type=TaskType.PROCESS_BASIC, owner_id=owner_id, payload={
        'scope': 'all', 'force': True,
    })
    worker = SimpleNamespace(add_tasks=crud_task.add_tasks, thread_pool=None)
    strategy = basic.BasicTaskStrategy()
    asyncio.run(strategy.process_batch(worker, [task], db))
    child = db.query(Task).filter(Task.type == TaskType.PROCESS_BASIC).one()
    results = asyncio.run(strategy.process_batch(worker, [child], db))
    assert results[0]['status'] == 'completed'
    asyncio.run(strategy.handle_completion(worker, results, db))
    db.commit()
    db.refresh(photo)
    assert db.query(Photo).count() == 1
    assert photo.processed_tasks['basic'] is True
    assert photo.md5 and photo.width == 320
    assert db.query(Task).filter(Task.type == TaskType.EXTRACT_METADATA).count() == 1
