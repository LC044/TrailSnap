"""Focused coverage for the five lowest-covered API routers.

The tests isolate database, network, task-manager, and storage dependencies so
they remain deterministic in both local and Docker CI environments.
"""

import json
import os
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

import app.crud.photo
from app.api import face as face_api
from app.api import media as media_api
from app.api import photo as photo_api
from app.api import settings as settings_api
from app.api import train_ticket as train_api
from app.schemas.photo import BatchDownloadRequest


pytestmark = pytest.mark.smoke


def _user(**overrides):
    data = {"id": uuid4(), "is_superuser": False}
    data.update(overrides)
    return SimpleNamespace(**data)


# api/photo.py


def test_batch_download_builds_archive_and_deduplicates_names(tmp_path: Path):
    user = _user()
    db = MagicMock()
    photo_ids = [uuid4(), uuid4()]
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    photos = [
        SimpleNamespace(file_path=str(first), filename="photo.jpg"),
        SimpleNamespace(file_path=str(second), filename="photo.jpg"),
    ]
    archive = tmp_path / "export.zip"

    def fake_mkstemp(*, suffix):
        fd = os.open(archive, os.O_CREAT | os.O_RDWR)
        return fd, str(archive)

    with patch.object(
        app.crud.photo, "get_photos_by_ids", return_value=photos
    ) as get_photos, patch.object(
        photo_api.tempfile, "mkstemp", side_effect=fake_mkstemp
    ):
        response = photo_api.batch_download_photos(
            req=BatchDownloadRequest(photo_ids=photo_ids),
            db=db,
            current_user=user,
        )

    get_photos.assert_called_once_with(
        db, [str(value) for value in photo_ids], user_id=user.id
    )
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.namelist() == ["photo.jpg", "photo_1.jpg"]
    assert response.media_type == "application/zip"


def test_batch_download_rejects_empty_photo_ids():
    with pytest.raises(HTTPException) as exc_info:
        photo_api.batch_download_photos(
            req=BatchDownloadRequest(photo_ids=[]),
            db=MagicMock(),
            current_user=_user(),
        )

    assert exc_info.value.status_code == 400


def test_batch_download_returns_404_when_no_owned_photos_exist():
    with patch.object(app.crud.photo, "get_photos_by_ids", return_value=[]):
        with pytest.raises(HTTPException) as exc_info:
            photo_api.batch_download_photos(
                req=BatchDownloadRequest(photo_ids=[uuid4()]),
                db=MagicMock(),
                current_user=_user(),
            )

    assert exc_info.value.status_code == 404


# api/settings.py


def _settings_config(connections):
    return SimpleNamespace(
        ai=SimpleNamespace(
            connections=connections,
            analysis_connection_id="analysis-1",
            analysis_model_name="vision-model",
        )
    )


def test_available_models_returns_enabled_static_connections_only():
    enabled = SimpleNamespace(
        id="enabled",
        enable=True,
        provider="OpenAI",
        api_base="http://models.test/v1",
        api_key="",
        model_names=["model-a"],
    )
    disabled = SimpleNamespace(
        id="disabled",
        enable=False,
        provider="OpenAI",
        api_base="http://disabled.test/v1",
        api_key="",
        model_names=["model-b"],
    )

    with patch.object(
        settings_api.config_manager,
        "get_user_config",
        return_value=_settings_config([enabled, disabled]),
    ), patch.object(settings_api.requests, "get") as request:
        result = settings_api.get_available_models(
            db=MagicMock(), current_user=_user()
        )

    assert result["connections"] == [
        {
            "id": "enabled",
            "provider": "OpenAI",
            "api_base": "http://models.test/v1",
            "models": ["model-a"],
        }
    ]
    assert result["chat_connection_id"] == ""
    request.assert_not_called()


def test_available_models_fetches_dynamic_ids_with_auth_header():
    connection = SimpleNamespace(
        id="dynamic",
        enable=True,
        api_base="http://models.test/v1/",
        api_key="secret",
        model_names=[],
    )
    response = MagicMock(status_code=200)
    response.json.return_value = {"data": [{"id": "model-a"}, {}, {"id": "model-b"}]}

    with patch.object(
        settings_api.config_manager,
        "get_user_config",
        return_value=_settings_config([connection]),
    ), patch.object(settings_api.requests, "get", return_value=response) as request:
        result = settings_api.get_available_models(
            db=MagicMock(), current_user=_user()
        )

    request.assert_called_once_with(
        "http://models.test/v1/models",
        headers={"Authorization": "Bearer secret"},
        timeout=5,
    )
    assert result["connections"][0]["models"] == ["model-a", "model-b"]
    assert result["connections"][0]["provider"] == "OpenAI"


def test_available_models_tolerates_provider_failure():
    connection = SimpleNamespace(
        id="offline",
        enable=True,
        api_base="http://offline.test/v1",
        api_key="",
        model_names=[],
    )

    with patch.object(
        settings_api.config_manager,
        "get_user_config",
        return_value=_settings_config([connection]),
    ), patch.object(settings_api.requests, "get", side_effect=OSError("offline")):
        result = settings_api.get_available_models(
            db=MagicMock(), current_user=_user()
        )

    assert result["connections"][0]["models"] == []


# api/media.py


async def _run_inline(function, *args, **kwargs):
    return function(*args, **kwargs)


