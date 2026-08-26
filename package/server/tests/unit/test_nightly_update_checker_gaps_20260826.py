"""Unit tests for app/service/update_checker.py (2026-08-26 round).

Covers the version compare helper, the aiohttp fetch path, and the
``UpdateCheckScheduler.tick`` body that persists UPDATE notifications.

The module is essentially side-effect free at the function-call level:
  * ``compare_versions`` is pure
  * ``fetch_remote_update_info`` only talks to aiohttp
  * ``tick`` delegates to ``SessionLocal`` / ``crud_notification`` /
    ``crud_user`` / ``NotificationManager`` / ``SystemState``.

We mock the network and DB seams to drive the positive and negative
branches without touching Postgres.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.service import update_checker
from app.service.update_checker import (
    DEFAULT_UPDATE_URL,
    LAST_NOTIFIED_KEY,
    UpdateCheckScheduler,
    compare_versions,
    fetch_remote_update_info,
)


pytestmark = [pytest.mark.smoke]


# -------------------------------------------------------------------------
# compare_versions
# -------------------------------------------------------------------------


def test_compare_versions_returns_zero_for_empty_inputs():
    assert compare_versions("", "") == 0
    assert compare_versions("1.0.0", "") == 0
    assert compare_versions("", "1.0.0") == 0


def test_compare_versions_returns_zero_for_invalid_format():
    assert compare_versions("a.b.c", "1.0.0") == 0
    assert compare_versions("1.0.0", "1.0.0-rc.1") == 0


def test_compare_versions_handles_equal_strings():
    assert compare_versions("1.2.3", "1.2.3") == 0


def test_compare_versions_major_minor_patch():
    assert compare_versions("2.0.0", "1.99.99") == 1
    assert compare_versions("1.99.99", "2.0.0") == -1
    assert compare_versions("1.2.3", "1.2.4") == -1
    assert compare_versions("1.2.4", "1.2.3") == 1


def test_compare_versions_pads_shorter_segment():
    assert compare_versions("1.0", "1.0.0") == 0
    assert compare_versions("1.0.1", "1.0") == 1
    assert compare_versions("1.0", "1.0.1") == -1


# -------------------------------------------------------------------------
# fetch_remote_update_info (async)
# -------------------------------------------------------------------------


def _build_response(status, payload):
    response = AsyncMock()
    response.status = status
    response.__aenter__.return_value = response
    response.__aexit__.return_value = False
    response.json = AsyncMock(return_value=payload)
    return response


def _run(coro):
    return asyncio.run(coro)


def test_fetch_remote_returns_none_on_non_200():
    session = MagicMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = False
    session.get = MagicMock(return_value=_build_response(500, {}))

    with patch.object(update_checker.aiohttp, "ClientSession", return_value=session):
        result = _run(fetch_remote_update_info(url="https://example.com/v.json"))

    assert result is None


def test_fetch_remote_returns_none_on_non_list_payload():
    session = MagicMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = False
    session.get = MagicMock(return_value=_build_response(200, {"version": "1.0"}))

    with patch.object(update_checker.aiohttp, "ClientSession", return_value=session):
        result = _run(fetch_remote_update_info(url="https://example.com/v.json"))

    assert result is None


def test_fetch_remote_returns_none_on_empty_list():
    session = MagicMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = False
    session.get = MagicMock(return_value=_build_response(200, []))

    with patch.object(update_checker.aiohttp, "ClientSession", return_value=session):
        result = _run(fetch_remote_update_info(url="https://example.com/v.json"))

    assert result is None


def test_fetch_remote_returns_no_update_when_remote_not_newer():
    payload = [{"version": "0.9.0", "download_url": "x", "update_info": "old"}]
    session = MagicMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = False
    session.get = MagicMock(return_value=_build_response(200, payload))

    with patch.object(update_checker.aiohttp, "ClientSession", return_value=session):
        result = _run(
            fetch_remote_update_info(url="https://example.com/v.json", current_version="1.0.0")
        )

    assert result is not None
    assert result["latest_version"] == "0.9.0"
    assert result["has_update"] is False
    assert result["update_info"] == ""
    assert result["download_url"] == "x"


def test_fetch_remote_returns_update_payload_with_changelog():
    payload = [
        {"version": "1.0.0", "download_url": "u1", "update_info": "old notes"},
        {"version": "1.1.0", "download_url": "u2", "update_info": "new in 1.1"},
        {"version": "1.2.0", "download_url": "u3", "update_info": "new in 1.2"},
    ]
    session = MagicMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = False
    session.get = MagicMock(return_value=_build_response(200, payload))

    with patch.object(update_checker.aiohttp, "ClientSession", return_value=session):
        result = _run(
            fetch_remote_update_info(url="https://example.com/v.json", current_version="1.0.0")
        )

    assert result is not None
    assert result["latest_version"] == "1.2.0"
    assert result["has_update"] is True
    assert "1.1.0" in result["update_info"]
    assert "1.2.0" in result["update_info"]
    assert result["download_url"] == "u3"


def test_fetch_remote_returns_none_on_exception():
    session = MagicMock()
    session.__aenter__.return_value = session
    session.__aexit__.side_effect = RuntimeError("boom")

    with patch.object(update_checker.aiohttp, "ClientSession", return_value=session):
        result = _run(fetch_remote_update_info(url="https://example.com/v.json"))

    assert result is None


# -------------------------------------------------------------------------
# UpdateCheckScheduler.tick
# -------------------------------------------------------------------------


def test_tick_returns_early_when_fetch_returns_none():
    sched = UpdateCheckScheduler(url="https://example.com/v.json")
    with patch.object(update_checker.asyncio, "run", return_value=None):
        sched.tick()


def test_tick_returns_early_when_fetch_raises():
    sched = UpdateCheckScheduler(url="https://example.com/v.json")
    with patch.object(update_checker.asyncio, "run", side_effect=RuntimeError("net down")):
        sched.tick()


def test_tick_returns_early_when_no_update():
    sched = UpdateCheckScheduler(url="https://example.com/v.json")
    info = {"latest_version": "0.9.0", "has_update": False,
            "update_info": "", "download_url": None}
    with patch.object(update_checker.asyncio, "run", return_value=info), \
         patch.object(update_checker, "SessionLocal") as session_local:
        sched.tick()
    session_local.assert_not_called()


def test_tick_returns_early_when_latest_version_empty():
    sched = UpdateCheckScheduler(url="https://example.com/v.json")
    info = {"latest_version": "", "has_update": True,
            "update_info": "x", "download_url": None}
    with patch.object(update_checker.asyncio, "run", return_value=info), \
         patch.object(update_checker, "SessionLocal") as session_local:
        sched.tick()
    session_local.assert_not_called()


def test_tick_returns_early_when_already_notified_newer_version():
    sched = UpdateCheckScheduler(url="https://example.com/v.json")
    info = {"latest_version": "1.2.0", "has_update": True,
            "update_info": "x", "download_url": "u"}
    db = MagicMock()
    with patch.object(update_checker.asyncio, "run", return_value=info), \
         patch.object(update_checker, "SessionLocal", return_value=db), \
         patch.object(update_checker, "_load_last_notified", return_value="1.5.0"), \
         patch.object(update_checker, "crud_user") as crud_user, \
         patch.object(update_checker, "crud_notification") as crud_n:
        sched.tick()
    crud_user.get_all_users.assert_not_called()
    crud_n.create_notification.assert_not_called()
    db.close.assert_not_called()


def test_tick_notifies_each_user_and_persists_last_notified():
    sched = UpdateCheckScheduler(url="https://example.com/v.json")
    info = {
        "latest_version": "1.2.0",
        "has_update": True,
        "update_info": "stuff",
        "download_url": "https://dl",
    }
    db = MagicMock()
    u1 = SimpleNamespace(id="u1")
    u2 = SimpleNamespace(id="u2")
    notification_obj = SimpleNamespace(id="n1")
    serialized = {"id": "n1", "title": "x"}
    manager = MagicMock()

    with patch.object(update_checker.asyncio, "run", return_value=info), \
         patch.object(update_checker, "SessionLocal", return_value=db), \
         patch.object(update_checker, "_load_last_notified", return_value=None), \
         patch.object(update_checker, "crud_user") as crud_user, \
         patch.object(update_checker, "crud_notification") as crud_n, \
         patch.object(update_checker, "NotificationManager") as nm_cls, \
         patch.object(update_checker, "_save_last_notified") as save_last:
        crud_user.get_all_users.return_value = [u1, u2]
        crud_n.create_notification.return_value = notification_obj
        crud_n._serialize.return_value = serialized
        nm_cls.get_instance.return_value = manager

        sched.tick()

    assert crud_n.create_notification.call_count == 2
    assert manager.publish_to_user.call_count == 2
    save_last.assert_called_once_with("1.2.0")
    db.commit.assert_called()
    db.close.assert_called_once()


def test_tick_returns_early_when_no_users():
    sched = UpdateCheckScheduler(url="https://example.com/v.json")
    info = {
        "latest_version": "1.2.0",
        "has_update": True,
        "update_info": "stuff",
        "download_url": None,
    }
    db = MagicMock()
    with patch.object(update_checker.asyncio, "run", return_value=info), \
         patch.object(update_checker, "SessionLocal", return_value=db), \
         patch.object(update_checker, "_load_last_notified", return_value=None), \
         patch.object(update_checker, "crud_user") as crud_user, \
         patch.object(update_checker, "crud_notification") as crud_n, \
         patch.object(update_checker, "NotificationManager") as nm_cls, \
         patch.object(update_checker, "_save_last_notified") as save_last:
        crud_user.get_all_users.return_value = []
        sched.tick()
    crud_n.create_notification.assert_not_called()
    save_last.assert_not_called()
    db.close.assert_called_once()


def test_tick_swallows_per_user_failure_and_still_persists():
    sched = UpdateCheckScheduler(url="https://example.com/v.json")
    info = {
        "latest_version": "1.2.0",
        "has_update": True,
        "update_info": "x",
        "download_url": None,
    }
    db = MagicMock()
    u1 = SimpleNamespace(id="u1")
    u2 = SimpleNamespace(id="u2")
    n1 = SimpleNamespace(id="n1")
    manager = MagicMock()

    with patch.object(update_checker.asyncio, "run", return_value=info), \
         patch.object(update_checker, "SessionLocal", return_value=db), \
         patch.object(update_checker, "_load_last_notified", return_value=None), \
         patch.object(update_checker, "crud_user") as crud_user, \
         patch.object(update_checker, "crud_notification") as crud_n, \
         patch.object(update_checker, "NotificationManager") as nm_cls, \
         patch.object(update_checker, "_save_last_notified") as save_last:
        crud_user.get_all_users.return_value = [u1, u2]
        crud_n.create_notification.side_effect = [RuntimeError("u1 boom"), n1]
        crud_n._serialize.return_value = {"id": "n1"}
        nm_cls.get_instance.return_value = manager

        sched.tick()

    assert crud_n.create_notification.call_count == 2
    save_last.assert_called_once_with("1.2.0")


# -------------------------------------------------------------------------
# _load_last_notified / _save_last_notified
# -------------------------------------------------------------------------


def test_load_last_notified_returns_value_when_row_present():
    db = MagicMock()
    row = SimpleNamespace(value="1.2.0")
    db.query.return_value.filter.return_value.first.return_value = row
    with patch.object(update_checker, "SessionLocal", return_value=db):
        assert update_checker._load_last_notified() == "1.2.0"
    db.close.assert_called_once()


def test_load_last_notified_returns_none_when_no_row():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with patch.object(update_checker, "SessionLocal", return_value=db):
        assert update_checker._load_last_notified() is None
    db.close.assert_called_once()


def test_load_last_notified_returns_none_on_exception():
    with patch.object(update_checker, "SessionLocal", side_effect=RuntimeError("db down")):
        assert update_checker._load_last_notified() is None


def test_save_last_notified_updates_existing_row():
    db = MagicMock()
    existing = SimpleNamespace(value="1.0.0")
    db.query.return_value.filter.return_value.first.return_value = existing
    with patch.object(update_checker, "SessionLocal", return_value=db):
        update_checker._save_last_notified("1.2.0")
    assert existing.value == "1.2.0"
    db.commit.assert_called_once()
    db.close.assert_called_once()


def test_save_last_notified_inserts_when_no_row():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with patch.object(update_checker, "SessionLocal", return_value=db), \
         patch.object(update_checker, "SystemState") as ss:
        update_checker._save_last_notified("1.2.0")
    ss.assert_called_once_with(key=LAST_NOTIFIED_KEY, value="1.2.0")
    db.add.assert_called_once()
    db.commit.assert_called_once()
    db.close.assert_called_once()


def test_save_last_notified_swallows_exception():
    with patch.object(update_checker, "SessionLocal", side_effect=RuntimeError("db down")):
        update_checker._save_last_notified("1.2.0")
