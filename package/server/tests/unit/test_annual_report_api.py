"""Unit tests for the Annual Report REST endpoints (app/api/annual_report.py).

Fills the nightly coverage gap on transport-analysis / expenses / comprehensive
endpoints. The handlers delegate to ``crud_annual_report`` for photo metrics and
build their own ticket aggregations from the ``TrainTicket`` model.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.api import annual_report as report_api
from app.schemas.annual_report import (
    ComprehensiveMetrics,
    ExpenseMetrics,
    TravelBehaviorMetrics,
    TripTypeDistribution,
)


pytestmark = [pytest.mark.smoke]


def _user():
    return SimpleNamespace(id=str(uuid4()))


def _ticket(date_time, train_code="G100", dep="Alpha", arr="Bravo", mileage=0, price=0):
    return SimpleNamespace(
        id=uuid4(),
        train_code=train_code,
        departure_station=dep,
        arrival_station=arr,
        date_time=date_time,
        price=price,
        seat_type="erzuo",
        name="tester",
        total_mileage=mileage,
    )


@pytest.fixture
def range_args():
    return {
        "start_time": datetime(2026, 1, 1),
        "end_time": datetime(2026, 12, 31, 23, 59, 59),
    }


# ---------------- /annual-report/expenses ----------------


def test_get_report_expenses_delegates_to_crud(range_args):
    db = MagicMock()
    user = _user()
    fake = ExpenseMetrics(
        totalAmount=1234.5, totalCount=5, averagePrice=246.9, monthlyTrend=[],
        maxExpenseAmount=0,
    )

    with patch.object(
        report_api.crud_annual_report, "get_report_expenses", return_value=fake
    ) as get_expenses:
        result = report_api.get_report_expenses(
            start_time=range_args["start_time"],
            end_time=range_args["end_time"],
            db=db,
            current_user=user,
        )

    get_expenses.assert_called_once_with(
        range_args["start_time"], range_args["end_time"], db, user_id=user.id,
    )
    assert result is fake


# ---------------- /annual-report/expenses/details ----------------


def test_get_report_expense_details_returns_ticket_dicts(range_args):
    db = MagicMock()
    user = _user()
    start, end = range_args["start_time"], range_args["end_time"]
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        _ticket(datetime(2026, 3, 14, 10, 0), price=99.5),
    ]

    with patch.object(report_api, "logger"):
        details = report_api.get_report_expense_details(
            start_time=start, end_time=end, db=db, current_user=user
        )

    assert len(details) == 1
    only = details[0]
    assert only.train_code == "G100"
    assert float(only.price) == 99.5
    assert only.date_time == datetime(2026, 3, 14, 10, 0)


def test_get_report_expense_details_wraps_underlying_errors(range_args):
    db = MagicMock()
    user = _user()
    start, end = range_args["start_time"], range_args["end_time"]
    db.query.side_effect = RuntimeError("boom")

    from fastapi import HTTPException

    with patch.object(report_api, "logger"):
        with pytest.raises(HTTPException) as exc:
            report_api.get_report_expense_details(
                start_time=start, end_time=end, db=db, current_user=user
            )
        assert exc.value.status_code == 500


# ---------------- /annual-report/comprehensive ----------------


def test_get_report_comprehensive_sums_mileage_and_cost(range_args):
    db = MagicMock()
    user = _user()
    start, end = range_args["start_time"], range_args["end_time"]

    sum_chain = MagicMock()
    sum_chain.scalar.side_effect = [500, 250.0]
    db.query.return_value.filter.return_value.with_entities.return_value = sum_chain

    metrics = report_api.get_report_comprehensive(
        start_time=start, end_time=end, db=db, current_user=user
    )

    assert isinstance(metrics, ComprehensiveMetrics)
    assert metrics.totalMileage == 500
    assert metrics.costPerKm == 0.5


def test_get_report_comprehensive_zero_mileage_avoids_division_error(range_args):
    db = MagicMock()
    user = _user()
    start, end = range_args["start_time"], range_args["end_time"]

    sum_chain = MagicMock()
    sum_chain.scalar.side_effect = [None, None]
    db.query.return_value.filter.return_value.with_entities.return_value = sum_chain

    metrics = report_api.get_report_comprehensive(
        start_time=start, end_time=end, db=db, current_user=user
    )

    assert metrics.totalMileage == 0
    assert metrics.costPerKm == 0.0


# ---------------- /annual-report/transport-analysis ----------------


def test_get_report_transport_analysis_composes_behavior_and_comprehensive(range_args):
    db = MagicMock()
    user = _user()
    start, end = range_args["start_time"], range_args["end_time"]

    fake_behavior = TravelBehaviorMetrics(
        monthlyFrequency=[], topRoutes=[], topDestinations=[],
        tripTypeDistribution=TripTypeDistribution(workday=0, weekend=0, holiday=0),
    )
    fake_comprehensive = ComprehensiveMetrics(totalMileage=321, costPerKm=0.42)

    with patch.object(report_api, "get_report_travel_behavior", return_value=fake_behavior) as behavior_call, \
         patch.object(report_api, "get_report_comprehensive", return_value=fake_comprehensive) as comprehensive_call:
        result = report_api.get_report_transport_analysis(
            start_time=start, end_time=end, db=db, current_user=user
        )

    behavior_call.assert_called_once_with(start, end, db, user)
    comprehensive_call.assert_called_once_with(start, end, db, user)
    assert result.behavior is fake_behavior
    assert result.comprehensive is fake_comprehensive


def test_get_report_travel_behavior_aggregates_weekday_vs_weekend(range_args):
    db = MagicMock()
    user = _user()
    start, end = range_args["start_time"], range_args["end_time"]
    db.query.return_value.filter.return_value.all.return_value = [
        _ticket(datetime(2026, 3, 14, 8, 0)),   # Saturday
        _ticket(datetime(2026, 3, 15, 9, 0)),   # Sunday
        _ticket(datetime(2026, 3, 17, 10, 0)),  # Wednesday
    ]

    with patch.object(report_api, "logger"):
        result = report_api.get_report_travel_behavior(
            start_time=start, end_time=end, db=db, current_user=user
        )

    assert isinstance(result, TravelBehaviorMetrics)
    assert result.tripTypeDistribution.workday == 1
    assert result.tripTypeDistribution.weekend == 2
    assert result.tripTypeDistribution.holiday == 0
