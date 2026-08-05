"""Unit tests for ``app/crud/moment.py``.

The moment day-caption CRUD is a thin wrapper around the
``MomentDayCaption`` table: list / get / upsert / delete by
``(user_id, scope_type, scope_id, day)``.  We exercise those four
primitives end-to-end through MagicMock so regressions in the filter
chain or upsert branches surface here, leaving the integration layer to
cover the actual SQL.

Coverage:

* ``list_captions`` honours the date range, scope filter, and ordering.
* ``list_captions`` treats ``scope_id=None`` as "global" via ``IS NULL``.
* ``get_caption`` returns ``None`` for misses.
* ``upsert_caption`` creates a fresh row when none exists.
* ``upsert_caption`` updates the existing row in place when one exists.
* ``upsert_caption`` leaves ``model_name`` untouched when caller passes
  ``None`` on an existing row.
* ``delete_caption`` returns ``False`` on miss and ``True`` on hit.
"""

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.crud import moment as crud_moment
from app.db.models.moment_day_caption import MomentDayCaption


pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


def _user_id():
    return uuid.uuid4()


def _chain_query(all_return=None, one_or_none_return=None):
    """Build a chainable mock so the query chain returns expected values
    regardless of the depth of ``.filter(...)`` calls."""
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = all_return if all_return is not None else []
    query.one_or_none.return_value = one_or_none_return
    return query


def _collect_filter_keys(q):
    """Inspect ``q.filter.call_args_list`` and return a list of the LHS
    column keys.  SQLAlchemy ``BinaryExpression.left.key`` gives the
    column name regardless of operator.  ``filter`` may be called with
    multiple positional args (a chained ``AND``), so we iterate all of
    them."""
    keys = []
    for c in q.filter.call_args_list:
        for expr in c.args:
            left = getattr(expr, "left", None)
            if hasattr(left, "key"):
                keys.append(left.key)
    return keys


def _has_is_null_predicate(q, column_key):
    """Return True if any ``.filter`` call used an ``IS NULL`` predicate
    against ``column_key`` (e.g. ``MomentDayCaption.scope_id.is_(None)``).
    Same multi-arg iteration as ``_collect_filter_keys``."""
    for c in q.filter.call_args_list:
        for expr in c.args:
            left = getattr(expr, "left", None)
            op = getattr(expr, "operator", None)
            op_name = getattr(op, "__name__", "") if op is not None else ""
            if (
                hasattr(left, "key")
                and left.key == column_key
                and "is_" in op_name
            ):
                return True
    return False


def test_list_captions_applies_scope_id_filter():
    """Passing a ``scope_id`` adds an equality predicate alongside the
    always-on user / scope_type / day range filters."""
    user = _user_id()
    q = _chain_query(all_return=[SimpleNamespace(id=1), SimpleNamespace(id=2)])
    db = MagicMock()
    db.query.return_value = q

    rows = crud_moment.list_captions(
        db,
        user_id=user,
        scope_type="album",
        scope_id="alb-1",
        start=date(2025, 8, 1),
        end=date(2025, 8, 31),
    )

    assert len(rows) == 2
    keys = _collect_filter_keys(q)
    assert "user_id" in keys
    assert "scope_type" in keys
    assert "scope_id" in keys
    # scope_id is provided -> no IS NULL predicate on scope_id.
    assert _has_is_null_predicate(q, "scope_id") is False
    # The ordering must still apply after the filters.
    q.order_by.assert_called_once()


def test_list_captions_scope_none_uses_is_null():
    """``scope_id=None`` must add an ``IS NULL`` predicate, not an
    equality match; otherwise global-scope rows would never come back."""
    user = _user_id()
    q = _chain_query(all_return=[])
    db = MagicMock()
    db.query.return_value = q

    crud_moment.list_captions(
        db,
        user_id=user,
        scope_type="all",
        scope_id=None,
        start=date(2025, 8, 1),
        end=date(2025, 8, 31),
    )

    keys = _collect_filter_keys(q)
    assert "user_id" in keys
    assert "scope_type" in keys
    assert "scope_id" in keys
    assert _has_is_null_predicate(q, "scope_id") is True
    q.order_by.assert_called_once()


def test_get_caption_returns_none_for_miss():
    """A miss returns ``None`` without raising."""
    user = _user_id()
    q = _chain_query(one_or_none_return=None)
    db = MagicMock()
    db.query.return_value = q

    found = crud_moment.get_caption(
        db,
        user_id=user,
        scope_type="all",
        scope_id=None,
        day=date(2025, 8, 5),
    )
    assert found is None


