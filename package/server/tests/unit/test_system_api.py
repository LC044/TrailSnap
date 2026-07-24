"""Unit tests for the system REST router (app/api/system.py).

Covers the three concerns in this thin module:

- ``/config`` GET + PUT  -- superuser-only, with dict-merge semantics
  on PUT so partial updates (e.g. ``{"security": {"allow_registration": false}}``)
  dont have to re-send every nested key.
- ``/version`` GET       -- returns the package ``VERSION`` constant.
- ``/update-check`` GET  -- wraps ``app.service.update_checker.fetch_remote_update_info``
  and surfaces both the success and the network/parse failure paths.

We patch the ``system_config`` singleton directly so we dont touch
``./data/system_config.json`` on disk and dont depend on FastAPI
``TestClient`` startup.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api import system as system_api
from app.core.config_manager import VERSION


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def _user(is_superuser=False):
    return SimpleNamespace(id="u-1", is_superuser=is_superuser)


# ----------------------------- /config -----------------------------------


def test_get_system_config_requires_superuser():
    user = _user(is_superuser=False)
    with pytest.raises(HTTPException) as exc_info:
        system_api.get_system_config(current_user=user)
    assert exc_info.value.status_code == 403


def test_get_system_config_returns_dump_for_superuser():
    user = _user(is_superuser=True)
    fake_dump = {"security": {"allow_registration": True}, "task": {}}
    fake_config = SimpleNamespace(model_dump=lambda: fake_dump)

    with patch.object(system_api.system_config, "config", fake_config):
        result = system_api.get_system_config(current_user=user)

    assert result == fake_dump


def test_update_system_config_requires_superuser():
    user = _user(is_superuser=False)
    with pytest.raises(HTTPException) as exc_info:
        system_api.update_system_config(payload={"security": {}}, current_user=user)
    assert exc_info.value.status_code == 403


def _make_settings_factory(captured):
    class _FakeSettings:
        def __init__(self, **kwargs):
            captured["init"] = kwargs
            self._data = kwargs

        def model_dump(self):
            return self._data

    return _FakeSettings


def test_update_system_config_merges_nested_dict_and_saves():
    user = _user(is_superuser=True)
    existing = {
        "security": {"allow_registration": True, "secret_key": "old"},
        "task": {"concurrency_level": "low"},
    }
    payload = {"security": {"allow_registration": False}}

    fake_manager = MagicMock()
    fake_manager.config.model_dump.return_value = existing

    captured = {}
    FakeSettings = _make_settings_factory(captured)

    with patch.object(system_api.system_config, "config", fake_manager.config):
        with patch.object(system_api.system_config, "save") as fake_save:
            with patch("app.core.system_config.SystemSettings", FakeSettings):
                result = system_api.update_system_config(payload=payload, current_user=user)

    assert captured["init"]["security"]["allow_registration"] is False
    assert captured["init"]["security"]["secret_key"] == "old"
    assert captured["init"]["task"]["concurrency_level"] == "low"

    fake_save.assert_called_once_with()
    assert result["status"] == "success"
    assert result["config"] == captured["init"]


def test_update_system_config_replaces_non_dict_fields():
    user = _user(is_superuser=True)
    existing = {
        "security": {"allow_registration": True},
        "recycle_bin": {"retention_days": 7, "cleanup_time": "00:00"},
    }

    fake_manager = MagicMock()
    fake_manager.config.model_dump.return_value = existing

    captured = {}
    FakeSettings = _make_settings_factory(captured)

    with patch.object(system_api.system_config, "config", fake_manager.config):
        with patch.object(system_api.system_config, "save") as fake_save:
            with patch("app.core.system_config.SystemSettings", FakeSettings):
                system_api.update_system_config(
                    payload={"recycle_bin": {"retention_days": 30}}, current_user=user
                )

    assert captured["init"]["recycle_bin"]["retention_days"] == 30
    assert captured["init"]["recycle_bin"]["cleanup_time"] == "00:00"
    fake_save.assert_called_once_with()


# ----------------------------- /version ----------------------------------


def test_get_version_returns_package_version_constant():
    result = system_api.get_version()
    assert result == {"version": VERSION}
    assert isinstance(result["version"], str) and result["version"]


# ----------------------------- /update-check ------------------------------


def test_check_update_returns_has_update_true_with_payload():
    info = {
        "latest_version": "9.9.9",
        "has_update": True,
        "update_info": "new stuff",
        "download_url": "https://example/dl",
    }

    async def _fake_fetch(**kwargs):
        return info

    with patch("app.api.system.fetch_remote_update_info", side_effect=_fake_fetch):
        result = asyncio.run(system_api.check_update())

    assert result["current_version"] == VERSION
    assert result["latest_version"] == "9.9.9"
    assert result["has_update"] is True
    assert result["update_info"] == "new stuff"
    assert result["download_url"] == "https://example/dl"


def test_check_update_returns_error_payload_when_fetch_returns_none():
    async def _fake_fetch(**kwargs):
        return None

    with patch("app.api.system.fetch_remote_update_info", side_effect=_fake_fetch):
        result = asyncio.run(system_api.check_update())

    assert result["current_version"] == VERSION
    assert result["latest_version"] is None
    assert result["has_update"] is False
    assert result["error"] == "Failed to check for updates"

