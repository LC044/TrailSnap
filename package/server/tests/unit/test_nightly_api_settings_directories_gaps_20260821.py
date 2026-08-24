"""Targeted unit tests for app/api/settings.py endpoints.

These endpoints were still uncovered after test_settings_api.py shipped; together
they close the bulk of the remaining miss-lines on api/settings.py and let the
nightly coverage scan rerun without flagging the same module again.

* GET    /models                              -> get_available_models
* POST   /verify-connection                   -> verify_connection
* DELETE /ai-models/{model_id}                -> delete_ai_model
* POST   /directories                         -> add_directory
* DELETE /directories                         -> remove_directory
* GET    /directories/browse                  -> browse_external_directories
* GET    /directories/candidates              -> get_directory_candidates
* POST   /directories/validate                -> validate_directory
* POST   /directories/batch                   -> batch_add_directories
* PUT    /storage-root                        -> update_storage_root
* POST   /filter/apply                        -> apply_filter
* POST   /map/upload                          -> upload_map_data
* GET    /map/files/{filename}                -> download_map_file
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

import pytest
from fastapi import BackgroundTasks, HTTPException

from app.api import settings as settings_api
from app.dependencies import BaseResponse


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


# ---------- GET /models ----------

def test_get_available_models_filters_disabled_connections():
    db = MagicMock()
    user = _user()
    enabled = SimpleNamespace(
        id="conn-1",
        provider="OpenAI",
        api_base="",
        enable=True,
        model_names=["gpt-4", "gpt-3.5"],
    )
    disabled = SimpleNamespace(
        id="conn-2",
        provider="OpenAI",
        api_base="",
        enable=False,
        model_names=["hidden"],
    )
    ai = SimpleNamespace(
        connections=[enabled, disabled],
        analysis_connection_id="conn-1",
        analysis_model_name="gpt-4",
        chat_connection_id="",
        chat_model_name="",
    )
    cfg = SimpleNamespace(ai=ai)

    with patch.object(settings_api.config_manager, "get_user_config", return_value=cfg):
        result = settings_api.get_available_models(db=db, current_user=user)

    assert [c["id"] for c in result["connections"]] == ["conn-1"]
    assert result["connections"][0]["models"] == ["gpt-4", "gpt-3.5"]
    assert result["analysis_connection_id"] == "conn-1"
    assert result["analysis_model_name"] == "gpt-4"


def test_get_available_models_fetches_models_dynamically_when_empty():
    db = MagicMock()
    user = _user()
    enabled = SimpleNamespace(
        id="conn-dynamic",
        provider="OpenAI",
        api_base="https://api.example.com/v1",
        api_key="key-123",
        enable=True,
        model_names=[],
    )
    ai = SimpleNamespace(
        connections=[enabled],
        analysis_connection_id="conn-dynamic",
        analysis_model_name="upstream-model",
        chat_connection_id="",
        chat_model_name="",
    )
    cfg = SimpleNamespace(ai=ai)

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "data": [
            {"id": "upstream-model"},
            {"id": ""},
            {"id": "another-model"},
        ]
    }

    with patch.object(settings_api.config_manager, "get_user_config", return_value=cfg), \
         patch.object(settings_api.requests, "get", return_value=fake_response) as get_call:
        result = settings_api.get_available_models(db=db, current_user=user)

    get_call.assert_called_once()
    args, kwargs = get_call.call_args
    assert args[0] == "https://api.example.com/v1/models"
    assert kwargs["headers"]["Authorization"] == "Bearer key-123"
    assert result["connections"][0]["models"] == ["upstream-model", "another-model"]


def test_get_available_models_swallows_upstream_errors():
    db = MagicMock()
    user = _user()
    enabled = SimpleNamespace(
        id="conn-broken",
        provider="OpenAI",
        api_base="https://broken.invalid/v1",
        api_key="",
        enable=True,
        model_names=[],
    )
    ai = SimpleNamespace(
        connections=[enabled],
        analysis_connection_id="",
        analysis_model_name="",
        chat_connection_id="",
        chat_model_name="",
    )
    cfg = SimpleNamespace(ai=ai)

    with patch.object(settings_api.config_manager, "get_user_config", return_value=cfg), \
         patch.object(settings_api.requests, "get", side_effect=RuntimeError("network boom")):
        result = settings_api.get_available_models(db=db, current_user=user)

    assert result["connections"][0]["models"] == []

# ---------- POST /verify-connection ----------

def test_verify_connection_returns_models_on_success():
    user = _user()

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "data": [{"id": "model-a"}, {"id": "model-b"}, {"id": None}]
    }

    with patch.object(settings_api.requests, "get", return_value=fake_response) as get_call:
        result = settings_api.verify_connection(
            req=settings_api.VerifyConnectionRequest(
                api_base="https://api.example.com/v1/",
                api_key="abcd",
            ),
            current_user=user,
        )

    args, kwargs = get_call.call_args
    assert args[0] == "https://api.example.com/v1/models"
    assert kwargs["headers"]["Authorization"] == "Bearer abcd"
    assert result == {"success": True, "models": ["model-a", "model-b"]}


def test_verify_connection_reports_non_2xx_status_code():
    user = _user()

    fake_response = MagicMock()
    fake_response.status_code = 401
    fake_response.text = "unauthorized"

    with patch.object(settings_api.requests, "get", return_value=fake_response):
        result = settings_api.verify_connection(
            req=settings_api.VerifyConnectionRequest(api_base="https://x.invalid/v1"),
            current_user=user,
        )

    assert result["success"] is False
    assert "401" in result["message"]
    assert "unauthorized" in result["message"]


def test_verify_connection_maps_network_error_to_message():
    user = _user()

    with patch.object(settings_api.requests, "get", side_effect=RuntimeError("dns broken")):
        result = settings_api.verify_connection(
            req=settings_api.VerifyConnectionRequest(api_base="https://x.invalid/v1"),
            current_user=user,
        )

    assert result["success"] is False
    assert "dns broken" in result["message"]


# ---------- DELETE /ai-models/{model_id} ----------

def test_delete_ai_model_quotes_model_id_and_calls_helper():
    db = MagicMock()
    user = _user()

    fake_response = BaseResponse.success(data={"deleted": True})
    with patch.object(
        settings_api,
        "_ai_model_request",
        return_value=fake_response,
    ) as helper:
        result = settings_api.delete_ai_model(
            model_id="foo/bar baz",
            db=db,
            current_user=user,
        )

    helper.assert_called_once()
    sent_method, sent_path, sent_user, sent_db = helper.call_args.args
    assert sent_method == "DELETE"
    assert sent_path == "/ai/models/foo%2Fbar%20baz"
    assert sent_user is user
    assert sent_db is db
    assert result is fake_response


# ---------- POST /directories (add_directory) ----------

def test_add_directory_rejects_non_superuser():
    db = MagicMock()
    user = _user(is_superuser=False)

    with pytest.raises(HTTPException) as exc:
        settings_api.add_directory(
            payload={"path": "/photos/family"},
            db=db,
            current_user=user,
        )

    assert exc.value.status_code == 403
    assert "Not authorized" in exc.value.detail


def test_add_directory_rejects_nonexistent_path(tmp_path):
    db = MagicMock()
    user = _user(is_superuser=True)
    missing = tmp_path / "definitely-missing"

    with pytest.raises(HTTPException) as exc:
        settings_api.add_directory(
            payload={"path": str(missing)},
            db=db,
            current_user=user,
        )
    assert exc.value.status_code == 400


def test_add_directory_appends_external_then_triggers_scan(tmp_path):
    db = MagicMock()
    user = _user(is_superuser=True)
    target = tmp_path / "gallery"
    target.mkdir()
    user.settings = {"storage": {"external_directories": []}}

    fake_task_manager = MagicMock()
    with patch.object(
        settings_api.config_manager,
        "update_user_config",
    ) as update_call, patch(
        "app.service.task_manager.TaskManager.get_instance",
        return_value=fake_task_manager,
    ):
        result = settings_api.add_directory(
            payload={"path": str(target)},
            db=db,
            current_user=user,
        )

    update_call.assert_called_once()
    persisted = update_call.call_args.args[1]
    assert str(target) in persisted["storage"]["external_directories"]
    fake_task_manager.add_task.assert_called_once()
    args, _ = fake_task_manager.add_task.call_args
    assert args[0] is db
    assert args[2]["scan_roots"] == [str(target)]
    assert result["external"][-1] == str(target)


def test_add_directory_dedupes_when_path_already_external(tmp_path):
    db = MagicMock()
    user = _user(is_superuser=True)
    target = tmp_path / "already-listed"
    target.mkdir()
    user.settings = {"storage": {"external_directories": [str(target)]}}

    fake_task_manager = MagicMock()
    with patch.object(
        settings_api.config_manager,
        "update_user_config",
    ) as update_call, patch(
        "app.service.task_manager.TaskManager.get_instance",
        return_value=fake_task_manager,
    ):
        result = settings_api.add_directory(
            payload={"path": str(target)},
            db=db,
            current_user=user,
        )

    # already-listed path: return early, no DB write, no scan task
    update_call.assert_not_called()
    fake_task_manager.add_task.assert_not_called()
    assert result["external"] == [str(target)]


# ---------- DELETE /directories (remove_directory) ----------

def test_remove_directory_requires_superuser():
    db = MagicMock()
    user = _user(is_superuser=False)

    with pytest.raises(HTTPException) as exc:
        settings_api.remove_directory(
            payload={"path": "/photos/family"},
            db=db,
            current_user=user,
        )
    assert exc.value.status_code == 403


def test_remove_directory_requires_path():
    db = MagicMock()
    user = _user(is_superuser=True)

    with pytest.raises(HTTPException) as exc:
        settings_api.remove_directory(
            payload={"path": ""},
            db=db,
            current_user=user,
        )
    assert exc.value.status_code == 400
    assert "path required" in exc.value.detail


def test_remove_directory_noop_when_not_in_external_list(tmp_path):
    db = MagicMock()
    user = _user(is_superuser=True)
    user.settings = {"storage": {"external_directories": [str(tmp_path / "a")]}}

    other = tmp_path / "b"
    other.mkdir()

    with patch.object(
        settings_api.config_manager,
        "get_user_config",
        return_value=_config(external=[str(tmp_path / "a")]),
    ):
        result = settings_api.remove_directory(
            payload={"path": str(other)},
            db=db,
            current_user=user,
        )

    assert result["external"] == [str(tmp_path / "a")]
    assert result["primary"].endswith("photos")


# ---------- GET /directories/browse ----------

def test_browse_external_directories_requires_superuser():
    user = _user(is_superuser=False)

    with pytest.raises(HTTPException) as exc:
        settings_api.browse_external_directories(path="/app/Photos", current_user=user)
    assert exc.value.status_code == 403


def test_browse_external_directories_returns_tree_payload():
    user = _user(is_superuser=True)
    tree = [{"name": "trip-1", "children": []}]

    with patch.object(
        settings_api.gallery_service,
        "list_directory_tree",
        return_value=tree,
    ) as service_call:
        result = settings_api.browse_external_directories(
            path="/srv/photos",
            current_user=user,
        )

    service_call.assert_called_once_with("/srv/photos")
    assert result.data == tree


def test_browse_external_directories_maps_service_errors_to_http():
    user = _user(is_superuser=True)

    with patch.object(
        settings_api.gallery_service,
        "list_directory_tree",
        side_effect=PermissionError("nope"),
    ):
        with pytest.raises(HTTPException) as exc:
            settings_api.browse_external_directories(path="/", current_user=user)
    assert exc.value.status_code == 403

    with patch.object(
        settings_api.gallery_service,
        "list_directory_tree",
        side_effect=FileNotFoundError("missing"),
    ):
        with pytest.raises(HTTPException) as exc:
            settings_api.browse_external_directories(path="/missing", current_user=user)
    assert exc.value.status_code == 404


# ---------- GET /directories/candidates ----------

def test_get_directory_candidates_delegates_to_gallery_service():
    db = MagicMock()
    user = _user(is_superuser=False)

    expected = [{"name": "trip-1"}, {"name": "trip-2"}]
    with patch.object(
        settings_api.gallery_service,
        "list_candidates",
        return_value=expected,
    ) as service_call:
        result = settings_api.get_directory_candidates(
            db=db,
            current_user=user,
        )

    service_call.assert_called_once_with(str(user.id), db)
    assert result.code == 0
    assert result.data == expected


def test_get_directory_candidates_superuser_can_target_other_user():
    db = MagicMock()
    user = _user(is_superuser=True)
    target = _user(uid="other-user-id", is_superuser=False)
    db.query.return_value.filter.return_value.first.return_value = target

    with patch.object(
        settings_api.gallery_service,
        "list_candidates",
        return_value=[],
    ) as service_call:
        result = settings_api.get_directory_candidates(
            db=db,
            current_user=user,
            user_id="other-user-id",
        )

    service_call.assert_called_once_with("other-user-id", db)
    assert result.code == 0


# ---------- POST /directories/validate ----------

def test_validate_directory_delegates_to_service():
    db = MagicMock()
    user = _user(is_superuser=False)

    validation = {"ok": True, "code": "OK", "path": "/photos"}
    with patch.object(
        settings_api.gallery_service,
        "validate_path",
        return_value=validation,
    ) as service_call:
        result = settings_api.validate_directory(
            payload={"path": "/photos"},
            db=db,
            current_user=user,
        )

    service_call.assert_called_once_with("/photos", str(user.id), db)
    assert result.code == 0
    assert result.data == validation


# ---------- POST /directories/batch ----------

def test_batch_add_directories_requires_superuser():
    db = MagicMock()
    user = _user(is_superuser=False)

    with pytest.raises(HTTPException) as exc:
        settings_api.batch_add_directories(
            payload={"paths": ["/photos/a"]},
            db=db,
            current_user=user,
        )
    assert exc.value.status_code == 403


def test_batch_add_directories_rejects_non_list_paths():
    db = MagicMock()
    user = _user(is_superuser=True)

    with pytest.raises(HTTPException) as exc:
        settings_api.batch_add_directories(
            payload={"paths": "not-a-list"},
            db=db,
            current_user=user,
        )
    assert exc.value.status_code == 400


def test_batch_add_directories_returns_partial_errors_payload(tmp_path):
    db = MagicMock()
    user = _user(is_superuser=True)
    bad = tmp_path / "missing-target"  # never created -> gallery_service batch_add will reject it
    fail_payload = {
        "added": [],
        "errors": [{"path": str(bad), "code": "DIRECTORY_NOT_FOUND"}],
    }

    with patch.object(
        settings_api.gallery_service,
        "batch_add",
        return_value=fail_payload,
    ) as service_call:
        result = settings_api.batch_add_directories(
            payload={"paths": [str(bad)]},
            db=db,
            current_user=user,
        )

    service_call.assert_called_once()
    assert result.code == 400
    assert "部分路径校验未通过" in (result.msg or "")
    assert result.data == fail_payload


def test_batch_add_directories_propagates_value_error_to_fail_response(tmp_path):
    db = MagicMock()
    user = _user(is_superuser=True)
    good = tmp_path / "gallery"
    good.mkdir()

    with patch.object(
        settings_api.gallery_service,
        "batch_add",
        side_effect=ValueError("too many paths"),
    ):
        result = settings_api.batch_add_directories(
            payload={"paths": [str(good)]},
            db=db,
            current_user=user,
        )

    assert result.code == 400
    assert "too many paths" in result.msg


# ---------- PUT /storage-root ----------

def test_update_storage_root_writes_path_to_config(tmp_path):
    db = MagicMock()
    user = _user()
    cfg = _config(storage_path="/old")

    with patch.object(
        settings_api.config_manager,
        "get_user_config",
        return_value=cfg,
    ), patch.object(
        settings_api.config_manager,
        "update_user_config",
    ) as update_call:
        result = settings_api.update_storage_root(
            payload={"storage_root": str(tmp_path)},
            db=db,
            current_user=user,
        )

    update_call.assert_called_once()
    args = update_call.call_args.args
    assert args[0] == user.id
    assert args[1]["storage"]["photo_storage_path"] == str(tmp_path)
    assert result == {"storage_root": str(tmp_path)}


def test_update_storage_root_rejects_missing_path():
    db = MagicMock()
    user = _user()

    with pytest.raises(HTTPException) as exc:
        settings_api.update_storage_root(
            payload={"storage_root": ""},
            db=db,
            current_user=user,
        )
    assert exc.value.status_code == 400


def test_update_storage_root_rejects_non_directory(tmp_path):
    db = MagicMock()
    user = _user()
    file_path = tmp_path / "file.txt"
    file_path.write_text("x")

    with pytest.raises(HTTPException) as exc:
        settings_api.update_storage_root(
            payload={"storage_root": str(file_path)},
            db=db,
            current_user=user,
        )
    assert exc.value.status_code == 400


# ---------- POST /filter/apply ----------

def test_apply_filter_enqueues_background_task_for_current_user():
    user = _user()
    bg = MagicMock(spec=BackgroundTasks)

    with patch.object(
        settings_api,
        "apply_filter_task_bg",
    ) as bg_func:
        result = settings_api.apply_filter(
            background_tasks=bg,
            current_user=user,
        )

    bg.add_task.assert_called_once()
    sent_args = bg.add_task.call_args.args
    assert sent_args[0] is bg_func
    assert sent_args[1] == str(user.id)
    assert result == {
        "status": "started",
        "message": "Filter application started in background",
    }


# ---------- POST /map/upload (upload_map_data) ----------

def test_upload_map_data_rejects_non_csv_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_api, "RG_DATA_DIR", str(tmp_path))

    upload = SimpleNamespace(filename="data.txt", read=AsyncMock(return_value=b""))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(settings_api.upload_map_data(file=upload))
    assert exc.value.status_code == 400
    assert "CSV" in exc.value.detail


def test_upload_map_data_writes_valid_csv(tmp_path, monkeypatch):
    data_dir = tmp_path / "rg"
    monkeypatch.setattr(settings_api, "RG_DATA_DIR", str(data_dir))

    csv_bytes = (
        b"longitude,latitude,country,admin_1,admin_2,admin_3,admin_4\n"
        b"114.30,30.59,CN,Hubei,Wuhan,,,\n"
    )
    upload = SimpleNamespace(filename="CN.csv", read=AsyncMock(return_value=csv_bytes))

    result = asyncio.run(settings_api.upload_map_data(file=upload))

    assert result["status"] == "success"
    assert (data_dir / "CN.csv").exists()


def test_upload_map_data_rejects_missing_columns(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_api, "RG_DATA_DIR", str(tmp_path))

    csv_bytes = b"longitude,latitude,country\n114.30,30.59,CN\n"
    upload = SimpleNamespace(filename="missing.csv", read=AsyncMock(return_value=csv_bytes))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(settings_api.upload_map_data(file=upload))
    assert exc.value.status_code == 400
    assert "Missing required columns" in exc.value.detail


# ---------- GET /map/files/{filename} ----------

def test_download_map_file_returns_csv_file_response(tmp_path, monkeypatch):
    data_dir = tmp_path / "rg"
    data_dir.mkdir()
    (data_dir / "CN.csv").write_text("longitude,latitude,country\n")
    monkeypatch.setattr(settings_api, "RG_DATA_DIR", str(data_dir))

    result = settings_api.download_map_file("CN.csv")
    assert Path(result.path).resolve() == (data_dir / "CN.csv").resolve()


def test_download_map_file_rejects_directory_traversal(tmp_path, monkeypatch):
    data_dir = tmp_path / "rg"
    data_dir.mkdir()
    monkeypatch.setattr(settings_api, "RG_DATA_DIR", str(data_dir))

    with pytest.raises(HTTPException) as exc:
        settings_api.download_map_file("..%2F..%2Fetc%2Fpasswd")
    assert exc.value.status_code == 400


def test_download_map_file_404_when_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_api, "RG_DATA_DIR", str(tmp_path / "missing"))

    with pytest.raises(HTTPException) as exc:
        settings_api.download_map_file("CN.csv")
    assert exc.value.status_code == 404
