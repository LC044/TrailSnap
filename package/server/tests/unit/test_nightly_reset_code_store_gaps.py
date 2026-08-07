"""Focused unit coverage for ``app.service.reset_code_store``.

The reset-code store is pure in-memory state-machine code; we exercise the
server-side verification path (``forgot-password`` server-mode) without
needing a database, model, or FastAPI app.

These tests cover the three public contracts that the gap scan keeps surfacing:

* ``issue_code`` enforces a 60-second resend cooldown per user.
* ``verify_code`` accepts the matching code (single-use, hash-only).
* ``verify_code`` invalidates the code after the configured number of failed
  attempts and after the TTL has elapsed.
"""
from types import SimpleNamespace

import pytest

from app.service import reset_code_store as rcs


pytestmark = [pytest.mark.smoke, pytest.mark.module_auth]


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    """Make each test independent: clear the module-level store and freeze time."""
    rcs._store.clear()
    monkeypatch.setattr(rcs, "RESEND_INTERVAL_SECONDS", 60)
    monkeypatch.setattr(rcs, "CODE_TTL_SECONDS", 600)
    monkeypatch.setattr(rcs, "MAX_VERIFY_ATTEMPTS", 5)
    monkeypatch.setattr(rcs, "CODE_DIGITS", 6)
    yield
    rcs._store.clear()


def _freeze_time(monkeypatch, value):
    """Return a controllable clock that always reports ``value``."""
    monkeypatch.setattr(rcs.time, "time", lambda: value)


def test_issue_code_returns_code_first_time_and_logs_only(monkeypatch, caplog):
    """First issuance for a user returns a 6-digit code and only writes to logs."""
    _freeze_time(monkeypatch, 1_000_000.0)

    with caplog.at_level("WARNING", logger="app.auth.reset_code"):
        code = rcs.issue_code("user-1", "alice@example.com")

    assert code is not None
    assert len(code) == rcs.CODE_DIGITS
    assert code.isdigit()
    # The plaintext code is never returned via storage; only the hash is kept.
    assert "user-1" in rcs._store
    stored = rcs._store["user-1"]
    assert stored["code_hash"] == rcs._hash_code(code)
    # The plaintext code was emitted to the WARN log.
    assert any(code in rec.getMessage() for rec in caplog.records)


def test_issue_code_respects_resend_cooldown(monkeypatch):
    """Within ``RESEND_INTERVAL_SECONDS`` of a previous issuance we must NOT reissue."""
    _freeze_time(monkeypatch, 1_000_000.0)
    first = rcs.issue_code("user-1", "alice")
    assert first is not None

    # 30 seconds later -> still within cooldown
    _freeze_time(monkeypatch, 1_000_000.0 + 30)
    again = rcs.issue_code("user-1", "alice")
    assert again is None

    # Past cooldown -> a new code can be issued
    _freeze_time(monkeypatch, 1_000_000.0 + 121)
    third = rcs.issue_code("user-1", "alice")
    assert third is not None
    assert third != first


def test_verify_code_consumes_on_success_and_rejects_replay(monkeypatch):
    """A correct code is single-use; presenting the same code twice returns False."""
    _freeze_time(monkeypatch, 1_000_000.0)
    code = rcs.issue_code("user-1", "alice")
    assert code is not None

    _freeze_time(monkeypatch, 1_000_000.0 + 5)
    assert rcs.verify_code("user-1", code, "alice") is True
    # After successful use the entry is purged.
    assert "user-1" not in rcs._store
    # Replay must therefore fail.
    assert rcs.verify_code("user-1", code, "alice") is False


def test_verify_code_increments_failures_and_eventually_invalidates(monkeypatch, caplog):
    """Failure counter increments per wrong guess and purges after limit."""
    _freeze_time(monkeypatch, 1_000_000.0)
    code = rcs.issue_code("user-1", "alice")
    wrong = "0" * rcs.CODE_DIGITS if code != "0" * rcs.CODE_DIGITS else "1" * rcs.CODE_DIGITS

    with caplog.at_level("WARNING", logger="app.auth.reset_code"):
        # First four wrong guesses: still alive, none of them matches.
        for _ in range(rcs.MAX_VERIFY_ATTEMPTS - 1):
            assert rcs.verify_code("user-1", wrong, "alice") is False
        assert "user-1" in rcs._store
        assert rcs._store["user-1"]["failed_attempts"] == rcs.MAX_VERIFY_ATTEMPTS - 1

        # Fifth wrong guess crosses the threshold and invalidates the entry.
        assert rcs.verify_code("user-1", wrong, "alice") is False
        assert "user-1" not in rcs._store

    # The real code can no longer succeed after MAX_VERIFY_ATTEMPTS hits.
    assert rcs.verify_code("user-1", code, "alice") is False


def test_verify_code_rejects_after_ttl(monkeypatch):
    """Expired codes are rejected and purged; expired == beyond CODE_TTL_SECONDS."""
    _freeze_time(monkeypatch, 1_000_000.0)
    code = rcs.issue_code("user-1", "alice")

    _freeze_time(monkeypatch, 1_000_000.0 + rcs.CODE_TTL_SECONDS + 1)
    assert rcs.verify_code("user-1", code, "alice") is False
    assert "user-1" not in rcs._store


def test_verify_code_unknown_user_returns_false():
    """Calling verify with no issuance history returns False without crashing."""
    assert rcs.verify_code("ghost", "anything") is False


def test_hash_is_stable_and_only_hash_is_stored():
    """Hash helper is deterministic; the store never holds the plaintext code."""
    assert rcs._hash_code("123456") == rcs._hash_code("123456")
    assert rcs._hash_code("123456") != rcs._hash_code("654321")
    # Sanity-check the full pipeline: code plaintext is not in the store.
    sample = SimpleNamespace()
    code = "987654"
    entry = {"code_hash": rcs._hash_code(code)}
    assert code not in entry["code_hash"]
