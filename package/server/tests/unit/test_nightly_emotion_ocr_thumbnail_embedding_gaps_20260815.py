"""Nightly coverage gaps closed 2026-08-15 round 4.

Targets (all mocked, no real Postgres / network):

- ``app/service/tasks/emotion.py`` (18 lines, 6 uncovered) - deprecated
  EXTRACT_EMOTION strategy: pin ``task_category``, the ``process`` skip
  envelope, and the per-task ``process_batch`` shape.
- ``app/crud/ocr.py`` (17 lines, 9 uncovered) - exercise get/delete/create.
- ``app/utils/embedding.py`` (35 lines, 14 uncovered) - sync + async HTTP
  wrappers to the AI embedding endpoint.
- ``app/service/tasks/thumbnail.py`` (127 lines, 81 uncovered) -
  ``GenerateThumbnailStrategy.process_batch`` payload routing, invalid
  UUID, missing photo, missing file, processed_tasks bookkeeping,
  PhotoColor insert/update, failure propagation, and ``_process_scan``
  pending vs force branches.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


pytestmark = pytest.mark.smoke


# ============================ emotion.py ============================


class _EmTaskStub:
    def __init__(self, task_id="task-emotion"):
        self.id = task_id
        self.type = SimpleNamespace(value="EXTRACT_EMOTION")
        self.payload = {}


def test_emotion_strategy_category_is_cpu():
    from app.service.tasks import emotion as emotion_mod

    assert emotion_mod.ExtractEmotionStrategy().task_category == "CPU"


def test_emotion_process_returns_deprecated_skip_envelope():
    from app.service.tasks import emotion as emotion_mod

    task = _EmTaskStub(task_id="task-1")
    result = asyncio.run(
        emotion_mod.ExtractEmotionStrategy().process(None, task, None)
    )
    assert result == {"processed": 0, "message": "Deprecated task, skipped"}


def test_emotion_process_batch_emits_one_completed_result_per_task():
    from app.service.tasks import emotion as emotion_mod

    tasks = [_EmTaskStub(task_id=f"task-{i}") for i in range(3)]
    results = asyncio.run(
        emotion_mod.ExtractEmotionStrategy().process_batch(None, tasks, None)
    )
    assert len(results) == 3
    for i, res in enumerate(results):
        assert res["task_id"] == f"task-{i}"
        assert res["task_type"] is tasks[i].type
        assert res["status"] == "completed"
        assert res["result"]["status"] == "skipped"
        assert "deprecated" in res["result"]["reason"]


def test_emotion_process_batch_handles_empty_task_list():
    from app.service.tasks import emotion as emotion_mod

    results = asyncio.run(
        emotion_mod.ExtractEmotionStrategy().process_batch(None, [], None)
    )
    assert results == []


# ============================ crud/ocr.py ============================


def test_get_ocr_by_photo_id_returns_query_rows():
    from app.crud import ocr as crud_ocr

    rows = [SimpleNamespace(text="a"), SimpleNamespace(text="b")]
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = rows

    result = crud_ocr.get_ocr_by_photo_id(db, photo_id=uuid4())

    assert result is rows
    db.query.assert_called_once()


def test_delete_ocr_by_photo_id_commits_and_returns_count():
    from app.crud import ocr as crud_ocr

    db = MagicMock()
    db.query.return_value.filter.return_value.delete.return_value = 4

    deleted = crud_ocr.delete_ocr_by_photo_id(db, photo_id=uuid4())

    assert deleted == 4
    db.commit.assert_called_once()


def test_create_ocr_persists_and_refreshes_row():
    from app.crud import ocr as crud_ocr
    from app.schemas.ocr import OCRCreate

    payload = OCRCreate(
        photo_id=uuid4(),
        text="hello",
        text_score=0.95,
        polygon=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
    )

    db = MagicMock()
    db_ocr = MagicMock()
    with patch.object(crud_ocr, "OCR", return_value=db_ocr):
        result = crud_ocr.create_ocr(db, payload)

    db.add.assert_called_once_with(db_ocr)
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(db_ocr)
    assert result is db_ocr


def test_create_ocr_propagates_schema_dump_to_model():
    from app.crud import ocr as crud_ocr
    from app.schemas.ocr import OCRCreate

    payload = OCRCreate(
        photo_id=uuid4(),
        text="abc",
        text_score=0.5,
        polygon=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
    )
    captured = {}

    def fake_ocr(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    db = MagicMock()
    with patch.object(crud_ocr, "OCR", side_effect=fake_ocr):
        crud_ocr.create_ocr(db, payload)

    assert captured["photo_id"] == payload.photo_id
    assert captured["text"] == "abc"
    assert captured["text_score"] == 0.5


# ============================ utils/embedding.py ============================


def _user_cfg(ai_api_url="http://ai.local:9999"):
    cfg = MagicMock()
    cfg.ai.ai_api_url = ai_api_url
    return cfg


def test_get_embedding_returns_first_vector_on_success():
    from app.utils import embedding as emb_mod

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = [[0.1, 0.2, 0.3], [0.9, 0.8, 0.7]]

    db = MagicMock()
    with patch.object(emb_mod.requests, "post", return_value=fake_response), \
         patch.object(emb_mod.config_manager, "get_user_config", return_value=_user_cfg()):
        vec = emb_mod.get_embedding("hello", user_id=1, db=db)

    assert vec == [0.1, 0.2, 0.3]


def test_get_embedding_raises_500_on_non_200_response():
    from app.utils import embedding as emb_mod

    fake_response = MagicMock()
    fake_response.status_code = 503
    fake_response.text = "upstream down"

    db = MagicMock()
    with patch.object(emb_mod.requests, "post", return_value=fake_response), \
         patch.object(emb_mod.config_manager, "get_user_config", return_value=_user_cfg()):
        with pytest.raises(emb_mod.HTTPException) as exc_info:
            emb_mod.get_embedding("hi", user_id=1, db=db)

    assert exc_info.value.status_code == 500
    assert "503" in exc_info.value.detail


def test_get_embedding_raises_500_on_connection_error():
    from app.utils import embedding as emb_mod
    import requests as real_requests

    db = MagicMock()
    with patch.object(emb_mod.requests, "post", side_effect=real_requests.ConnectionError("boom")), \
         patch.object(emb_mod.config_manager, "get_user_config", return_value=_user_cfg()):
        with pytest.raises(emb_mod.HTTPException) as exc_info:
            emb_mod.get_embedding("hi", user_id=1, db=db)

    assert exc_info.value.status_code == 500
    assert "boom" in exc_info.value.detail


@pytest.mark.asyncio
async def test_async_get_embedding_returns_first_vector_on_success():
    from app.utils import embedding as emb_mod

    class _FakeResp:
        status = 200

        async def json(self):
            return [[0.4, 0.5, 0.6]]

        async def text(self):
            return ""

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeSession:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json=None):
            return _FakeResp()

    db = MagicMock()
    with patch.object(emb_mod.aiohttp, "ClientSession", _FakeSession), \
         patch.object(emb_mod.config_manager, "get_user_config", return_value=_user_cfg()):
        vec = await emb_mod.async_get_embedding("hi", user_id=1, db=db)

    assert vec == [0.4, 0.5, 0.6]


@pytest.mark.asyncio
async def test_async_get_embedding_raises_500_on_non_200_response():
    from app.utils import embedding as emb_mod

    class _FakeResp:
        status = 502

        async def json(self):
            return []

        async def text(self):
            return "bad gateway"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeSession:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json=None):
            return _FakeResp()

    db = MagicMock()
    with patch.object(emb_mod.aiohttp, "ClientSession", _FakeSession), \
         patch.object(emb_mod.config_manager, "get_user_config", return_value=_user_cfg()):
        with pytest.raises(emb_mod.HTTPException) as exc_info:
            await emb_mod.async_get_embedding("hi", user_id=1, db=db)

    assert exc_info.value.status_code == 500


# ============================ thumbnail.py ============================


def _photo_obj(photo_id=None, file_path="/tmp/whatever.jpg", owner_id="user-1"):
    return SimpleNamespace(
        id=photo_id or uuid4(),
        owner_id=owner_id,
        file_path=file_path,
        processed_tasks={},
    )


def _task(photo_id=None, task_id=None):
    return SimpleNamespace(
        id=task_id or uuid4(),
        type=SimpleNamespace(value="GENERATE_THUMBNAIL"),
        payload={"photo_id": str(photo_id)} if photo_id else {},
        owner_id="user-1",
    )


def _make_db(photo_lookup=None, photo_color_lookup=None):
    """Build a MagicMock Session with separate per-model query chains.

    ``db.query(Photo).filter().first()`` returns ``photo_lookup``
    (default None = "photo not found").
    ``db.query(PhotoColor).filter().first()`` returns ``photo_color_lookup``
    (default None = insert path).

    Note: callers may have replaced ``thumb_mod.PhotoColor`` with a Mock,
    so we match by class ``__name__`` rather than identity.
    """
    db = MagicMock()

    def query_side_effect(model):
        cls_name = getattr(model, "__name__", None) or type(model).__name__
        chain = MagicMock()
        if cls_name == "Photo":
            chain.filter.return_value.first.return_value = photo_lookup
        elif cls_name == "PhotoColor":
            chain.filter.return_value.first.return_value = photo_color_lookup
        return chain

    db.query.side_effect = query_side_effect
    return db


def _setup_strategy_env(tmp_path, photo_color_lookup=None):
    from PIL import Image as PILImage

    png_path = tmp_path / "img.png"
    PILImage.new("RGB", (16, 16), (255, 0, 0)).save(png_path, format="PNG")

    photo = _photo_obj(file_path=str(png_path))
    db = _make_db(photo_lookup=photo, photo_color_lookup=photo_color_lookup)

    cfg = MagicMock()
    cfg.image = MagicMock()
    worker = MagicMock()
    worker.thread_pool = None

    storage_mod = MagicMock()
    storage_mod.update_storage_root_cache = MagicMock()
    storage_mod.generate_thumbnail = MagicMock(
        return_value=str(tmp_path / "thumb.jpg")
    )
    storage_mod._get_storage_root = MagicMock(return_value=str(tmp_path))

    config_manager = MagicMock()
    config_manager.get_user_config = MagicMock(return_value=cfg)

    return {
        "db": db,
        "worker": worker,
        "photo": photo,
        "storage_mod": storage_mod,
        "config_manager": config_manager,
        "cfg": cfg,
    }


@pytest.mark.asyncio
async def test_thumbnail_process_batch_routes_scan_payload_to_scan_handler(tmp_path):
    from app.service.tasks import thumbnail as thumb_mod

    env = _setup_strategy_env(tmp_path)
    strategy = thumb_mod.GenerateThumbnailStrategy()
    scan_task = _task(photo_id=None)

    async def fake_scan(_worker, _task, _db):
        return {"processed": 0, "generated_tasks": 5, "message": "ok"}

    with patch.object(thumb_mod, "storage", env["storage_mod"]), \
         patch.object(thumb_mod, "config_manager", env["config_manager"]), \
         patch.object(strategy, "_process_scan", side_effect=fake_scan) as scan:
        results = await strategy.process_batch(env["worker"], [scan_task], env["db"])

    scan.assert_awaited_once()
    assert len(results) == 1
    assert results[0]["status"] == "completed"
    assert results[0]["result"]["generated_tasks"] == 5


@pytest.mark.asyncio
async def test_thumbnail_process_batch_skips_invalid_uuid_payload(tmp_path):
    from app.service.tasks import thumbnail as thumb_mod

    env = _setup_strategy_env(tmp_path)
    strategy = thumb_mod.GenerateThumbnailStrategy()
    bad_task = SimpleNamespace(
        id=uuid4(),
        type=SimpleNamespace(value="GENERATE_THUMBNAIL"),
        payload={"photo_id": "not-a-uuid"},
        owner_id="user-1",
    )

    with patch.object(thumb_mod, "storage", env["storage_mod"]), \
         patch.object(thumb_mod, "config_manager", env["config_manager"]):
        results = await strategy.process_batch(env["worker"], [bad_task], env["db"])

    assert results[0]["status"] == "failed"
    assert results[0]["error"] == "invalid uuid"


@pytest.mark.asyncio
async def test_thumbnail_process_batch_skips_missing_photo(tmp_path):
    from app.service.tasks import thumbnail as thumb_mod

    env = _setup_strategy_env(tmp_path)
    # Override photo lookup to None
    env["db"].query.side_effect = lambda model: (
        MagicMock(filter=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None))))
        if True else None
    )
    strategy = thumb_mod.GenerateThumbnailStrategy()
    task = _task(photo_id=uuid4())

    with patch.object(thumb_mod, "storage", env["storage_mod"]), \
         patch.object(thumb_mod, "config_manager", env["config_manager"]):
        results = await strategy.process_batch(env["worker"], [task], env["db"])

    assert results[0]["status"] == "completed"
    assert results[0]["result"]["status"] == "skipped"
    assert "not found" in results[0]["result"]["reason"]


@pytest.mark.asyncio
async def test_thumbnail_process_batch_fails_when_file_missing(tmp_path):
    from app.service.tasks import thumbnail as thumb_mod

    env = _setup_strategy_env(tmp_path)
    env["photo"].file_path = str(tmp_path / "no-such-file.jpg")
    strategy = thumb_mod.GenerateThumbnailStrategy()
    task = _task(photo_id=env["photo"].id)

    with patch.object(thumb_mod, "storage", env["storage_mod"]), \
         patch.object(thumb_mod, "config_manager", env["config_manager"]):
        results = await strategy.process_batch(env["worker"], [task], env["db"])

    assert results[0]["status"] == "failed"
    assert results[0]["error"] == "file not found"


@pytest.mark.asyncio
async def test_thumbnail_process_batch_marks_processed_tasks_and_inserts_color(tmp_path):
    """No existing PhotoColor -> strategy inserts a new row with the
    decoded payload.

    We let ``PhotoColor`` instantiate for real (its ``__init__`` only
    sets attributes; the test asserts via the captured kwargs that the
    strategy forwarded the correct values.
    """
    from app.service.tasks import thumbnail as thumb_mod
    from app.db.models.photo_color import PhotoColor as RealPhotoColor

    env = _setup_strategy_env(tmp_path, photo_color_lookup=None)
    color_payload = {
        "dominant_colors": ["#ff0000", "#00ff00"],
        "brightness": 0.42,
        "saturation": 0.7,
        "emotion_hint": "warm",
    }

    def fake_batch(_data, _config):
        return [{
            "success": True,
            "thumb_path": str(tmp_path / "thumb.jpg"),
            "color_info": color_payload,
        }]

    captured = []

    def fake_init(self, *args, **kwargs):
        captured.append(kwargs)
        # Mimic SQLAlchemy attribute setup without touching the DB.
        for k, v in kwargs.items():
            setattr(self, k, v)

    strategy = thumb_mod.GenerateThumbnailStrategy()
    task = _task(photo_id=env["photo"].id)

    with patch.object(thumb_mod, "storage", env["storage_mod"]), \
         patch.object(thumb_mod, "config_manager", env["config_manager"]), \
         patch.object(thumb_mod, "rebuild_thumbnail_cpu_batch_job", side_effect=fake_batch), \
         patch.object(RealPhotoColor, "__init__", fake_init):
        results = await strategy.process_batch(env["worker"], [task], env["db"])

    assert len(results) == 1
    assert results[0]["status"] == "completed"
    assert env["photo"].processed_tasks["thumbnail"] is True
    assert len(captured) == 1, f"expected one PhotoColor init, got {captured}"
    kwargs = captured[0]
    assert kwargs["photo_id"] == env["photo"].id
    assert kwargs["dominant_colors"] == ["#ff0000", "#00ff00"]
    assert kwargs["brightness"] == 0.42
    assert kwargs["emotion_hint"] == "warm"
    env["db"].add.assert_called()
    env["db"].commit.assert_called()


@pytest.mark.asyncio
async def test_thumbnail_process_batch_updates_existing_photo_color_row(tmp_path):
    from app.service.tasks import thumbnail as thumb_mod

    env = _setup_strategy_env(tmp_path)
    color_payload = {
        "dominant_colors": ["#abcdef"],
        "brightness": 0.1,
        "saturation": 0.2,
        "emotion_hint": "cool",
    }

    def fake_batch(_data, _config):
        return [{
            "success": True,
            "thumb_path": str(tmp_path / "thumb.jpg"),
            "color_info": color_payload,
        }]

    existing = MagicMock()
    env["db"].query.side_effect = lambda model: (
        MagicMock(filter=MagicMock(return_value=MagicMock(first=MagicMock(return_value=env["photo"]))))
        if getattr(model, "__name__", None) == "Photo"
        else MagicMock(filter=MagicMock(return_value=MagicMock(first=MagicMock(return_value=existing))))
    )

    strategy = thumb_mod.GenerateThumbnailStrategy()
    task = _task(photo_id=env["photo"].id)

    with patch.object(thumb_mod, "storage", env["storage_mod"]), \
         patch.object(thumb_mod, "config_manager", env["config_manager"]), \
         patch.object(thumb_mod, "rebuild_thumbnail_cpu_batch_job", side_effect=fake_batch):
        results = await strategy.process_batch(env["worker"], [task], env["db"])

    assert results[0]["status"] == "completed"
    assert existing.dominant_colors == ["#abcdef"]
    assert existing.brightness == 0.1
    assert existing.emotion_hint == "cool"


@pytest.mark.asyncio
async def test_thumbnail_process_batch_records_failure_when_rebuild_returns_error(tmp_path):
    from app.service.tasks import thumbnail as thumb_mod

    env = _setup_strategy_env(tmp_path)

    def fake_batch(_data, _config):
        return [{"success": False, "error": "boom"}]

    strategy = thumb_mod.GenerateThumbnailStrategy()
    task = _task(photo_id=env["photo"].id)

    with patch.object(thumb_mod, "storage", env["storage_mod"]), \
         patch.object(thumb_mod, "config_manager", env["config_manager"]), \
         patch.object(thumb_mod, "rebuild_thumbnail_cpu_batch_job", side_effect=fake_batch):
        results = await strategy.process_batch(env["worker"], [task], env["db"])

    assert results[0]["status"] == "failed"
    assert results[0]["error"] == "boom"


@pytest.mark.asyncio
async def test_thumbnail_process_scan_generates_one_task_per_pending_photo(tmp_path):
    from app.service.tasks import thumbnail as thumb_mod
    from app.db.models.task import TaskType

    db = MagicMock()
    photos_pending = [
        SimpleNamespace(id=uuid4(), owner_id="u1", file_path="/x.jpg", processed_tasks={}),
        SimpleNamespace(id=uuid4(), owner_id="u1", file_path="/y.jpg", processed_tasks=None),
    ]
    photos_done = [
        SimpleNamespace(id=uuid4(), owner_id="u1", file_path="/z.jpg", processed_tasks={"thumbnail": True}),
    ]
    query_chain = MagicMock()
    query_chain.filter.return_value.offset.return_value.limit.return_value.all.side_effect = [
        photos_pending,
        photos_done,
        [],
    ]
    db.query.return_value = query_chain

    worker = MagicMock()
    worker.add_tasks = MagicMock()

    task = SimpleNamespace(
        id=uuid4(),
        type=SimpleNamespace(value="GENERATE_THUMBNAIL"),
        payload={"scope": "all", "force": False},
        owner_id="u1",
    )

    with patch.object(thumb_mod, "config_manager", MagicMock()):
        result = await thumb_mod.GenerateThumbnailStrategy()._process_scan(worker, task, db)

    assert result["generated_tasks"] == 2
    worker.add_tasks.assert_called_once()
    added = worker.add_tasks.call_args.args[1]
    assert len(added) == 2
    for entry in added:
        assert entry["type"] == TaskType.GENERATE_THUMBNAIL
        assert entry["priority"] == 8
        assert entry["owner_id"] == "u1"


@pytest.mark.asyncio
async def test_thumbnail_process_scan_force_includes_already_done_photos(tmp_path):
    from app.service.tasks import thumbnail as thumb_mod

    db = MagicMock()
    photos = [
        SimpleNamespace(id=uuid4(), owner_id="u1", file_path="/x.jpg", processed_tasks={"thumbnail": True}),
        SimpleNamespace(id=uuid4(), owner_id="u1", file_path="/y.jpg", processed_tasks=None),
    ]
    query_chain = MagicMock()
    query_chain.filter.return_value.offset.return_value.limit.return_value.all.side_effect = [
        photos,
        [],
    ]
    db.query.return_value = query_chain
    worker = MagicMock()
    worker.add_tasks = MagicMock()
    task = SimpleNamespace(
        id=uuid4(),
        type=SimpleNamespace(value="GENERATE_THUMBNAIL"),
        payload={"scope": "all", "force": True},
        owner_id="u1",
    )

    with patch.object(thumb_mod, "config_manager", MagicMock()):
        result = await thumb_mod.GenerateThumbnailStrategy()._process_scan(worker, task, db)

    assert result["generated_tasks"] == 2
    assert "Generated 2" in result["message"]


@pytest.mark.asyncio
async def test_thumbnail_process_scan_returns_zero_when_db_empty(tmp_path):
    from app.service.tasks import thumbnail as thumb_mod

    db = MagicMock()
    query_chain = MagicMock()
    query_chain.filter.return_value.offset.return_value.limit.return_value.all.return_value = []
    db.query.return_value = query_chain
    worker = MagicMock()
    worker.add_tasks = MagicMock()
    task = SimpleNamespace(
        id=uuid4(),
        type=SimpleNamespace(value="GENERATE_THUMBNAIL"),
        payload={},
        owner_id="u1",
    )

    with patch.object(thumb_mod, "config_manager", MagicMock()):
        result = await thumb_mod.GenerateThumbnailStrategy()._process_scan(worker, task, db)

    assert result["generated_tasks"] == 0
    worker.add_tasks.assert_not_called()