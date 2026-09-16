"""2026-09-16 nightly tests closing remaining coverage gaps in app/api/settings.py.

These tests focus on the branches that the nightly coverage scan still flagged
as uncovered after the previous nightly runs. They exercise:

* GET    /directories                  -> superuser can target another user (404 path)
* POST   /directories                  -> add for another user; settings init paths
* DELETE /directories                  -> superuser 404 + photo cleanup cascade
* GET    /storage-root                 -> update_storage_root rw check failure
* POST   /verify-ai-service            -> non-200 / invalid JSON / wrong status /
                                          RequestException paths
* POST   /map/test-key                 -> invalid JSON / non-OK status paths
* _ai_model_request                    -> ValueError body fallback + 503 path
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api import settings as settings_api


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def _user(uid=None, *, is_superuser=False):
    from uuid import uuid4

    return SimpleNamespace(
        id=uid or uuid4(),
        is_superuser=is_superuser,
        settings={},
    )


def _config(storage_path="/photos", external=None):
    external = external or []
    return SimpleNamespace(
        model_dump=lambda: {
            "storage": {
                "photo_storage_path": storage_path,
                "external_directories": list(external),
            }
        },
        storage=SimpleNamespace(
            photo_storage_path=storage_path,
            external_directories=list(external),
        ),
    )


# ---------- GET /directories ----------


def test_get_directories_superuser_can_target_other_user():
    db = MagicMock()
    admin = _user(is_superuser=True)
    target = _user(uid="target-user")
    db.query.return_value.filter.return_value.first.return_value = target

    with patch.object(
        settings_api, "get_storage_root", return_value="/srv/photos"
    ) as get_root:
        result = settings_api.get_directories(
            db=db, current_user=admin, user_id="target-user"
        )

    assert result["primary"] == "/srv/photos"
    get_root.assert_called_once_with("target-user", db)


def test_get_directories_superuser_404_for_missing_target():
    db = MagicMock()
    admin = _user(is_superuser=True)
    db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as exc:
        settings_api.get_directories(
            db=db, current_user=admin, user_id="ghost-user"
        )

    assert exc.value.status_code == 404
    assert "User not found" in exc.value.detail


# ---------- POST /directories ----------


def test_add_directory_superuser_can_target_other_user(tmp_path):
    db = MagicMock()
    admin = _user(is_superuser=True)
    target = _user(uid="other-user")
    target.settings = {"storage": {"external_directories": []}}
    db.query.return_value.filter.return_value.first.return_value = target

    gallery = tmp_path / "incoming"
    gallery.mkdir()

    fake_task_manager = MagicMock()
    with patch.object(
        settings_api.config_manager, "update_user_config"
    ) as update_call, patch(
        "app.service.task_manager.TaskManager.get_instance",
        return_value=fake_task_manager,
    ):
        result = settings_api.add_directory(
            payload={"user_id": "other-user", "path": str(gallery)},
            db=db,
            current_user=admin,
        )

    update_call.assert_called_once()
    persisted = update_call.call_args.args[1]
    assert str(gallery.resolve()) in persisted["storage"]["external_directories"]
    fake_task_manager.add_task.assert_called_once()
    scan_kwargs = fake_task_manager.add_task.call_args.args[2]
    assert scan_kwargs["user_id"] == "other-user"
    assert result["external"][-1] == str(gallery.resolve())


def test_add_directory_superuser_404_for_missing_target():
    db = MagicMock()
    admin = _user(is_superuser=True)
    db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as exc:
        settings_api.add_directory(
            payload={"user_id": "ghost", "path": "/tmp/x"},
            db=db,
            current_user=admin,
        )

    assert exc.value.status_code == 404


def test_add_directory_initializes_settings_for_fresh_user(tmp_path):
    db = MagicMock()
    admin = _user(is_superuser=True)
    target = _user(uid="fresh-user")
    # Settings attribute is None to trigger init branch (lines 414-420)
    target.settings = None
    db.query.return_value.filter.return_value.first.return_value = target

    gallery = tmp_path / "fresh"
    gallery.mkdir()

    fake_task_manager = MagicMock()
    with patch.object(
        settings_api.config_manager, "update_user_config"
    ) as update_call, patch(
        "app.service.task_manager.TaskManager.get_instance",
        return_value=fake_task_manager,
    ):
        result = settings_api.add_directory(
            payload={"user_id": "fresh-user", "path": str(gallery)},
            db=db,
            current_user=admin,
        )

    persisted = update_call.call_args.args[1]
    assert persisted["storage"]["external_directories"] == [str(gallery.resolve())]
    assert result["external"][-1] == str(gallery.resolve())


# ---------- DELETE /directories ----------


def test_remove_directory_superuser_404_for_missing_target():
    db = MagicMock()
    admin = _user(is_superuser=True)
    db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as exc:
        settings_api.remove_directory(
            payload={"user_id": "ghost", "path": "/srv/p"},
            db=db,
            current_user=admin,
        )

    assert exc.value.status_code == 404


def test_remove_directory_cascade_deletes_photos_in_removed_path(tmp_path):
    """Superuser path; verifies photo cascade (lines 479-492).

    Bypass PathValidator.validate so the test is independent of OS path layout.
    """
    import os

    db = MagicMock()
    admin = _user(is_superuser=True)

    target_path = tmp_path / "victim-gallery"
    target_path.mkdir()
    sibling = tmp_path / "sibling-gallery"
    sibling.mkdir()
    abs_target = os.path.abspath(str(target_path))

    target = _user(uid="victim-user")
    target.settings = {"storage": {"external_directories": [abs_target]}}
    db.query.return_value.filter.return_value.first.return_value = target

    cfg = _config(storage_path="/srv/root", external=[abs_target])

    inside = SimpleNamespace(id=1, file_path=os.path.join(abs_target, "img.jpg"))
    sibling_photo = SimpleNamespace(id=2, file_path=str(sibling / "stay.jpg"))
    db.query.return_value.filter.return_value.all.return_value = [inside, sibling_photo]

    batch_delete = MagicMock()
    fake_task_manager = MagicMock()
    with patch.object(
        settings_api.PathValidator, "validate", return_value=abs_target
    ), patch.object(
        settings_api.gallery_service,
        "relation",
        side_effect=lambda p, q: ("child" if p.startswith(abs_target) else "unrelated"),
    ), patch.object(
        settings_api.config_manager,
        "get_user_config",
        return_value=cfg,
    ), patch.object(
        settings_api.config_manager, "update_user_config"
    ), patch(
        "app.service.task_manager.TaskManager.get_instance",
        return_value=fake_task_manager,
    ), patch(
        "app.crud.photo.batch_delete_photos_db", batch_delete
    ), patch.object(settings_api, "get_storage_root", return_value="/srv/root"):
        settings_api.remove_directory(
            payload={"user_id": "victim-user", "path": str(target_path)},
            db=db,
            current_user=admin,
        )

    # The photo inside the removed path should be deleted; the sibling photo must NOT.
    assert db.add.called  # IndexLog rows added
    assert batch_delete.called
    deleted_ids = batch_delete.call_args.args[1]
    assert deleted_ids == [1]
    db.commit.assert_called_once()


# ---------- PUT /storage-root ----------


def test_update_storage_root_rejects_unwritable_directory(tmp_path):
    db = MagicMock()
    user = _user()
    target = tmp_path / "readonly"
    target.mkdir()

    with patch("tempfile.mkstemp", side_effect=OSError("rw fail")):
        with pytest.raises(HTTPException) as exc:
            settings_api.update_storage_root(
                payload={"storage_root": str(target)},
                db=db,
                current_user=user,
            )

    assert exc.value.status_code == 400
    assert "rw check failed" in exc.value.detail


# ---------- POST /verify-ai-service ----------


def test_verify_ai_service_reports_non_200_http_status():
    response = MagicMock(status_code=502)
    with patch.object(settings_api.requests, "get", return_value=response):
        result = settings_api.verify_ai_service(
            req=settings_api.VerifyAIServiceRequest(api_url="http://ai:8001"),
            current_user=_user(),
        )

    assert result.code == 0
    assert result.data["success"] is False
    assert "502" in result.data["message"]


def test_verify_ai_service_treats_invalid_json_as_empty_body():
    response = MagicMock(status_code=200)
    response.json.side_effect = ValueError("not json")
    with patch.object(settings_api.requests, "get", return_value=response):
        result = settings_api.verify_ai_service(
            req=settings_api.VerifyAIServiceRequest(api_url="http://ai:8001"),
            current_user=_user(),
        )

    assert result.code == 0
    assert result.data["success"] is False
    assert "不是可识别" in result.data["message"]


def test_verify_ai_service_reports_generic_request_exception():
    with patch.object(
        settings_api.requests, "get", side_effect=settings_api.requests.ConnectionError
    ):
        result = settings_api.verify_ai_service(
            req=settings_api.VerifyAIServiceRequest(api_url="http://ai:8001"),
            current_user=_user(),
        )

    assert result.code == 0
    assert result.data["success"] is False
    assert "无法连接" in result.data["message"]


# ---------- POST /map/test-key ----------


def test_map_key_reports_invalid_json_response():
    response = MagicMock(ok=True, status_code=200)
    response.json.side_effect = ValueError("bad json")
    with patch.object(settings_api.requests, "get", return_value=response):
        result = settings_api.test_map_key(
            settings_api.MapKeyTestRequest(api_key="any-key"),
            current_user=_user(),
        )

    assert result.code == 0
    assert result.data == {"valid": False, "reason": "天地图返回了无效响应"}


def test_map_key_reports_non_zero_tianditu_status():
    response = MagicMock(ok=True, status_code=200)
    response.json.return_value = {"status": "207", "msg": "权限不足"}
    with patch.object(settings_api.requests, "get", return_value=response):
        result = settings_api.test_map_key(
            settings_api.MapKeyTestRequest(api_key="bad-key"),
            current_user=_user(),
        )

    assert result.code == 0
    assert result.data == {"valid": False, "reason": "权限不足"}


# ---------- _ai_model_request ----------


def test_ai_model_request_returns_503_on_connection_error():
    db = MagicMock()
    user = _user()
    cfg = SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://127.0.0.1:18001"))

    with patch.object(settings_api.config_manager, "get_user_config", return_value=cfg), \
         patch.object(settings_api.requests, "request", side_effect=settings_api.requests.ConnectionError):
        result = settings_api._ai_model_request("GET", "/ai/models", user, db)

    assert result.code == 503
    assert "AI 模型服务不可用" in result.msg


def test_ai_model_request_falls_back_to_text_on_invalid_json():
    db = MagicMock()
    user = _user()
    cfg = SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://127.0.0.1:18001"))
    response = MagicMock(status_code=400, text="bad upstream")
    response.json.side_effect = ValueError("nope")

    with patch.object(settings_api.config_manager, "get_user_config", return_value=cfg), \
         patch.object(settings_api.requests, "request", return_value=response):
        result = settings_api._ai_model_request("POST", "/ai/models/x/download", user, db)

    assert result.code == 400
    assert result.msg == "bad upstream"






