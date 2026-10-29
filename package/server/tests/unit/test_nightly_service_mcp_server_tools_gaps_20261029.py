"""2026-10-29 nightly gap tests for the MCP tool wrappers in ``app/service/mcp_server.py``.

The tool entry points are called directly with the principal resolution and
the domain helpers patched, so the least-privilege wiring and the error
translation (``ValueError`` -> ``ToolError``) are covered without a live
Agent Token.

Covered gaps:
* ``investigate_memory`` success and ``ValueError`` translation.
* ``get_person_timeline`` success and ``ValueError`` translation.
* ``propose_album_organization`` success payload and ``ValueError`` translation.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from app.service import mcp_server


pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


def _plan(plan_id=None, expires_at=None):
    return SimpleNamespace(
        id=plan_id or uuid4(),
        status="pending",
        expires_at=expires_at,
        preview={"name": "整理相册"},
    )


class _Session:
    """A session context manager that yields a mock DB session."""

    def __init__(self, db=None):
        self.db = db or MagicMock()

    def __enter__(self):
        return self.db

    def __exit__(self, *args):
        return False


# ----------------------- investigate_memory -----------------------


def test_investigate_memory_returns_clues():
    """The tool forwards every filter to the domain helper."""
    user_id = uuid4()
    db = MagicMock()
    payload = {"events": [{"title": "西湖"}]}

    with patch.object(mcp_server, "_principal", return_value=user_id):
        with patch.object(mcp_server, "SessionLocal", return_value=_Session(db)):
            with patch.object(mcp_server, "investigate_memory_clues", return_value=payload) as helper:
                result = mcp_server.investigate_memory("西湖", max_events=3)

    helper.assert_called_once_with(db, str(user_id), "西湖", None, None, None, None, None, None, 3)
    assert result == payload


def test_investigate_memory_translates_value_error():
    """An invalid clue combination becomes a tool error."""
    with patch.object(mcp_server, "_principal", return_value=uuid4()):
        with patch.object(mcp_server, "SessionLocal", return_value=_Session()):
            with patch.object(mcp_server, "investigate_memory_clues", side_effect=ValueError("线索冲突")):
                with pytest.raises(ToolError) as excinfo:
                    mcp_server.investigate_memory("冲突线索")

    assert "线索冲突" in str(excinfo.value)


# ----------------------- get_person_timeline -----------------------


def test_get_person_timeline_returns_timeline():
    """The person timeline tool forwards the identity and the event budget."""
    user_id = uuid4()
    db = MagicMock()
    payload = {"identity_id": "abc", "events": []}

    with patch.object(mcp_server, "_principal", return_value=user_id):
        with patch.object(mcp_server, "SessionLocal", return_value=_Session(db)):
            with patch.object(mcp_server, "build_person_timeline", return_value=payload) as helper:
                result = mcp_server.get_person_timeline("abc", max_events=5)

    helper.assert_called_once_with(db, str(user_id), "abc", None, None, 5)
    assert result == payload


def test_get_person_timeline_translates_value_error():
    """An unknown identity is reported as a tool error."""
    with patch.object(mcp_server, "_principal", return_value=uuid4()):
        with patch.object(mcp_server, "SessionLocal", return_value=_Session()):
            with patch.object(mcp_server, "build_person_timeline", side_effect=ValueError("人物不存在")):
                with pytest.raises(ToolError) as excinfo:
                    mcp_server.get_person_timeline("missing")

    assert "人物不存在" in str(excinfo.value)


# ----------------------- propose_album_organization -----------------------


def test_propose_album_organization_returns_plan_summary():
    """The proposal tool returns the plan id, status and approval link."""
    user_id = uuid4()
    plan = _plan()

    with patch.object(mcp_server, "_principal", return_value=user_id):
        with patch.object(mcp_server, "SessionLocal", return_value=_Session()):
            with patch.object(mcp_server, "propose_album_plan", return_value=plan) as helper:
                result = mcp_server.propose_album_organization("旅行相册", ["p1", "p2"])

    helper.assert_called_once()
    assert result["plan_id"] == str(plan.id)
    assert result["status"] == "pending"
    assert result["expires_at"] is None
    assert result["approval_url"].endswith(str(plan.id))
    assert "尚未执行" in result["notice"]


def test_propose_album_organization_translates_value_error():
    """A rejected proposal (e.g. foreign photos) becomes a tool error."""
    with patch.object(mcp_server, "_principal", return_value=uuid4()):
        with patch.object(mcp_server, "SessionLocal", return_value=_Session()):
            with patch.object(mcp_server, "propose_album_plan", side_effect=ValueError("照片不属于当前用户")):
                with pytest.raises(ToolError) as excinfo:
                    mcp_server.propose_album_organization("非法相册", ["p1"])

    assert "照片不属于当前用户" in str(excinfo.value)


# ----------------------- scope enforcement -----------------------


def test_investigate_memory_requires_photos_read_scope():
    """Without the ``photos:read`` scope the tool refuses to run."""
    with patch.object(mcp_server, "_principal", side_effect=ToolError("Agent Token 缺少权限: photos:read")):
        with pytest.raises(ToolError) as excinfo:
            mcp_server.investigate_memory("任意线索")

    assert "缺少权限" in str(excinfo.value)