def test_get_caption_returns_row_for_hit():
    """A hit returns the row from ``one_or_none``."""
    user = _user_id()
    row = SimpleNamespace(id=42, caption="hello")
    q = _chain_query(one_or_none_return=row)
    db = MagicMock()
    db.query.return_value = q

    found = crud_moment.get_caption(
        db,
        user_id=user,
        scope_type="all",
        scope_id=None,
        day=date(2025, 8, 5),
    )
    assert found is row


def test_upsert_caption_creates_when_missing():
    """When ``get_caption`` returns ``None`` we insert a new row with all
    fields populated, then commit + refresh."""
    user = _user_id()
    db = MagicMock()
    db.query.return_value = _chain_query(one_or_none_return=None)

    saved = crud_moment.upsert_caption(
        db,
        user_id=user,
        scope_type="all",
        scope_id=None,
        day=date(2025, 8, 5),
        caption="first take",
        source="ai",
        model_name="gpt-4o",
        photo_count=12,
    )

    db.add.assert_called_once()
    inserted = db.add.call_args[0][0]
    assert isinstance(inserted, MomentDayCaption)
    assert inserted.user_id == user
    assert inserted.caption == "first take"
    assert inserted.source == "ai"
    assert inserted.model_name == "gpt-4o"
    assert inserted.photo_count == 12
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(inserted)
    assert saved is inserted


def test_upsert_caption_updates_existing_row_in_place():
    """When a row already exists we mutate it instead of creating a new
    one.  ``db.add`` is NOT called; commit + refresh fire."""
    user = _user_id()
    existing = MomentDayCaption(
        user_id=user,
        scope_type="all",
        scope_id=None,
        day=date(2025, 8, 5),
        caption="old text",
        source="ai",
        model_name="gpt-4o",
        photo_count=5,
    )
    db = MagicMock()
    db.query.return_value = _chain_query(one_or_none_return=existing)

    saved = crud_moment.upsert_caption(
        db,
        user_id=user,
        scope_type="all",
        scope_id=None,
        day=date(2025, 8, 5),
        caption="new text",
        source="manual",
        model_name="gpt-4o",
        photo_count=8,
    )

    assert saved is existing
    assert existing.caption == "new text"
    assert existing.source == "manual"
    assert existing.photo_count == 8
    db.add.assert_not_called()
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(existing)


def test_upsert_caption_keeps_existing_model_name_when_caller_passes_none():
    """Upsert must not overwrite ``model_name`` with ``None`` on an
    existing row -- callers who re-upsert a manual edit should not erase
    the model provenance."""
    user = _user_id()
    existing = MomentDayCaption(
        user_id=user,
        scope_type="all",
        scope_id=None,
        day=date(2025, 8, 5),
        caption="manual",
        source="manual",
        model_name="gpt-4o",
        photo_count=2,
    )
    db = MagicMock()
    db.query.return_value = _chain_query(one_or_none_return=existing)

    crud_moment.upsert_caption(
        db,
        user_id=user,
        scope_type="all",
        scope_id=None,
        day=date(2025, 8, 5),
        caption="manual again",
        source="manual",
        model_name=None,
        photo_count=3,
    )

    # model_name preserved because the caller passed None.
    assert existing.model_name == "gpt-4o"


def test_delete_caption_returns_false_on_miss():
    """A miss returns ``False`` and we must not call ``db.delete``."""
    db = MagicMock()
    db.query.return_value = _chain_query(one_or_none_return=None)

    out = crud_moment.delete_caption(
        db,
        user_id=_user_id(),
        scope_type="all",
        scope_id=None,
        day=date(2025, 8, 5),
    )
    assert out is False
    db.delete.assert_not_called()
    db.commit.assert_not_called()


def test_delete_caption_returns_true_on_hit():
    """A hit deletes the row, commits, and returns ``True``."""
    user = _user_id()
    existing = MomentDayCaption(
        user_id=user,
        scope_type="all",
        scope_id=None,
        day=date(2025, 8, 5),
        caption="bye",
        source="manual",
        model_name=None,
        photo_count=0,
    )
    db = MagicMock()
    db.query.return_value = _chain_query(one_or_none_return=existing)

    out = crud_moment.delete_caption(
        db,
        user_id=user,
        scope_type="all",
        scope_id=None,
        day=date(2025, 8, 5),
    )
    assert out is True
    db.delete.assert_called_once_with(existing)
    db.commit.assert_called_once()