import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import create_engine, text

pytestmark = [pytest.mark.smoke, pytest.mark.module_embedding]
ROOT = Path(__file__).parents[2]


def exercise_migration(connection, folder, revision):
    path = next((ROOT / folder / 'versions').glob(revision + '*.py'))
    spec = importlib.util.spec_from_file_location('embedding_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    uuid_type = 'uuid' if connection.dialect.name == 'postgresql' else 'varchar(36)'
    connection.exec_driver_sql(f'CREATE TABLE image_vectors (photo_id {uuid_type})')
    connection.exec_driver_sql(f'''CREATE TABLE tasks (id {uuid_type} PRIMARY KEY, type varchar(50),
        status varchar(20), priority integer, payload json, attempt_count integer NOT NULL,
        total_items integer, processed_items integer, created_at timestamp, updated_at timestamp)''')
    with Operations.context(MigrationContext.configure(connection)):
        migration.upgrade()
        assert connection.scalar(text('SELECT count(*) FROM tasks')) == 0
        connection.execute(text('INSERT INTO image_vectors VALUES (:id)'), {'id': str(uuid4())})
        migration.upgrade()
        migration.upgrade()
        assert connection.scalar(text('SELECT count(*) FROM tasks')) == 1
        row = connection.execute(text('SELECT type,status,payload FROM tasks')).one()
        import json
        payload = json.loads(row.payload) if isinstance(row.payload, str) else row.payload
        assert row.type == 'IMAGE_EMBEDDING' and row.status == 'pending'
        assert payload == {'force': True, 'model': 'chinese-clip-ViT-B-16', 'source': 'chinese_clip_upgrade_v1'}
        migration.downgrade()
        assert connection.scalar(text('SELECT count(*) FROM tasks')) == 0
        assert connection.scalar(text('SELECT count(*) FROM image_vectors')) == 1


def test_sqlite_upgrade_queues_once_only_for_existing_vectors():
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        exercise_migration(connection, 'alembic_sqlite', 'e205c1a0b002')
    engine.dispose()


@pytest.mark.postgres
def test_postgres_upgrade_queues_once_only_for_existing_vectors(request):
    if 'postgres' not in request.config.getoption('markexpr'):
        pytest.skip('Select postgres explicitly')
    engine = create_engine(os.environ['TS_DB_URL'])
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                schema = 'embedding_upgrade_' + uuid4().hex
                connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
                connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
                exercise_migration(connection, 'alembic', 'e205c1a0b001')
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


@pytest.fixture
def switch_context(face_sqlite_session, monkeypatch):
    from app.api import settings
    from app.dependencies import BaseResponse
    db = face_sqlite_session
    user = SimpleNamespace(id=uuid4())
    snapshot = {'tasks': {'embedding': {'selected': 'old'}}, 'models': [
        {'id': 'new', 'tasks': ['embedding'], 'status': 'ready', 'runtimeName': 'new-runtime'}]}
    calls = []

    def request(method, path, *args, **kwargs):
        calls.append((method, path, kwargs.get('json_body')))
        return BaseResponse.success(data=snapshot if method == 'GET' else {'status': 'active'})

    monkeypatch.setattr(settings, '_ai_model_request', request)
    monkeypatch.setattr(settings.config_manager, 'get_user_config', lambda *a: SimpleNamespace(ai=SimpleNamespace(ai_api_url='http://ai')))
    monkeypatch.setattr(settings.TaskManager, 'get_instance', lambda: MagicMock())
    return settings, db, user, snapshot, calls


def test_switch_commits_force_generator_then_blocks_repeat(switch_context):
    settings, db, user, snapshot, calls = switch_context
    from app.db.models.task import Task
    result = settings.select_ai_model(settings.AIModelSelectionRequest(task='embedding', model='new'), db, user)
    assert result.code == 0 and result.data['rebuildTaskId']
    task = db.query(Task).one()
    assert task.owner_id is None and task.payload['force'] is True
    assert task.payload['model'] == 'new-runtime'
    assert task.payload['ai_api_url'] == 'http://ai'
    assert settings.select_ai_model(settings.AIModelSelectionRequest(task='embedding', model='new'), db, user).code == 409


def test_switch_queue_commit_failure_restores_model(switch_context, monkeypatch):
    settings, db, user, snapshot, calls = switch_context
    monkeypatch.setattr(db, 'commit', MagicMock(side_effect=RuntimeError('disk full')))
    result = settings.select_ai_model(settings.AIModelSelectionRequest(task='embedding', model='new'), db, user)
    assert result.code != 0
    assert calls[-1][2] == {'task': 'embedding', 'model': 'old'}
    from app.db.models.task import Task
    assert db.query(Task).count() == 0


def test_same_model_and_not_ready_do_not_queue(switch_context):
    settings, db, user, snapshot, calls = switch_context
    assert settings.select_ai_model(settings.AIModelSelectionRequest(task='embedding', model='old'), db, user).code == 0
    snapshot['models'][0]['status'] = 'downloading'
    assert settings.select_ai_model(settings.AIModelSelectionRequest(task='embedding', model='new'), db, user).code == 409
    from app.db.models.task import Task
    assert db.query(Task).count() == 0


def test_selected_embedding_model_cannot_be_deleted(switch_context):
    settings, db, user, snapshot, calls = switch_context
    assert settings.delete_ai_model('old', db, user).code == 409
    assert len(calls) == 1 and calls[0][0] == 'GET'


def test_response_requires_actual_target_model():
    from app.service.tasks.image_embedding import ImageEmbeddingStrategy
    response = SimpleNamespace(headers={'X-Embedding-Model': 'new-runtime'})
    assert ImageEmbeddingStrategy._response_model(response, 'new-runtime') == 'new-runtime'
    with pytest.raises(ValueError, match='不一致'):
        ImageEmbeddingStrategy._response_model(response, 'old-runtime')
    with pytest.raises(ValueError, match='升级 AI 服务'):
        ImageEmbeddingStrategy._response_model(SimpleNamespace(headers={}), 'new-runtime')


def test_model_mismatch_is_waiting_and_retryable():
    from app.service.task_worker import TaskWorker
    error = 'AI Service error: 409: 等待 AI 模型：需要 chinese-clip-ViT-B-16'
    assert TaskWorker._is_model_preparing_error(error)
    assert TaskWorker._is_retryable_error(error)


def test_upgrade_generator_keeps_force_and_target_for_processed_photos(face_sqlite_session):
    import asyncio
    from app.db.models.photo import Photo, FileType
    from app.db.models.task import Task, TaskType
    from app.service.tasks.image_embedding import ImageEmbeddingStrategy
    from app.crud.task import add_tasks
    db = face_sqlite_session
    photo = Photo(id=uuid4(), file_path='/fixture.jpg', file_type=FileType.image,
                  processed_tasks={'image_embedding': True})
    db.add(photo)
    db.commit()
    task = Task(type=TaskType.IMAGE_EMBEDDING, payload={
        'force': True, 'model': 'chinese-clip-ViT-B-16', 'source': 'chinese_clip_upgrade_v1'})
    db.add(task)
    db.commit()
    result = asyncio.run(ImageEmbeddingStrategy().process(SimpleNamespace(add_tasks=add_tasks), task, db))
    assert result['generated_tasks'] == 1
    child = db.query(Task).filter(Task.photo_id == photo.id).one()
    assert child.payload['force'] is True
    assert child.payload['model'] == 'chinese-clip-ViT-B-16'
