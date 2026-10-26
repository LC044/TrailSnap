"""Nightly coverage for the remaining branches of ``app/api/user.py`` (2026-10-26).

The 2026-10-26 backend coverage scan listed ``api/user.py`` at 86.4% with 8
missed lines.  All of them sat in the *user administration* endpoints:

* ``create_new_user`` never reached the duplicate-username guard nor the
  successful ``create(...)`` call
* ``update_user_password`` never reached the 404 branch for an unknown user id
* ``delete_user`` never reached the 403 branch for a non-superuser deleting
  somebody else

These tests call the endpoint functions directly (they are plain functions,
not coroutines) with a mocked session, and assert on the HTTP semantics.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.smoke]


def _superuser():
    return SimpleNamespace(id=uuid.uuid4(), is_superuser=True, username="root", email="root@example.com")


def _plain_user():
    return SimpleNamespace(id=uuid.uuid4(), is_superuser=False, username="bob", email="bob@example.com")


def _user_create(email="new@example.com", username="newbie"):
    from app.schemas.user import UserCreate

    return UserCreate(email=email, username=username, password="Passw0rd!123")


def _query_returning(*results):
    """A MagicMock session whose ``query(...).filter(...).first()`` walks results."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = list(results)
    return db


# ---------------------------------------------------------------------------
# create_new_user
# ---------------------------------------------------------------------------


def test_create_user_rejects_a_duplicate_username():
    from app.api.user import create_new_user
    from fastapi import HTTPException

    db = _query_returning(None, SimpleNamespace(id=uuid.uuid4()))
    payload = _user_create(email="free@example.com", username="taken")

    with pytest.raises(HTTPException) as exc_info:
        create_new_user(user_in=payload, db=db, current_user=_superuser())

    assert exc_info.value.status_code == 400
    assert "username already exists" in str(exc_info.value.detail)


def test_create_user_succeeds_when_both_names_are_free():
    from app.api.user import create_new_user

    db = _query_returning(None, None)
    payload = _user_create()

    created = create_new_user(user_in=payload, db=db, current_user=_superuser())

    assert created is not None
    db.add.assert_called_once()


def test_create_user_requires_superuser():
    from app.api.user import create_new_user
    from fastapi import HTTPException

    db = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        create_new_user(user_in=_user_create(), db=db, current_user=_plain_user())

    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# update_user_password
# ---------------------------------------------------------------------------


def test_update_password_reports_an_unknown_user():
    from app.api.user import update_user_password
    from fastapi import HTTPException

    db = _query_returning(None)

    with pytest.raises(HTTPException) as exc_info:
        update_user_password(
            user_id=uuid.uuid4(),
            payload={"password": "Passw0rd!123"},
            db=db,
            current_user=_superuser(),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "User not found"


def test_update_password_rejects_a_short_password():
    from app.api.user import update_user_password
    from fastapi import HTTPException

    db = _query_returning(SimpleNamespace(id=uuid.uuid4()))

    with pytest.raises(HTTPException) as exc_info:
        update_user_password(
            user_id=uuid.uuid4(),
            payload={"password": "123"},
            db=db,
            current_user=_superuser(),
        )

    assert exc_info.value.status_code == 400
    assert "at least 6 characters" in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# delete_user
# ---------------------------------------------------------------------------


def test_delete_user_rejects_deleting_somebody_else():
    from app.api.user import delete_user
    from fastapi import HTTPException

    db = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        delete_user(user_id=uuid.uuid4(), db=db, current_user=_plain_user())

    assert exc_info.value.status_code == 403
    assert "enough privileges" in str(exc_info.value.detail)


def test_delete_user_allows_deleting_yourself():
    from app.api.user import delete_user

    db = MagicMock()
    current = _plain_user()

    with patch("app.api.user.delete", return_value="deleted") as delete:
        result = delete_user(user_id=current.id, db=db, current_user=current)

    delete.assert_called_once_with(db, current.id)
    assert result == "deleted"


# ---------------------------------------------------------------------------
# read_users
# ---------------------------------------------------------------------------


def test_read_users_returns_only_the_current_user_for_non_superusers():
    from app.api.user import read_users

    db = MagicMock()
    current = _plain_user()

    assert read_users(db=db, skip=0, limit=100, current_user=current) == [current]
    db.query.assert_not_called()


def test_read_users_lists_every_user_for_superusers():
    from app.api.user import read_users

    db = MagicMock()
    current = _superuser()
    other = SimpleNamespace(id=uuid.uuid4(), is_superuser=False)

    db.query.return_value.offset.return_value.limit.return_value.all.return_value = [current, other]

    assert read_users(db=db, skip=0, limit=100, current_user=current) == [current, other]
