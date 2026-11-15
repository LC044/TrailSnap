from types import SimpleNamespace

import pytest

from app.core import ai_endpoint
from app.core.config_manager import AISettings, config_manager

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


@pytest.mark.parametrize("url,expected", [
    ("http://localhost:8001", "http://127.0.0.1:8001"),
    ("http://LOCALHOST:8001/prefix/", "http://127.0.0.1:8001/prefix/"),
    ("http://localhost:9001", "http://localhost:9001"),
    ("https://localhost:8001", "https://localhost:8001"),
    ("http://ai:8001", "http://ai:8001"),
    ("http://[::1]:8001", "http://[::1]:8001"),
    ("http://192.168.1.10:8001", "http://192.168.1.10:8001"),
])
def test_windows_local_default_only(monkeypatch, url, expected):
    monkeypatch.setattr(ai_endpoint, "sys", SimpleNamespace(platform="win32"))
    assert AISettings(ai_api_url=url).ai_api_url == expected


def test_non_windows_explicit_localhost_is_preserved(monkeypatch):
    monkeypatch.setattr(ai_endpoint, "sys", SimpleNamespace(platform="linux"))
    assert AISettings(ai_api_url="http://localhost:8001").ai_api_url == "http://localhost:8001"


def test_legacy_user_config_also_updates_builtin_connection(monkeypatch):
    monkeypatch.setattr(ai_endpoint, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.delenv("TS_DESKTOP_AI_GATEWAY", raising=False)
    cfg = config_manager.merge_user_settings({"ai": {
        "ai_api_url": "http://localhost:8001",
        "connections": [{"id": "builtin", "provider": "Built-in AI",
                         "api_base": "http://localhost:8001/v1"}],
    }})
    assert cfg.ai.ai_api_url == "http://127.0.0.1:8001"
    assert cfg.ai.connections[0].api_base == "http://127.0.0.1:8001/v1"


def test_desktop_gateway_overrides_old_default(monkeypatch):
    monkeypatch.setenv("TS_DESKTOP_AI_GATEWAY", "http://127.0.0.1:54321")
    cfg = config_manager.merge_user_settings({"ai": {"ai_api_url": "http://localhost:8001"}})
    assert cfg.ai.ai_api_url == "http://127.0.0.1:54321"
    assert cfg.ai.connections[0].api_base == "http://127.0.0.1:54321/v1"
