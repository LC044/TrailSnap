"""2026-11-18 nightly coverage for ``app/service/reset_code_store.py``.

No test file referenced ``app/service/reset_code_store.py``.  The module backs
the "reset your password through the server log" fallback, so its guard rails
matter: the code is only ever stored as a hash, it is rate limited, it burns
after one successful use, and it dies after too many failed attempts.
"""

from __future__ import annotations

import pytest

from app.service import reset_code_store


pytestmark = [pytest.mark.smoke, pytest.mark.module_user]


@pytest.fixture(autouse=True)
def _clean_store():
    reset_code_store._store.clear()
    yield
    reset_code_store._store.clear()


def test_an_issued_code_is_six_digits():
    code = reset_code_store.issue_code("user-1", "alice")

    assert code is not None
    assert len(code) == 6
    assert code.isdigit()


def test_only_the_hash_is_stored_never_the_plain_code():
    code = reset_code_store.issue_code("user-1", "alice")

    entry = reset_code_store._store["user-1"]

    assert entry["code_hash"] != code
    assert entry["code_hash"] == reset_code_store._hash_code(code)


def test_a_second_issue_within_the_resend_interval_is_refused():
    assert reset_code_store.issue_code("user-1", "alice") is not None

    assert reset_code_store.issue_code("user-1", "alice") is None


def test_a_code_can_be_verified_once():
    code = reset_code_store.issue_code("user-1", "alice")

    assert reset_code_store.verify_code("user-1", code, "alice") is True


def test_a_used_code_cannot_be_replayed():
    code = reset_code_store.issue_code("user-1", "alice")
    reset_code_store.verify_code("user-1", code, "alice")

    assert reset_code_store.verify_code("user-1", code, "alice") is False


def test_a_wrong_code_is_rejected_and_counts_as_an_attempt():
    code = reset_code_store.issue_code("user-1", "alice")

    assert reset_code_store.verify_code("user-1", "000000" if code != "000000" else "111111", "alice") is False
    assert reset_code_store._store["user-1"]["failed_attempts"] == 1


def test_too_many_failed_attempts_invalidate_the_code():
    code = reset_code_store.issue_code("user-1", "alice")
    wrong = "000000" if code != "000000" else "111111"

    for _ in range(reset_code_store.MAX_VERIFY_ATTEMPTS):
        assert reset_code_store.verify_code("user-1", wrong, "alice") is False

    assert "user-1" not in reset_code_store._store


def test_verifying_without_an_issued_code_is_rejected():
    assert reset_code_store.verify_code("nobody", "123456", "nobody") is False


def test_an_expired_code_is_rejected():
    code = reset_code_store.issue_code("user-1", "alice")
    reset_code_store._store["user-1"]["expires_at"] = 0.0

    assert reset_code_store.verify_code("user-1", code, "alice") is False
    assert "user-1" not in reset_code_store._store


def test_codes_of_different_users_do_not_interfere():
    first = reset_code_store.issue_code("user-1", "alice")
    second = reset_code_store.issue_code("user-2", "bob")

    assert reset_code_store.verify_code("user-2", second, "bob") is True
    assert reset_code_store.verify_code("user-1", first, "alice") is True
