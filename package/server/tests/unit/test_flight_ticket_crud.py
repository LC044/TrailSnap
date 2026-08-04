"""Unit tests for ``app/crud/flight_ticket.py``.

The CRUD layer is mocked at the SQLAlchemy session level so we never touch
Postgres. The behaviour we lock down:

* ``get_flight_ticket`` queries by id and returns the first match (or None)
* ``get_flight_tickets`` builds the right ``ilike`` / equality / range filters
  based on the value types, applies pagination, and returns ``(total, items)``
* ``create_flight_ticket`` short-circuits to ``None`` on duplicate
  (same flight_code + date_time + name) and otherwise persists with defaults
* ``update_flight_ticket`` mutates only the fields present in the dump
  (exclude_unset=True semantics) and returns None when the id is unknown
* ``delete_flight_ticket`` returns False when missing, True when removed
* ``delete_flight_ticket_by_photo_id`` issues a bulk DELETE filtered by
  photo_id and always commits (even with zero matches)
"""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.sql import operators

from app.crud import flight_ticket as crud_ft
from app.schemas.flight_ticket import FlightTicketCreate, FlightTicketUpdate


pytestmark = [pytest.mark.smoke, pytest.mark.module_ticket]


def _collect_filter_args(db):
    """Walk the chained .filter() calls on db.query() and gather each predicate
    object that was passed in. We use ``.operator`` (a SQLAlchemy public API
    attribute on BinaryExpression) to identify the predicate kind."""
    args = []
    cursor = db.query.return_value
    for _ in range(5):
        f = getattr(cursor, "filter", None)
        if f is None or not f.called:
            break
        for call in f.call_args_list:
            args.append(call.args[0])
        cursor = f.return_value
    return args


# ---------------------------------------------------------------------------
# get_flight_ticket
# ---------------------------------------------------------------------------

def test_get_flight_ticket_returns_first_match():
    db = MagicMock()
    expected = SimpleNamespace(id="t-1", flight_code="CA1234")
    db.query.return_value.filter.return_value.first.return_value = expected

    out = crud_ft.get_flight_ticket(db, "t-1")

    db.query.assert_called_once()
    assert out is expected


def test_get_flight_ticket_returns_none_when_missing():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    assert crud_ft.get_flight_ticket(db, "missing") is None


# ---------------------------------------------------------------------------
# get_flight_tickets
# ---------------------------------------------------------------------------

def test_get_flight_tickets_with_no_filters_returns_total_and_items():
    db = MagicMock()
    expected = [SimpleNamespace(id="a"), SimpleNamespace(id="b")]
    db.query.return_value.count.return_value = 2
    db.query.return_value.order_by.return_value.offset.return_value \
        .limit.return_value.all.return_value = expected

    total, items = crud_ft.get_flight_tickets(db, skip=10, limit=50)

    assert total == 2
    assert items == expected
    db.query.return_value.order_by.return_value.offset.assert_called_once_with(10)
    db.query.return_value.order_by.return_value.offset.return_value \
        .limit.assert_called_once_with(50)


def test_get_flight_tickets_applies_ilike_for_string_filters():
    db = MagicMock()
    db.query.return_value.count.return_value = 0
    db.query.return_value.order_by.return_value.offset.return_value \
        .limit.return_value.all.return_value = []

    crud_ft.get_flight_tickets(db, filters={"flight_code": "CA"})

    predicates = _collect_filter_args(db)
    # One predicate with the ilike operator wrapping the wildcard.
    assert any(getattr(p, "operator", None) is operators.ilike_op for p in predicates)
    # The right-hand value carries the wildcard.
    ilike_preds = [p for p in predicates if getattr(p, "operator", None) is operators.ilike_op]
    assert any(str(p.right.value) == "%CA%" for p in ilike_preds)


def test_get_flight_tickets_applies_equality_for_decimal_datetime_uuid():
    db = MagicMock()
    db.query.return_value.count.return_value = 1
    db.query.return_value.order_by.return_value.offset.return_value \
        .limit.return_value.all.return_value = [SimpleNamespace()]
    moment = datetime(2026, 1, 2, 3, 4, 5)
    owner = uuid4()

    crud_ft.get_flight_tickets(
        db,
        filters={"price": Decimal("999.50"), "date_time": moment, "owner_id": owner},
    )

    predicates = _collect_filter_args(db)
    eq_preds = [p for p in predicates if getattr(p, "operator", None) is operators.eq]
    assert len(eq_preds) >= 3
    rhs_values = {p.right.value for p in eq_preds}
    assert Decimal("999.50") in rhs_values
    assert moment in rhs_values
    assert owner in rhs_values


