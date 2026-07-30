"""Unit tests for app/service/update_checker.py.

Covers the pure ``compare_versions`` helper, the ``_load_last_notified`` /
``_save_last_notified`` SystemState round-trip, and the async
``fetch_remote_update_info`` happy / failure paths.
"""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


# --------------------------------------------------------------------
# compare_versions (pure)
# --------------------------------------------------------------------

def test_compare_versions_equal_simple():
    from app.service.update_checker import compare_versions
    assert compare_versions("1.2.3", "1.2.3") == 0


def test_compare_versions_newer_major():
    from app.service.update_checker import compare_versions
    assert compare_versions("2.0.0", "1.99.99") == 1


def test_compare_versions_older_patch():
    from app.service.update_checker import compare_versions
    assert compare_versions("1.2.3", "1.2.4") == -1


def test_compare_versions_handles_uneven_lengths():
    """`1.0` should compare equal to `1.0.0`."""
    from app.service.update_checker import compare_versions
    assert compare_versions("1.0", "1.0.0") == 0
    assert compare_versions("1.0.1", "1.0") == 1


@pytest.mark.parametrize("bad", ["", "abc", "1.x.0", None])
def test_compare_versions_invalid_inputs_return_zero(bad):
    from app.service.update_checker import compare_versions
    if bad is None:
        # Treat None as `v1 is None` -> the function short-circuits to 0.
        assert compare_versions(None, "1.0.0") == 0
    else:
        assert compare_versions(bad, "1.0.0") == 0


# --------------------------------------------------------------------
# _load_last_notified / _save_last_notified (DB round-trip)
# --------------------------------------------------------------------

def test_load_last_notified_returns_value_when_row_exists():
    from app.service.update_checker import _load_last_notified
    row = MagicMock()
    row.value = "2.4.1"
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row
    with patch("app.service.update_checker.SessionLocal", MagicMock(return_value=db)):
        assert _load_last_notified() == "2.4.1"
    db.close.assert_called_once()


def test_load_last_notified_returns_none_when_no_row():
    from app.service.update_checker import _load_last_notified
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with patch("app.service.update_checker.SessionLocal", MagicMock(return_value=db)):
        assert _load_last_notified() is None


def test_save_last_notified_updates_existing_row():
    from app.service.update_checker import _save_last_notified
    row = MagicMock()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row
    with patch("app.service.update_checker.SessionLocal", MagicMock(return_value=db)):
        _save_last_notified("3.1.0")
    assert row.value == "3.1.0"
    db.commit.assert_called_once()


def test_save_last_notified_inserts_when_no_row():
    from app.service.update_checker import _save_last_notified, SystemState
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with patch("app.service.update_checker.SessionLocal", MagicMock(return_value=db)):
        _save_last_notified("0.9.0")
    db.add.assert_called_once()
    added = db.add.call_args.args[0]
    assert isinstance(added, SystemState)
    assert added.key.endswith("last_notified_update_version") or "last_notified" in added.key
    assert added.value == "0.9.0"
    db.commit.assert_called_once()


# --------------------------------------------------------------------
# fetch_remote_update_info (async, aiohttp)
# --------------------------------------------------------------------

import asyncio


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_fetch_remote_update_info_happy_path():
    """When the remote payload lists a newer version, has_update is True."""
    from app.service import update_checker

    payload = [
        {"version": "1.0.0", "update_info": "first"},
        {"version": "1.1.0", "update_info": "second"},
    ]
    fake_response = MagicMock()
    fake_response.status = 200
    fake_response.json = _async_return(payload)

    fake_session = MagicMock()
    fake_session.get = _async_return_ctx(fake_response)
    fake_session.__aenter__ = _async_return(fake_session)
    fake_session.__aexit__ = _async_return(None)

    with patch.object(update_checker.aiohttp, "ClientSession", MagicMock(return_value=fake_session)):
        info = _run(update_checker.fetch_remote_update_info(
            url="http://test", current_version="1.0.0"
        ))
    assert info is not None
    assert info["has_update"] is True
    assert info["latest_version"] == "1.1.0"
    assert "1.1.0" in info["update_info"]


def test_fetch_remote_update_info_no_update_when_versions_match():
    from app.service import update_checker

    payload = [{"version": "1.0.0", "update_info": "x"}]
    fake_response = MagicMock()
    fake_response.status = 200
    fake_response.json = _async_return(payload)

    fake_session = MagicMock()
    fake_session.get = _async_return_ctx(fake_response)
    fake_session.__aenter__ = _async_return(fake_session)
    fake_session.__aexit__ = _async_return(None)

    with patch.object(update_checker.aiohttp, "ClientSession", MagicMock(return_value=fake_session)):
        info = _run(update_checker.fetch_remote_update_info(
            url="http://test", current_version="1.0.0"
        ))
    assert info is not None
    assert info["has_update"] is False


def test_fetch_remote_update_info_returns_none_on_non_200():
    from app.service import update_checker

    fake_response = MagicMock()
    fake_response.status = 503
    fake_session = MagicMock()
    fake_session.get = _async_return_ctx(fake_response)
    fake_session.__aenter__ = _async_return(fake_session)
    fake_session.__aexit__ = _async_return(None)

    with patch.object(update_checker.aiohttp, "ClientSession", MagicMock(return_value=fake_session)):
        info = _run(update_checker.fetch_remote_update_info(url="http://test"))
    assert info is None


def test_fetch_remote_update_info_returns_none_on_bad_payload():
    """Empty / non-list payload must short-circuit to None."""
    from app.service import update_checker

    fake_response = MagicMock()
    fake_response.status = 200
    fake_response.json = _async_return({})
    fake_session = MagicMock()
    fake_session.get = _async_return_ctx(fake_response)
    fake_session.__aenter__ = _async_return(fake_session)
    fake_session.__aexit__ = _async_return(None)

    with patch.object(update_checker.aiohttp, "ClientSession", MagicMock(return_value=fake_session)):
        info = _run(update_checker.fetch_remote_update_info(url="http://test"))
    assert info is None


# ---------------- aiohttp async CM helpers (local to this module) ----------------

def _async_return(value):
    async def _coro(*_a, **_k):
        return value
    return _coro


def _async_return_ctx(value):
    """Build a fake `session.get(...)` that returns an async CM wrapping ``value``."""

    class _Ctx:
        def __init__(self, v):
            self._v = v

        async def __aenter__(self):
            return self._v

        async def __aexit__(self, *_a):
            return None

    def _factory(*_a, **_k):
        return _Ctx(value)

    return _factory
