"""Nightly coverage for the MCP server helpers of ``app/service/mcp_server.py``
(2026-10-26).

The 2026-10-26 backend coverage scan listed ``service/mcp_server.py`` at
79.4% with 35 missed lines.  The missed lines sat in the pure helpers that
guard every MCP tool call:

* ``_approval_url`` never built the explicit ``TRAILSNAP_MCP_URL`` variant
* ``_principal`` never rejected a token without a subject or without the
  required scope
* ``_parse_date`` never rejected a malformed date
* ``search_photos`` never rejected an inverted date range or an unknown
  orientation

Those helpers are plain functions, so they are driven directly.
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# _approval_url
# ---------------------------------------------------------------------------


def test_approval_url_prefers_the_public_url(monkeypatch):
    from app.service import mcp_server

    monkeypatch.setenv("TRAILSNAP_PUBLIC_URL", "https://trailsnap.example/")
    monkeypatch.delenv("TRAILSNAP_MCP_URL", raising=False)

    plan_id = uuid.uuid4()
    assert mcp_server._approval_url(plan_id) == f"https://trailsnap.example/agent/actions/{plan_id}"


def test_approval_url_falls_back_to_the_explicit_mcp_url(monkeypatch):
    from app.service import mcp_server

    monkeypatch.delenv("TRAILSNAP_PUBLIC_URL", raising=False)
    monkeypatch.setenv("TRAILSNAP_MCP_URL", "https://mcp.example/sse")

    plan_id = uuid.uuid4()
    assert mcp_server._approval_url(plan_id) == f"https://mcp.example/agent/actions/{plan_id}"


def test_approval_url_is_relative_without_any_configuration(monkeypatch):
    from app.service import mcp_server

    monkeypatch.delenv("TRAILSNAP_PUBLIC_URL", raising=False)
    monkeypatch.delenv("TRAILSNAP_MCP_URL", raising=False)

    plan_id = uuid.uuid4()
    assert mcp_server._approval_url(plan_id) == f"/agent/actions/{plan_id}"


def test_approval_url_ignores_an_mcp_url_without_a_host(monkeypatch):
    from app.service import mcp_server

    monkeypatch.delenv("TRAILSNAP_PUBLIC_URL", raising=False)
    monkeypatch.setenv("TRAILSNAP_MCP_URL", "not-a-url")

    plan_id = uuid.uuid4()
    assert mcp_server._approval_url(plan_id) == f"/agent/actions/{plan_id}"


# ---------------------------------------------------------------------------
# _principal
# ---------------------------------------------------------------------------


def _token(subject=None, scopes=()):
    from mcp.server.auth.provider import AccessToken

    return AccessToken(token="token", client_id="client", scopes=list(scopes), subject=subject)


def test_principal_rejects_a_missing_token(monkeypatch):
    from app.service import mcp_server
    from mcp.server.mcpserver.exceptions import ToolError

    monkeypatch.setattr(mcp_server, "get_access_token", lambda: None)

    with pytest.raises(ToolError, match="无法识别 Agent Token 所属用户"):
        mcp_server._principal("photos:read")


def test_principal_rejects_a_token_without_a_subject(monkeypatch):
    from app.service import mcp_server
    from mcp.server.mcpserver.exceptions import ToolError

    monkeypatch.setattr(mcp_server, "get_access_token", lambda: _token(subject=None))

    with pytest.raises(ToolError, match="无法识别 Agent Token 所属用户"):
        mcp_server._principal("photos:read")


def test_principal_rejects_a_token_without_the_required_scope(monkeypatch):
    from app.service import mcp_server
    from mcp.server.mcpserver.exceptions import ToolError

    subject = str(uuid.uuid4())
    monkeypatch.setattr(mcp_server, "get_access_token", lambda: _token(subject=subject, scopes=["albums:read"]))

    with pytest.raises(ToolError, match="Agent Token 缺少权限: photos:read"):
        mcp_server._principal("photos:read")


def test_principal_rejects_a_subject_that_is_not_a_uuid(monkeypatch):
    from app.service import mcp_server
    from mcp.server.mcpserver.exceptions import ToolError

    monkeypatch.setattr(
        mcp_server, "get_access_token", lambda: _token(subject="not-a-uuid", scopes=["photos:read"])
    )

    with pytest.raises(ToolError, match="Agent Token 用户标识无效"):
        mcp_server._principal("photos:read")


def test_principal_returns_the_owner_uuid(monkeypatch):
    from app.service import mcp_server

    subject = str(uuid.uuid4())
    monkeypatch.setattr(
        mcp_server, "get_access_token", lambda: _token(subject=subject, scopes=["photos:read"])
    )

    assert mcp_server._principal("photos:read") == uuid.UUID(subject)


# ---------------------------------------------------------------------------
# _parse_date
# ---------------------------------------------------------------------------


def test_parse_date_returns_none_for_an_empty_value():
    from app.service import mcp_server

    assert mcp_server._parse_date(None, "开始日期") is None
    assert mcp_server._parse_date("", "开始日期") is None


def test_parse_date_parses_an_iso_day():
    from datetime import datetime

    from app.service import mcp_server

    assert mcp_server._parse_date("2026-10-26", "开始日期") == datetime(2026, 10, 26)


def test_parse_date_rejects_a_malformed_value():
    from app.service import mcp_server
    from mcp.server.mcpserver.exceptions import ToolError

    with pytest.raises(ToolError, match="开始日期格式必须为 YYYY-MM-DD"):
        mcp_server._parse_date("26.10.2026", "开始日期")


# ---------------------------------------------------------------------------
# search_photos argument guards
# ---------------------------------------------------------------------------


def test_search_photos_rejects_an_inverted_date_range(monkeypatch):
    from app.service import mcp_server
    from mcp.server.mcpserver.exceptions import ToolError

    monkeypatch.setattr(mcp_server, "_principal", lambda _scope: uuid.uuid4())

    with pytest.raises(ToolError, match="开始日期不能晚于结束日期"):
        mcp_server.search_photos(start_date="2026-10-26", end_date="2026-10-01")


def test_search_photos_rejects_an_unknown_orientation(monkeypatch):
    from app.service import mcp_server
    from mcp.server.mcpserver.exceptions import ToolError

    monkeypatch.setattr(mcp_server, "_principal", lambda _scope: uuid.uuid4())

    with pytest.raises(ToolError, match="orientation 只能是 landscape、portrait 或 square"):
        mcp_server.search_photos(orientation="diagonal")
