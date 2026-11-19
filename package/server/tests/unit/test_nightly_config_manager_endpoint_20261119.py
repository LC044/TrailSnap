"""覆盖 app/core/config_manager.py 中 normalize_local_endpoint 校验器。

盲区来源：函数级静态引用扫描命中 normalize_local_endpoint——它是
AISettings.ai_api_url 的唯一校验入口，负责把 Windows 上旧的
http://localhost:8001 本地默认地址迁移为 127.0.0.1，但既有测试从未直接
引用过它，因此「哪些端点该迁移、哪些必须原样保留」从未被断言。
"""

from __future__ import annotations

import sys

import pytest

from app.core.ai_endpoint import normalize_ai_api_url
from app.core.config_manager import AISettings

pytestmark = [pytest.mark.smoke]


@pytest.fixture
def windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    return None


@pytest.fixture
def posix(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    return None


@pytest.mark.parametrize("value", [
    "http://localhost:8001",
    "http://LOCALHOST:8001",
])
def test_local_default_is_migrated_to_ipv4_loopback(windows, value):
    assert normalize_ai_api_url(value) == "http://127.0.0.1:8001"


@pytest.mark.parametrize("value", [
    "http://localhost:8002",
    "http://127.0.0.1:8001",
    "https://localhost:8001",
    "http://example.com:8001",
])
def test_explicit_endpoints_are_preserved(windows, value):
    assert normalize_ai_api_url(value) == value


def test_non_windows_platform_keeps_localhost(posix):
    assert normalize_ai_api_url("http://localhost:8001") == "http://localhost:8001"


def test_ai_settings_validator_applies_the_migration(windows):
    settings = AISettings(ai_api_url="http://localhost:8001")
    assert settings.ai_api_url == "http://127.0.0.1:8001"


def test_ai_settings_validator_keeps_custom_port(windows):
    settings = AISettings(ai_api_url="http://localhost:9000")
    assert settings.ai_api_url == "http://localhost:9000"
