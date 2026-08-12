"""Unit tests for the settings REST router (app/api/settings.py).

Covers the small, deterministic endpoints:

* GET    /settings/get_storage_root  -> helper reading user config
* GET    /settings/                 -> returns config_manager.get_user_config().model_dump()
* PUT    /settings/                 -> updates config via config_manager
* GET    /settings/export           -> same payload as get_settings
* POST   /settings/import           -> updates config + refreshes storage cache
* GET    /settings/map/countries    -> reads countries.json from disk
* GET    /settings/map/downloaded   -> lists CSV files in RG_DATA_DIR
* DELETE /settings/map/files/{name} -> path-traversal guard + missing-file branches
* POST   /settings/map/download     -> enqueues background task
                                         (BackgroundTasks.add_task is verified)

The endpoints that touch live Postgres, make HTTP calls or scan the disk are
out of scope and tested via the Playwright E2E suite.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException

from app.api import settings as settings_api


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def _user(uid=None):
    from uuid import uuid4

    return SimpleNamespace(id=uid or uuid4())


def _config(storage_path="E:/photos"):
    return SimpleNamespace(
        model_dump=lambda: {"storage": {"photo_storage_path": storage_path}},
        storage=SimpleNamespace(photo_storage_path=storage_path),
    )


# ----------------------- GET settings/ helper -----------------------


def test_get_storage_root_returns_configured_path():
    db = MagicMock()
    user = _user()

    with patch.object(settings_api.config_manager, "get_user_config", return_value=_config("E:/photos")):
        result = settings_api.get_storage_root(user_id=user.id, db=db)

    assert result == "E:/photos"
    db.close.assert_called_once()


def test_get_storage_root_falls_back_to_uploads():
    db = MagicMock()
    user = _user()

    with patch.object(settings_api.config_manager, "get_user_config", return_value=_config("")):
        result = settings_api.get_storage_root(user_id=user.id, db=db)

    assert result == "uploads"


# ----------------------- GET/PUT settings -----------------------


def test_get_settings_returns_config_dump():
    db = MagicMock()
    user = _user()
    cfg = _config("D:/photos")

    with patch.object(settings_api.config_manager, "get_user_config", return_value=cfg):
        result = settings_api.get_settings(db=db, current_user=user)

    assert result == {"storage": {"photo_storage_path": "D:/photos"}}


def test_update_settings_returns_new_config():
    db = MagicMock()
    user = _user()
    new_cfg = _config("F:/photos")

    with patch.object(
        settings_api.config_manager,
        "update_user_config",
        return_value=new_cfg,
    ) as update_call, patch.object(
        settings_api, "update_storage_root_cache"
    ) as cache_call:
        result = settings_api.update_settings(
            payload={"storage": {"photo_storage_path": "F:/photos"}},
            db=db,
            current_user=user,
        )

    update_call.assert_called_once_with(
        user.id, {"storage": {"photo_storage_path": "F:/photos"}}, db
    )
    cache_call.assert_called_once_with(user.id, "F:/photos")
    assert result["status"] == "success"
    assert result["config"]["storage"]["photo_storage_path"] == "F:/photos"


def test_export_settings_matches_get_settings():
    db = MagicMock()
    user = _user()
    cfg = _config("G:/photos")

    with patch.object(settings_api.config_manager, "get_user_config", return_value=cfg):
        result = settings_api.export_settings(db=db, current_user=user)

    assert result == {"storage": {"photo_storage_path": "G:/photos"}}


def test_get_ai_models_proxies_configured_ai_service():
    db = MagicMock()
    user = _user()
    cfg = SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://127.0.0.1:18001"))
    response = MagicMock(status_code=200)
    response.json.return_value = {"models": [{"id": "desktop-core-models", "status": "ready"}]}

    with patch.object(settings_api.config_manager, "get_user_config", return_value=cfg), \
         patch.object(settings_api.requests, "request", return_value=response) as request_call:
        result = settings_api.get_ai_models(db=db, current_user=user)

    request_call.assert_called_once_with(
        "GET", "http://127.0.0.1:18001/ai/models", timeout=120
    )
    assert result.code == 0
    assert result.data["models"][0]["status"] == "ready"


def test_download_ai_model_encodes_identifier_and_returns_upstream_error():
    db = MagicMock()
    user = _user()
    cfg = SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://127.0.0.1:18001/"))
    response = MagicMock(status_code=409)
    response.json.return_value = {"detail": "模型正在下载"}

    with patch.object(settings_api.config_manager, "get_user_config", return_value=cfg), \
         patch.object(settings_api.requests, "request", return_value=response) as request_call:
        result = settings_api.download_ai_model("core/model", db=db, current_user=user)

    request_call.assert_called_once_with(
        "POST", "http://127.0.0.1:18001/ai/models/core%2Fmodel/download", timeout=120
    )
    assert result.code == 409
    assert result.msg == "模型正在下载"


# ----------------------- POST /settings/import -----------------------


def test_import_settings_updates_then_refreshes_storage_cache():
    db = MagicMock()
    user = _user()
    payload = {"storage": {"photo_storage_path": "H:/photos"}}
    new_cfg = _config("H:/photos")

    with patch.object(settings_api.config_manager, "update_user_config") as update_call, \
         patch.object(settings_api.config_manager, "get_user_config", return_value=new_cfg), \
         patch.object(settings_api, "update_storage_root_cache") as cache_call:
        result = settings_api.import_settings(payload=payload, db=db, current_user=user)

    update_call.assert_called_once_with(user.id, payload, db)
    cache_call.assert_called_once_with("H:/photos")
    assert result["status"] == "success"
    assert result["config"]["storage"]["photo_storage_path"] == "H:/photos"


def test_import_settings_skips_cache_refresh_when_storage_path_missing():
    db = MagicMock()
    user = _user()
    payload = {"display": {"theme": "dark"}}
    cfg = SimpleNamespace(storage=SimpleNamespace(photo_storage_path=None), model_dump=lambda: {"storage": {"photo_storage_path": None}})

    with patch.object(settings_api.config_manager, "update_user_config"), \
         patch.object(settings_api.config_manager, "get_user_config", return_value=cfg), \
         patch.object(settings_api, "update_storage_root_cache") as cache_call:
        settings_api.import_settings(payload=payload, db=db, current_user=user)

    cache_call.assert_not_called()


# ----------------------- GET /settings/map/countries -----------------------


def test_get_map_countries_reads_json_file(tmp_path: Path, monkeypatch):
    sample = [{"code": "CN", "name": "China"}, {"code": "US", "name": "United States"}]
    data_file = tmp_path / "countries.json"
    data_file.write_text("[{\"code\": \"CN\", \"name\": \"China\"}, {\"code\": \"US\", \"name\": \"United States\"}]", encoding="utf-8")
    monkeypatch.setattr(settings_api, "COUNTRIES_JSON_FILE", str(data_file))

    result = settings_api.get_map_countries()

    assert result == sample


def test_get_map_countries_returns_empty_when_missing(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(settings_api, "COUNTRIES_JSON_FILE", str(tmp_path / "missing.json"))
    assert settings_api.get_map_countries() == []


# ----------------------- GET /settings/map/downloaded -----------------------


def test_get_downloaded_countries_lists_csv_files(monkeypatch, tmp_path: Path):
    (tmp_path / "CN.csv").write_text("longitude,latitude\n1,1\n")
    (tmp_path / "US.csv").write_text("longitude,latitude\n2,2\n")
    (tmp_path / "ignore.txt").write_text("nope")
    monkeypatch.setattr(settings_api, "RG_DATA_DIR", str(tmp_path))
    countries = [{"code": "CN", "name": "China"}, {"code": "US", "name": "United States"}]

    with patch.object(settings_api, "get_map_countries", return_value=countries):
        result = settings_api.get_downloaded_countries()

    codes = {entry["code"] for entry in result}
    assert codes == {"CN", "US"}
    names = {entry["name"] for entry in result}
    assert names == {"China", "United States"}


def test_get_downloaded_countries_returns_empty_when_dir_missing(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(settings_api, "RG_DATA_DIR", str(tmp_path / "missing-dir"))
    assert settings_api.get_downloaded_countries() == []


# ----------------------- DELETE /settings/map/files/{filename} -----------------------


def test_delete_map_file_rejects_traversal(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(settings_api, "RG_DATA_DIR", str(tmp_path))

    with pytest.raises(HTTPException) as exc_info:
        settings_api.delete_map_file(filename="..\\evil.csv")

    assert exc_info.value.status_code == 400


def test_delete_map_file_404_when_dir_missing(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(settings_api, "RG_DATA_DIR", str(tmp_path / "missing"))
    with pytest.raises(HTTPException) as exc_info:
        settings_api.delete_map_file(filename="CN.csv")
    assert exc_info.value.status_code == 404


def test_delete_map_file_404_when_file_missing(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(settings_api, "RG_DATA_DIR", str(tmp_path))
    with pytest.raises(HTTPException) as exc_info:
        settings_api.delete_map_file(filename="nope.csv")
    assert exc_info.value.status_code == 404


def test_delete_map_file_removes_file(monkeypatch, tmp_path: Path):
    target = tmp_path / "CN.csv"
    target.write_text("x,y")
    monkeypatch.setattr(settings_api, "RG_DATA_DIR", str(tmp_path))

    result = settings_api.delete_map_file(filename="CN.csv")

    assert result == {"status": "success", "filename": "CN.csv"}
    assert not target.exists()


# ----------------------- POST /settings/map/download -----------------------


def test_download_map_data_enqueues_background_task():
    payload = {"code": "CN"}
    background_tasks = BackgroundTasks()

    with patch.object(settings_api, "download_country_data") as dl_call:
        result = settings_api.download_map_data(
            payload=payload, background_tasks=background_tasks
        )

    assert result == {"status": "downloading", "country_code": "CN"}
    assert len(background_tasks.tasks) == 1


def test_download_map_data_rejects_missing_code():
    payload = {}
    background_tasks = BackgroundTasks()

    with pytest.raises(HTTPException) as exc_info:
        settings_api.download_map_data(payload=payload, background_tasks=background_tasks)

    assert exc_info.value.status_code == 400


# ----------------------- POST /settings/verify-ai-service -----------------------


def test_verify_ai_service_returns_service_and_elapsed_time():
    response = MagicMock(status_code=200)
    response.json.return_value = {"status": "ok", "service": "TrailSnap AI"}
    with patch.object(settings_api.requests, "get", return_value=response) as get_call:
        result = settings_api.verify_ai_service(
            req=settings_api.VerifyAIServiceRequest(api_url=" http://ai:8001/ "),
            current_user=_user(),
        )

    assert result.code == 0
    assert result.data["success"] is True
    assert result.data["service"] == "TrailSnap AI"
    assert isinstance(result.data["elapsed_ms"], int)
    get_call.assert_called_once_with("http://ai:8001/health-check", timeout=5)


def test_verify_ai_service_rejects_invalid_url():
    result = settings_api.verify_ai_service(
        req=settings_api.VerifyAIServiceRequest(api_url="ai:8001"),
        current_user=_user(),
    )

    assert result.code == 400
    assert "http://" in result.msg


def test_verify_ai_service_reports_wrong_service_and_network_errors():
    response = MagicMock(status_code=200)
    response.json.return_value = {"status": "something-else"}
    with patch.object(settings_api.requests, "get", return_value=response):
        wrong_service = settings_api.verify_ai_service(
            req=settings_api.VerifyAIServiceRequest(api_url="http://example:8001"),
            current_user=_user(),
        )
    assert wrong_service.data["success"] is False
    assert "不是可识别" in wrong_service.data["message"]

    with patch.object(settings_api.requests, "get", side_effect=settings_api.requests.Timeout):
        timeout = settings_api.verify_ai_service(
            req=settings_api.VerifyAIServiceRequest(api_url="http://ai:8001"),
            current_user=_user(),
        )
    assert timeout.data["success"] is False
    assert "连接超时" in timeout.data["message"]





