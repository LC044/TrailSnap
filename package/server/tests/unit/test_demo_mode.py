"""Unit tests for app.middleware.demo_mode helpers.

Covers the pure-Python helpers that live alongside DemoModeMiddleware so the
middleware class itself stays untouched (its full async dispatch is exercised
by the integration suite):

- _truthy: str truthiness parser used for env var flags.
- is_whitelisted_write: prefix matching against the WRITE-method whitelist.
- _content_length: parses Content-Length header defensively.
- _client_ip: prefers the first X-Forwarded-For entry, falls back to client.host.
- _mask_value: returns placeholder per type.
- mask_sensitive: recursive dict/list redaction using SENSITIVE_KEYS.

The class DemoModeMiddleware and the async ``__call__`` dispatch are not
unit-tested here because they require a live ASGI server.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.middleware import demo_mode


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


# ---------------------------------------------------------------------------
# _truthy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value,expected", [
    ("1", True),
    ("true", True),
    ("TRUE", True),
    (" yes ", True),
    ("on", True),
    ("0", False),
    ("false", False),
    ("", False),
    (None, False),
    ("random", False),
])
def test_truthy_parses_env_flags(value, expected):
    assert demo_mode._truthy(value) is expected


# ---------------------------------------------------------------------------
# is_whitelisted_write
# ---------------------------------------------------------------------------


def test_is_whitelisted_write_matches_exact_path():
    assert demo_mode.is_whitelisted_write("POST", "/auth/login") is True


def test_is_whitelisted_write_matches_subpath():
    assert demo_mode.is_whitelisted_write("POST", "/agent/chat/abc-123/abort") is True


def test_is_whitelisted_write_rejects_similar_prefix():
    # /search/textimage must NOT be matched by the /search/text whitelist.
    assert demo_mode.is_whitelisted_write("POST", "/search/textimage") is False


def test_is_whitelisted_write_rejects_wrong_method():
    # /agent/chat is whitelisted for POST only; DELETE should not match.
    assert demo_mode.is_whitelisted_write("DELETE", "/agent/chat") is False


def test_is_whitelisted_write_rejects_unrelated_path():
    assert demo_mode.is_whitelisted_write("POST", "/albums/create") is False


def test_is_whitelisted_write_handles_missing_trailing_slash_in_prefix():
    # If a whitelist entry were registered without a trailing slash but the
    # request has sub-paths, the boundary check still has to honour the
    # 'prefix + /' boundary rule. Build an ad-hoc whitelist for the test.
    original = demo_mode.WHITELIST
    demo_mode.WHITELIST = [("POST", "/foo")]
    try:
        assert demo_mode.is_whitelisted_write("POST", "/foo/bar") is True
        assert demo_mode.is_whitelisted_write("POST", "/foobar") is False
    finally:
        demo_mode.WHITELIST = original


# ---------------------------------------------------------------------------
# _content_length
# ---------------------------------------------------------------------------


def test_content_length_parses_valid_header():
    request = MagicMock()
    request.headers = {"content-length": "1024"}
    assert demo_mode._content_length(request) == 1024


def test_content_length_returns_none_when_missing():
    request = MagicMock()
    request.headers = {}
    assert demo_mode._content_length(request) is None


def test_content_length_returns_none_on_garbage_value():
    request = MagicMock()
    request.headers = {"content-length": "abc"}
    assert demo_mode._content_length(request) is None


# ---------------------------------------------------------------------------
# _client_ip
# ---------------------------------------------------------------------------


def test_client_ip_prefers_first_xff_entry():
    request = SimpleNamespace(
        headers={"x-forwarded-for": "1.2.3.4, 5.6.7.8"},
        client=SimpleNamespace(host="9.9.9.9"),
    )
    assert demo_mode._client_ip(request) == "1.2.3.4"


def test_client_ip_falls_back_to_tcp_when_xff_missing():
    request = SimpleNamespace(
        headers={},
        client=SimpleNamespace(host="9.9.9.9"),
    )
    assert demo_mode._client_ip(request) == "9.9.9.9"


def test_client_ip_falls_back_to_unknown_when_no_client():
    request = SimpleNamespace(headers={}, client=None)
    assert demo_mode._client_ip(request) == "unknown"


def test_client_ip_blank_first_entry_falls_back_to_client_host():
    # Current behaviour: a blank first XFF entry causes the parser to fall back
    # to client.host because the empty string short-circuits ``if first:``.
    request = SimpleNamespace(
        headers={"x-forwarded-for": ", 5.6.7.8"},
        client=SimpleNamespace(host="9.9.9.9"),
    )
    assert demo_mode._client_ip(request) == "9.9.9.9"


# ---------------------------------------------------------------------------
# _mask_value
# ---------------------------------------------------------------------------


def test_mask_value_redacts_list_to_empty():
    assert demo_mode._mask_value(["a", "b"]) == []


def test_mask_value_redacts_dict_to_empty_dict():
    assert demo_mode._mask_value({"x": 1}) == {}


def test_mask_value_redacts_scalars_to_placeholder():
    assert demo_mode._mask_value("sk-xxx") == "******"
    assert demo_mode._mask_value(42) == "******"
    assert demo_mode._mask_value(True) == "******"


# ---------------------------------------------------------------------------
# mask_sensitive
# ---------------------------------------------------------------------------


def test_mask_sensitive_redacts_top_level_sensitive_keys():
    payload = {"api_key": "sk-1", "name": "demo"}
    demo_mode.mask_sensitive(payload)
    assert payload["api_key"] == "******"
    assert payload["name"] == "demo"


def test_mask_sensitive_redacts_nested_dict():
    payload = {"outer": {"secret_key": "shh", "safe": 1}}
    demo_mode.mask_sensitive(payload)
    assert payload["outer"]["secret_key"] == "******"
    assert payload["outer"]["safe"] == 1


def test_mask_sensitive_redacts_inside_lists():
    payload = {"items": [{"password": "p"}, {"password": "q"}]}
    demo_mode.mask_sensitive(payload)
    assert payload["items"][0]["password"] == "******"
    assert payload["items"][1]["password"] == "******"


def test_mask_sensitive_is_case_insensitive():
    payload = {"API_KEY": "sk-1", "Ai_Api_Url": "x"}
    demo_mode.mask_sensitive(payload)
    assert payload["API_KEY"] == "******"
    assert payload["Ai_Api_Url"] == "******"


def test_mask_sensitive_keeps_non_sensitive_payloads_intact():
    payload = {"name": "demo", "tags": ["a", "b"]}
    demo_mode.mask_sensitive(payload)
    assert payload == {"name": "demo", "tags": ["a", "b"]}


def test_mask_sensitive_preserves_map_keys_for_demo_map_loading():
    payload = {
        "map": {"provider": "tianditu", "api_keys": ["map-key-1"]},
        "ai": {"api_keys": ["ai-key-1"], "api_key": "ai-key-2"},
    }

    demo_mode.mask_sensitive(payload)

    assert payload["map"]["api_keys"] == ["map-key-1"]
    assert payload["ai"]["api_keys"] == []
    assert payload["ai"]["api_key"] == "******"
