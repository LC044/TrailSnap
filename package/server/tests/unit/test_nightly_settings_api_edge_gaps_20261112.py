"""Nightly watch 2026-11-12 · app/api/settings.py 错误分支盲区补测。

被测模块：app/api/settings.py
覆盖点（2026-11-12 覆盖率基线中未触达的分支）：
- GET /map/runtime：地图提供商不支持、缺少 API Key。
- POST /directories：路径非法、目标用户不存在。
- POST /map/upload：非 UTF-8 编码、空文件。
- GET /map/files/{filename}：文件不存在。
- DELETE /map/files/{filename}：删除失败时返回 500。

所有依赖均通过 monkeypatch / patch 打桩，不触网、不读真实图库。
"""

import io
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, UploadFile

from app.api import settings as settings_api

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def _map_config(provider="tianditu", api_keys=("key-1",)):
    return SimpleNamespace(map=SimpleNamespace(provider=provider, api_keys=list(api_keys)))


def _upload(name, payload: bytes) -> UploadFile:
    return UploadFile(file=io.BytesIO(payload), filename=name)


# ----------------------- GET /map/runtime -----------------------


def test_map_runtime_rejects_unsupported_provider():
    db = MagicMock()
    user = SimpleNamespace(id=uuid4())
    with patch.object(settings_api.config_manager, "get_user_config",
                      return_value=_map_config(provider="google")):
        with pytest.raises(HTTPException) as excinfo:
            settings_api.get_map_runtime(db=db, current_user=user)
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "暂不支持该地图提供商"


def test_map_runtime_requires_api_key():
    db = MagicMock()
    user = SimpleNamespace(id=uuid4())
    with patch.object(settings_api.config_manager, "get_user_config",
                      return_value=_map_config(api_keys=("  ",))):
        with pytest.raises(HTTPException) as excinfo:
            settings_api.get_map_runtime(db=db, current_user=user)
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Map API Key is missing"


def test_map_runtime_issues_scoped_token():
    db = MagicMock()
    user = SimpleNamespace(id=uuid4())
    with patch.object(settings_api.config_manager, "get_user_config",
                      return_value=_map_config()), \
         patch.object(settings_api.security, "create_access_token", return_value="tok") as create:
        result = settings_api.get_map_runtime(db=db, current_user=user)
    assert result.data["access_token"] == "tok"
    assert create.call_args.args[0]["scope"] == "map_proxy"


# ----------------------- POST /directories -----------------------


def test_add_directory_rejects_invalid_path():
    db = MagicMock()
    user = SimpleNamespace(id=uuid4(), is_superuser=True, settings={})
    with pytest.raises(HTTPException) as excinfo:
        settings_api.add_directory(payload={}, db=db, current_user=user)
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "invalid path"


def test_add_directory_rejects_missing_target_user():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    user = SimpleNamespace(id=uuid4(), is_superuser=True, settings={})
    payload = {"user_id": str(uuid4()), "path": "E:/photos"}
    with pytest.raises(HTTPException) as excinfo:
        settings_api.add_directory(payload=payload, db=db, current_user=user)
    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "User not found"


# ----------------------- POST /map/upload -----------------------


@pytest.mark.asyncio
async def test_upload_map_data_rejects_non_utf8_encoding():
    with pytest.raises(HTTPException) as excinfo:
        await settings_api.upload_map_data(file=_upload("cn.csv", b"\xff\xfe\x00bad"))
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Invalid encoding"


@pytest.mark.asyncio
async def test_upload_map_data_rejects_empty_file():
    with pytest.raises(HTTPException) as excinfo:
        await settings_api.upload_map_data(file=_upload("cn.csv", b""))
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Empty file"


@pytest.mark.asyncio
async def test_upload_map_data_rejects_non_csv_extension():
    with pytest.raises(HTTPException) as excinfo:
        await settings_api.upload_map_data(file=_upload("cn.txt", b"longitude,latitude"))
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Only CSV files are allowed"


# ----------------------- map file download / delete -----------------------


def test_download_map_file_returns_404_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_api, "RG_DATA_DIR", str(tmp_path))
    with pytest.raises(HTTPException) as excinfo:
        settings_api.download_map_file("cn.csv")
    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "File not found"


def test_download_map_file_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_api, "RG_DATA_DIR", str(tmp_path))
    with pytest.raises(HTTPException) as excinfo:
        settings_api.download_map_file(os.path.join("..", "secret.csv"))
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Invalid filename"


def test_delete_map_file_reports_os_error(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_api, "RG_DATA_DIR", str(tmp_path))
    target = tmp_path / "cn.csv"
    target.write_text("longitude,latitude", encoding="utf-8")
    with patch.object(settings_api.os, "remove", side_effect=OSError("locked")):
        with pytest.raises(HTTPException) as excinfo:
            settings_api.delete_map_file("cn.csv")
    assert excinfo.value.status_code == 500
    assert "Error deleting file" in excinfo.value.detail

