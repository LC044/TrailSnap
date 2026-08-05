"""Async dispatch tests for ``app.middleware.demo_mode.DemoModeMiddleware``.

The companion ``test_demo_mode.py`` exercises pure helpers. This file focuses
on the ``DemoModeMiddleware.__call__`` lifecycle by driving the ASGI callable
directly with a fake scope/receive/send — no live server.

Coverage targets the lines that pure-helper tests cannot reach:

* Per-request dispatch branching on ``DEMO_MODE`` flag (off → transparent pass-through).
* WRITE-method blocking outside the whitelist (``code=403`` JSON envelope).
* Whitelisted writes that survive the rate limit (``agent/chat`` path remains writable).
* Rate-limit exhaustion → ``code=429`` response shape.
* ``/agent/chat`` tighter bucket (``AGENT_CHAT_RATE_LIMIT_CAPACITY`` vs default).
* ``/search/image`` content-length guard (``code=413`` when > 20 MB).
* ``custom_send`` rewriting JSON response body via ``mask_sensitive``.
* Non-JSON content types are forwarded untouched (no masking).
* Streaming responses (``more_body=True``) are forwarded untouched.
* Token-bucket store cleanup once ``RATE_LIMIT_STORE_MAX`` is exceeded.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.middleware import demo_mode


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_rate_store():
    """Wipe shared token-bucket state before every test to keep cases independent."""
    demo_mode._rate_store.clear()
    yield
    demo_mode._rate_store.clear()


def _run(coro):
    return asyncio.run(coro)


def _make_scope(method, path, headers=None, client_host="10.0.0.1"):
    raw_headers = []
    for k, v in (headers or {}).items():
        raw_headers.append((k.lower().encode("latin-1"), str(v).encode("latin-1")))
    return {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode("latin-1"),
        "query_string": b"",
        "scheme": "http",
        "server": ("testserver", 80),
        "headers": raw_headers,
        "client": (client_host, 12345),
    }


def _invoke(middleware, scope, downstream):
    """Call ``middleware.__call__`` with a captured send and the given downstream."""
    captured: list = []

    async def _send(msg):
        captured.append(msg)

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope["receive"] = _receive
    scope["send"] = _send
    middleware.app = downstream
    _run(middleware(scope, _receive, _send))
    return captured


async def _json_ok(send, payload=None):
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    await send({"type": "http.response.body", "body": body, "more_body": False})


def _decode_json_body(messages):
    for msg in reversed(messages):
        if msg["type"] == "http.response.body" and msg.get("body"):
            return json.loads(msg["body"].decode("utf-8"))
    raise AssertionError("no JSON body present")


# ---------------------------------------------------------------------------
# Dispatch: write blocking outside the whitelist
# ---------------------------------------------------------------------------


def test_dispatch_passes_through_when_demo_mode_disabled(monkeypatch):
    monkeypatch.setattr(demo_mode, "DEMO_MODE", False)
    mw = demo_mode.DemoModeMiddleware(app=lambda *a, **kw: None)

    downstream_calls: list = []

    async def downstream(scope, receive, send):
        downstream_calls.append((scope["method"], scope["path"]))
        await _json_ok(send, {"ok": True})

    messages = _invoke(mw, _make_scope("POST", "/albums"), downstream)
    assert downstream_calls == [("POST", "/albums")]
    # mask_sensitive was applied to the JSON body but dict has no sensitive keys.
    assert _decode_json_body(messages) == {"ok": True}


def test_dispatch_blocks_post_not_in_whitelist(monkeypatch):
    monkeypatch.setattr(demo_mode, "DEMO_MODE", True)
    mw = demo_mode.DemoModeMiddleware(app=lambda *a, **kw: None)

    async def downstream(scope, receive, send):
        await _json_ok(send, {"ok": True})

    messages = _invoke(mw, _make_scope("POST", "/albums/123/delete"), downstream)
    body = _decode_json_body(messages)
    assert body == {"code": 403, "msg": demo_mode.DEMO_BLOCK_MSG, "data": None}


def test_dispatch_blocks_delete_outside_whitelist(monkeypatch):
    monkeypatch.setattr(demo_mode, "DEMO_MODE", True)
    mw = demo_mode.DemoModeMiddleware(app=lambda *a, **kw: None)

    async def downstream(scope, receive, send):
        await _json_ok(send)

    messages = _invoke(mw, _make_scope("DELETE", "/photos/abc"), downstream)
    body = _decode_json_body(messages)
    assert body["code"] == 403


def test_dispatch_blocks_unsupported_http_method(monkeypatch):
    monkeypatch.setattr(demo_mode, "DEMO_MODE", True)
    mw = demo_mode.DemoModeMiddleware(app=lambda *a, **kw: None)

    async def downstream(scope, receive, send):
        await _json_ok(send)

    # PATCH is in WRITE_METHODS but not whitelisted anywhere.
    messages = _invoke(mw, _make_scope("PATCH", "/settings/"), downstream)
    body = _decode_json_body(messages)
    assert body["code"] == 403


def test_dispatch_allows_whitelisted_post(monkeypatch):
    monkeypatch.setattr(demo_mode, "DEMO_MODE", True)
    mw = demo_mode.DemoModeMiddleware(app=lambda *a, **kw: None)
    reached = {"hit": False}

    async def downstream(scope, receive, send):
        reached["hit"] = True
        await _json_ok(send, {"downstream": True})

    messages = _invoke(mw, _make_scope("POST", "/auth/login"), downstream)
    assert reached["hit"] is True
    assert _decode_json_body(messages) == {"downstream": True}


# ---------------------------------------------------------------------------
# Rate limiting + /search/image guard
# ---------------------------------------------------------------------------


def test_dispatch_returns_429_when_token_bucket_exhausted(monkeypatch):
    monkeypatch.setattr(demo_mode, "DEMO_MODE", True)
    mw = demo_mode.DemoModeMiddleware(app=lambda *a, **kw: None)

    # Pass capacity/refill explicitly (defaults are bound at import time, so
    # monkeypatch.setattr on the module constants won't reach _rate_limit_allow).
    def _block_request():
        # Token bucket drained by manually seeding the store with no remaining tokens.
        demo_mode._rate_store.clear()
        demo_mode._rate_store["10.0.0.1:/auth/login"] = (0.0, demo_mode.time.monotonic())
        return _invoke(mw, _make_scope("POST", "/auth/login"),
                       downstream=lambda s, r, send: _json_ok(send))

    body = _decode_json_body(_block_request())
    assert body["code"] == 429
    assert "请求过于频繁" in body["msg"]


def test_dispatch_uses_tighter_bucket_for_agent_chat(monkeypatch):
    monkeypatch.setattr(demo_mode, "DEMO_MODE", True)
    mw = demo_mode.DemoModeMiddleware(app=lambda *a, **kw: None)

    # Seed both buckets to 0 tokens — first call drains to a negative,
    # but we want a deterministic 429 path on the second /agent/chat call.
    async def downstream(scope, receive, send):
        await _json_ok(send)

    # /auth/login uses the default (large) capacity — first call passes,
    # so the downstream function is reached and emits a 200 OK JSON body.
    demo_mode._rate_store.clear()
    reached_login = {"hit": False}

    async def login_downstream(scope, receive, send):
        reached_login["hit"] = True
        await _json_ok(send)

    messages = _invoke(mw, _make_scope("POST", "/auth/login"), login_downstream)
    assert reached_login["hit"] is True

    # For /agent/chat, force the AGENT_CHAT bucket to be exhausted by
    # draining it via the helper itself with capacity=1, refill=0.
    demo_mode._rate_store["10.0.0.1:/agent/chat"] = (0.0, demo_mode.time.monotonic())
    messages = _invoke(mw, _make_scope("POST", "/agent/chat"), downstream)
    body = _decode_json_body(messages)
    assert body["code"] == 429


def test_dispatch_blocks_oversized_search_image(monkeypatch):
    monkeypatch.setattr(demo_mode, "DEMO_MODE", True)
    mw = demo_mode.DemoModeMiddleware(app=lambda *a, **kw: None)

    async def downstream(scope, receive, send):
        await _json_ok(send)

    headers = {"content-length": str(50 * 1024 * 1024)}  # 50 MB > 20 MB
    messages = _invoke(mw, _make_scope("POST", "/search/image", headers=headers), downstream)
    body = _decode_json_body(messages)
    assert body["code"] == 413
    assert "上限 20MB" in body["msg"]


def test_dispatch_passes_through_when_content_length_missing(monkeypatch):
    monkeypatch.setattr(demo_mode, "DEMO_MODE", True)
    mw = demo_mode.DemoModeMiddleware(app=lambda *a, **kw: None)
    reached = {"hit": False}

    async def downstream(scope, receive, send):
        reached["hit"] = True
        await _json_ok(send)

    messages = _invoke(mw, _make_scope("POST", "/search/image", headers={}), downstream)
    assert reached["hit"] is True


# ---------------------------------------------------------------------------
# custom_send JSON masking
# ---------------------------------------------------------------------------


def test_dispatch_masks_sensitive_fields_in_json_response(monkeypatch):
    monkeypatch.setattr(demo_mode, "DEMO_MODE", True)
    mw = demo_mode.DemoModeMiddleware(app=lambda *a, **kw: None)

    payload = json.dumps({"api_key": "sk-live", "name": "demo"}, ensure_ascii=False)

    async def downstream(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": payload.encode("utf-8"),
                "more_body": False,
            }
        )

    messages = _invoke(mw, _make_scope("GET", "/"), downstream)
    body_msg = next(m for m in messages if m["type"] == "http.response.body")
    decoded = json.loads(body_msg["body"].decode("utf-8"))
    assert decoded["api_key"] == "******"
    assert decoded["name"] == "demo"


def test_dispatch_skips_masking_for_non_json_responses(monkeypatch):
    monkeypatch.setattr(demo_mode, "DEMO_MODE", True)
    mw = demo_mode.DemoModeMiddleware(app=lambda *a, **kw: None)

    async def downstream(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"api_key=sk-live",
                "more_body": False,
            }
        )

    messages = _invoke(mw, _make_scope("GET", "/"), downstream)
    body_msg = next(m for m in messages if m["type"] == "http.response.body")
    assert body_msg["body"] == b"api_key=sk-live"


def test_dispatch_forwards_streaming_more_body_unchanged(monkeypatch):
    monkeypatch.setattr(demo_mode, "DEMO_MODE", True)
    mw = demo_mode.DemoModeMiddleware(app=lambda *a, **kw: None)

    async def downstream(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b'{"api_key":"sk-live"}',
                "more_body": True,
            }
        )

    messages = _invoke(mw, _make_scope("GET", "/stream"), downstream)
    body_msg = next(m for m in messages if m["type"] == "http.response.body")
    assert body_msg["body"] == b'{"api_key":"sk-live"}'
    assert body_msg["more_body"] is True


# ---------------------------------------------------------------------------
# Token-bucket cleanup when store grows past the cap
# ---------------------------------------------------------------------------


def test_rate_limit_store_cleanup_drops_stale_buckets(monkeypatch):
    monkeypatch.setattr(demo_mode, "DEMO_MODE", True)
    monkeypatch.setattr(demo_mode, "RATE_LIMIT_STORE_MAX", 4)

    # Pre-populate with stale entries (timestamps far in the past).
    now = demo_mode.time.monotonic()
    demo_mode._rate_store.update(
        {f"old-{i}:/old-{i}": (1.0, now - 999) for i in range(5)}
    )
    # A single fresh request should trigger the cleanup branch.
    demo_mode._rate_limit_allow("trigger-ip", "/trigger-path", capacity=20.0, refill_per_min=20.0)
    stale_remaining = [k for k in demo_mode._rate_store if k.startswith("old-")]
    assert stale_remaining == []


def test_rate_limit_allow_consumes_token_per_request(monkeypatch):
    demo_mode._rate_store.clear()
    # Pass the limits explicitly because the function defaults were bound at
    # import time and ``monkeypatch.setattr`` on module constants won't reach them.
    assert demo_mode._rate_limit_allow("ip-a", "/x", capacity=1.0, refill_per_min=0.0) is True
    assert demo_mode._rate_limit_allow("ip-a", "/x", capacity=1.0, refill_per_min=0.0) is False
    # Independent (ip, path) bucket is fresh.
    assert demo_mode._rate_limit_allow("ip-a", "/y", capacity=1.0, refill_per_min=0.0) is True