def test_get_flight_tickets_applies_date_range_filters():
    db = MagicMock()
    db.query.return_value.count.return_value = 0
    db.query.return_value.order_by.return_value.offset.return_value \
        .limit.return_value.all.return_value = []

    crud_ft.get_flight_tickets(
        db, filters={"start_date": "2026-01-01", "end_date": "2026-01-31"}
    )

    predicates = _collect_filter_args(db)
    # Two range predicates (>= and <=) and no ilike.
    ge_preds = [p for p in predicates if getattr(p, "operator", None) is operators.ge]
    le_preds = [p for p in predicates if getattr(p, "operator", None) is operators.le]
    assert len(ge_preds) >= 1
    assert len(le_preds) >= 1
    assert not any(
        getattr(p, "operator", None) is operators.ilike_op for p in predicates
    )


# ---------------------------------------------------------------------------
# create_flight_ticket
# ---------------------------------------------------------------------------

def test_create_flight_ticket_returns_none_when_duplicate_detected():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(id="dup")

    payload = FlightTicketCreate(
        flight_code="CA1234",
        departure_city="武汉",
        arrival_city="北京",
        date_time=datetime(2026, 5, 1, 10, 0),
        price=Decimal("800"),
        name="张三",
    )

    out = crud_ft.create_flight_ticket(db, payload)

    assert out is None
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_create_flight_ticket_persists_with_defaults():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    payload = FlightTicketCreate(
        flight_code="CA1234",
        departure_city="武汉",
        arrival_city="北京",
        date_time=datetime(2026, 5, 1, 10, 0),
        price=Decimal("800"),
        name="张三",
        total_mileage=None,
        total_running_time=None,
        comments="window seat",
        photo_id=None,
    )
    owner_id = uuid4()

    out = crud_ft.create_flight_ticket(db, payload, owner_id=owner_id)

    db.add.assert_called_once()
    db.commit.assert_called_once()
    db.refresh.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.flight_code == "CA1234"
    assert added.total_mileage == Decimal("0.0")
    assert added.total_running_time == 0
    assert added.owner_id == owner_id
    assert out is added


# ---------------------------------------------------------------------------
# update_flight_ticket
# ---------------------------------------------------------------------------

def test_update_flight_ticket_returns_none_when_not_found():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    out = crud_ft.update_flight_ticket(
        db, "missing", FlightTicketUpdate(comments="x")
    )

    assert out is None
    db.commit.assert_not_called()


def test_update_flight_ticket_mutates_only_supplied_fields():
    db = MagicMock()
    target = SimpleNamespace(
        flight_code="CA1234",
        price=Decimal("800"),
        comments="old",
        photo_id=None,
    )
    db.query.return_value.filter.return_value.first.return_value = target

    out = crud_ft.update_flight_ticket(
        db, "id-1", FlightTicketUpdate(comments="window seat")
    )

    assert target.comments == "window seat"
    # Other fields were not in the dump → untouched.
    assert target.flight_code == "CA1234"
    assert target.price == Decimal("800")
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(target)
    assert out is target


# ---------------------------------------------------------------------------
# delete_flight_ticket
# ---------------------------------------------------------------------------

def test_delete_flight_ticket_returns_false_when_missing():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    assert crud_ft.delete_flight_ticket(db, "missing") is False
    db.delete.assert_not_called()
    db.commit.assert_not_called()


def test_delete_flight_ticket_returns_true_when_removed():
    db = MagicMock()
    target = SimpleNamespace(id="t-1")
    db.query.return_value.filter.return_value.first.return_value = target

    assert crud_ft.delete_flight_ticket(db, "t-1") is True
    db.delete.assert_called_once_with(target)
    db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# delete_flight_ticket_by_photo_id
# ---------------------------------------------------------------------------

def test_delete_flight_ticket_by_photo_id_always_commits():
    db = MagicMock()
    db.query.return_value.filter.return_value.delete.return_value = 0

    assert crud_ft.delete_flight_ticket_by_photo_id(db, "photo-1") is True
    db.query.return_value.filter.return_value.delete.assert_called_once()
    db.commit.assert_called_once()