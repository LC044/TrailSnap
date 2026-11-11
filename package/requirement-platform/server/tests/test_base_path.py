"""Deployment URL prefix (RP_BASE_PATH) behaviour."""
from dataclasses import replace

import pytest

from requirement_platform.config import (
    apply_base_path,
    derive_web_url,
    normalize_base_path,
    settings,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, ""),
        ("", ""),
        ("  ", ""),
        ("/", ""),
        ("///", ""),
        ("issues", "/issues"),
        ("/issues", "/issues"),
        ("/issues/", "/issues"),
        ("  /feedback/issues/  ", "/feedback/issues"),
        ("/v1.2-beta_1", "/v1.2-beta_1"),
    ],
)
def test_normalize_base_path(raw, expected):
    assert normalize_base_path(raw) == expected


@pytest.mark.parametrize("raw", ["/../etc", "/issues/../admin", "/a b", "/is?s=1", "/is#frag", "/a//../b"])
def test_normalize_base_path_rejects_unsafe_segments(raw):
    with pytest.raises(ValueError, match="RP_BASE_PATH"):
        normalize_base_path(raw)


@pytest.mark.parametrize(
    ("url", "base", "expected"),
    [
        ("https://example.com/api/auth/github/callback", "/issues", "https://example.com/issues/api/auth/github/callback"),
        ("https://example.com/mcp/", "/issues", "https://example.com/issues/mcp/"),
        ("https://example.com", "/issues", "https://example.com/issues"),
        ("https://example.com/issues/mcp/", "/issues", "https://example.com/issues/mcp/"),
        ("https://example.com/mcp/", "", "https://example.com/mcp/"),
        ("/relative/path", "/issues", "/relative/path"),
    ],
)
def test_apply_base_path(url, base, expected):
    assert apply_base_path(url, base) == expected
    # Applying twice must not stack the prefix.
    assert apply_base_path(expected, base) == expected


@pytest.mark.parametrize(
    ("raw", "base", "expected"),
    [
        ("https://example.com", "/issues", "https://example.com"),
        ("https://example.com/", "/issues", "https://example.com"),
        ("https://example.com/issues", "/issues", "https://example.com"),
        ("https://example.com/issues/", "/issues", "https://example.com"),
        ("https://example.com/other", "/issues", "https://example.com/other"),
        ("https://example.com", "", "https://example.com"),
    ],
)
def test_derive_web_url(raw, base, expected):
    assert derive_web_url(raw, base) == expected


def test_settings_public_urls_with_prefix():
    prefixed = replace(settings, web_url="https://example.com", base_path="/issues")
    assert prefixed.public_base_url == "https://example.com/issues"
    assert prefixed.public_url() == "https://example.com/issues"
    assert prefixed.public_url("requirements/REQ-12") == "https://example.com/issues/requirements/REQ-12"
    assert prefixed.api_path() == "/issues/api"
    assert prefixed.api_path("auth/github") == "/issues/api/auth/github"


def test_settings_public_urls_at_root():
    root = replace(settings, web_url="https://example.com", base_path="")
    assert root.public_base_url == "https://example.com"
    assert root.public_url("requirements/REQ-12") == "https://example.com/requirements/REQ-12"
    assert root.api_path("auth/github") == "/api/auth/github"


def test_agent_guide_uses_prefixed_public_urls(monkeypatch):
    from requirement_platform import public_agent_guide

    monkeypatch.setattr(
        public_agent_guide, "settings",
        replace(settings, web_url="https://example.com", base_path="/issues"),
    )
    guide = public_agent_guide.agent_guide()
    assert "GET https://example.com/issues/api/requirements" in guide
    assert "https://example.com/issues/requirements/REQ-编号" in guide
    assert "GET https://example.com/api/requirements?" not in guide