@pytest.mark.asyncio
async def test_upload_photo_saves_record_and_schedules_basic_task():
    user = _user()
    db = MagicMock()
    uploaded = SimpleNamespace(filename="photo.jpg")
    saved = SimpleNamespace(id=uuid4())
    manager = MagicMock()

    with patch.object(
        media_api, "run_in_threadpool", side_effect=_run_inline
    ), patch.object(
        media_api.storage, "save_upload_file", return_value="/photos/photo.jpg"
    ) as save_file, patch.object(
        media_api, "save_and_create_photo", return_value=saved
    ) as create_photo, patch.object(
        media_api.TaskManager, "get_instance", return_value=manager
    ):
        result = await media_api.upload_photo_generic(
            album_id=None, file=uploaded, db=db, current_user=user
        )

    assert result is saved
    assert save_file.call_args.args[0] is uploaded
    create_photo.assert_called_once()
    task = manager.add_tasks.call_args.args[1][0]
    assert task["type"] == media_api.TaskType.PROCESS_BASIC
    assert task["payload"]["file_path"] == "/photos/photo.jpg"
    assert manager.add_tasks.call_args.kwargs["owner_id"] == user.id


@pytest.mark.asyncio
async def test_finish_upload_rejects_session_without_numeric_chunks():
    with patch.object(
        media_api, "run_in_threadpool", side_effect=_run_inline
    ), patch.object(media_api.os.path, "exists", return_value=True), patch.object(
        media_api.os, "listdir", return_value=["merged", "notes.txt"]
    ):
        with pytest.raises(HTTPException) as exc_info:
            await media_api.finish_upload_generic(
                upload_id=uuid4(),
                file_name="photo.jpg",
                album_id=None,
                db=MagicMock(),
                current_user=_user(),
            )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "No chunks found"


@pytest.mark.asyncio
async def test_upload_photo_rejects_unknown_album_before_saving():
    album_id = uuid4()

    with patch.object(
        media_api, "run_in_threadpool", side_effect=_run_inline
    ), patch.object(media_api.crud_album, "get_album", return_value=None), patch.object(
        media_api.storage, "save_upload_file"
    ) as save_file:
        with pytest.raises(HTTPException) as exc_info:
            await media_api.upload_photo_generic(
                album_id=album_id,
                file=SimpleNamespace(filename="photo.jpg"),
                db=MagicMock(),
                current_user=_user(),
            )

    assert exc_info.value.status_code == 404
    save_file.assert_not_called()


# api/train_ticket.py


def _upload(name, content_type, payload):
    file = SimpleNamespace(filename=name, content_type=content_type)
    file.read = AsyncMock(return_value=payload)
    return file


@pytest.mark.asyncio
async def test_import_tickets_accepts_empty_json_array():
    response = await train_api.import_tickets(
        file=_upload("tickets.json", "application/json", b"[]"),
        db=MagicMock(),
        current_user=_user(),
    )

    assert response.code == 200
    assert response.data["total"] == 0
    assert response.data["success"] == 0
    assert response.data["failed"] == 0


@pytest.mark.asyncio
async def test_import_tickets_rejects_oversized_payload():
    payload = b"x" * (10 * 1024 * 1024 + 1)

    with pytest.raises(HTTPException) as exc_info:
        await train_api.import_tickets(
            file=_upload("tickets.json", "application/json", payload),
            db=MagicMock(),
            current_user=_user(),
        )

    assert exc_info.value.status_code == 413


def test_export_tickets_serializes_json_for_current_user():
    user = _user()
    db = MagicMock()
    tickets = [{"id": "ticket-1", "train_code": "G1"}]

    with patch.object(
        train_api, "get_all_train_tickets", return_value=tickets
    ) as get_tickets:
        response = train_api.export_tickets(
            format="json", db=db, current_user=user
        )

    assert json.loads(response.body) == tickets
    assert response.media_type == "application/json"
    get_tickets.assert_called_once_with(db, owner_id=user.id)


# api/face.py


def test_get_identity_photos_forwards_owner_and_paging():
    user = _user()
    db = MagicMock()
    identity_id = uuid4()
    photos = [SimpleNamespace(id=uuid4())]

    with patch.object(
        face_api.crud_face, "get_identity_photos", return_value=photos
    ) as get_photos:
        response = face_api.get_identity_photos(
            id=identity_id, skip=5, limit=20, db=db, current_user=user
        )

    get_photos.assert_called_once_with(
        db,
        identity_id,
        skip=5,
        limit=20,
        owner_id=user.id,
    )
    assert response.data is photos


@pytest.mark.asyncio
async def test_add_photos_accepts_empty_selection_without_creating_faces():
    user = _user()
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.all.return_value = []
    payload = SimpleNamespace(photo_ids=[])

    with patch.object(
        face_api.crud_face, "get_identity", return_value=SimpleNamespace(id=uuid4())
    ), patch("app.crud.album.trigger_conditional_albums_update") as trigger:
        response = await face_api.add_photos_to_identity(
            id=uuid4(), payload=payload, db=db, current_user=user
        )

    assert response.data["count"] == 0
    db.commit.assert_called_once()
    trigger.assert_called_once_with(db, user.id, [])


@pytest.mark.asyncio
async def test_add_photos_rejects_missing_identity():
    with patch.object(face_api.crud_face, "get_identity", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            await face_api.add_photos_to_identity(
                id=uuid4(),
                payload=SimpleNamespace(photo_ids=[uuid4()]),
                db=MagicMock(),
                current_user=_user(),
            )

    assert exc_info.value.status_code == 404
