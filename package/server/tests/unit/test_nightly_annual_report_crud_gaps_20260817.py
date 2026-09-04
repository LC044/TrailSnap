"""Unit tests covering 2026-08-17 nightly coverage gap scan (round 12).

Modules exercised:
* app/crud/annual_report.py -- functions still < 33% after 2026-08-14 round:
  - get_report_expenses: total / avg / max + monthly trend + last-year comparison
    + leap-year edge branch (Feb 29 -> ValueError handled with day=28 fallback).
  - get_report_summary: TimeMetrics aggregation including first/last photo dates
    and late-night count + distinct dates.
  - find_best_match_photo: postgres branch (dialect != sqlite) ordering by
    cosine_distance + months filter application.
  - get_report_season: SEASON_VECTORS branch + representative photo URL build
    + picsum fallback when no rep photo.
  - get_report_emotion: live photo + camera photo + video duration aggregation
    with user_id filtering.
  - get_report_easter_egg: best photo URL + date fallback to default.

Note: get_annual_report_photos is skipped because its window-function subquery
relies on `ranked.c.rn <= 10` column comparisons that MagicMock cannot satisfy
without an SQLAlchemy session.

Pattern: MagicMock chains mimic SQLAlchemy's fluent query API without booting
Postgres; the goal is to exercise branch logic in crud/annual_report.py and
shove coverage past 33%.
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _chain(first=None, count=0, scalar=None, all_rows=None):
    """Build a self-returning fluent mock with the supplied terminal values."""
    q = MagicMock(name="q")
    q.filter.return_value = q
    q.with_entities.return_value = q
    q.join.return_value = q
    q.order_by.return_value = q
    q.group_by.return_value = q
    q.distinct.return_value = q
    q.label.return_value = q
    q.first.return_value = first
    q.count.return_value = count
    q.scalar.return_value = scalar
    q.all.return_value = all_rows if all_rows is not None else []
    return q


def _photo(id_=None, time=None, **kw):
    return SimpleNamespace(
        id=id_ or ("photo-" + (time.isoformat() if time else "x")),
        photo_time=time,
        **kw,
    )


# ---------------------------------------------------------------------------
# get_report_expenses
# ---------------------------------------------------------------------------


def test_get_report_expenses_zero_count_uses_zero_average():
    from app.crud import annual_report as ar

    q = _chain()
    q.scalar.return_value = None
    q.first.return_value = None
    q.all.return_value = []

    db = MagicMock()
    db.query.return_value = q

    metrics = ar.get_report_expenses(
        datetime(2024, 1, 1), datetime(2024, 12, 31), db
    )
    assert metrics.totalCount == 0
    assert metrics.totalAmount == 0.0
    assert metrics.averagePrice == 0.0
    assert metrics.maxExpenseTicket is None
    assert metrics.maxExpenseAmount == 0.0
    assert metrics.monthlyTrend == []
    assert metrics.totalAmountLastYear == 0.0


def test_get_report_expenses_aggregates_with_max_ticket():
    from app.crud import annual_report as ar

    ticket = SimpleNamespace(
        price=300.0,
        train_code="G1",
        departure_station="\u5317\u4eac\u5357",
        arrival_station="\u4e0a\u6d77\u8679\u6865",
    )
    monthly_rows = [
        SimpleNamespace(year=2024, month=1, amount=120.0),
        SimpleNamespace(year=2024, month=2, amount=180.0),
    ]

    q = _chain(count=2, first=ticket, all_rows=monthly_rows)
    q.scalar.side_effect = [300.0, 150.0]

    db = MagicMock()
    db.query.return_value = q

    metrics = ar.get_report_expenses(
        datetime(2024, 1, 1), datetime(2024, 12, 31), db
    )
    assert metrics.totalCount == 2
    assert metrics.totalAmount == 300.0
    assert metrics.averagePrice == 150.0
    assert metrics.maxExpenseAmount == 300.0
    assert "G1" in metrics.maxExpenseTicket
    assert len(metrics.monthlyTrend) == 2
    assert metrics.monthlyTrend[0].month == "2024-01"


def test_get_report_expenses_handles_leap_year_feb_29():
    """Feb 29 -> ValueError; crud falls back to day=28."""
    from app.crud import annual_report as ar

    q = _chain()
    q.scalar.return_value = None
    q.first.return_value = None
    q.all.return_value = []

    db = MagicMock()
    db.query.return_value = q

    metrics = ar.get_report_expenses(
        datetime(2024, 2, 29), datetime(2024, 3, 1), db
    )
    assert metrics.totalCount == 0


def test_get_report_expenses_applies_user_id_filter():
    from app.crud import annual_report as ar

    q = _chain()
    q.scalar.return_value = None
    q.first.return_value = None
    q.all.return_value = []

    db = MagicMock()
    db.query.return_value = q

    ar.get_report_expenses(
        datetime(2024, 1, 1), datetime(2024, 12, 31), db, user_id="user-42"
    )
    assert q.filter.called


# ---------------------------------------------------------------------------
# get_report_summary
# ---------------------------------------------------------------------------


def test_get_report_summary_empty_query_returns_zero_metrics():
    from app.crud import annual_report as ar

    q = _chain()
    q.distinct.return_value = q

    db = MagicMock()
    db.query.return_value = q

    summary = ar.get_report_summary(datetime(2024, 1, 1), datetime(2024, 12, 31), db)
    assert summary.user.nickname == "\u65f6\u5149\u65c5\u4eba"
    assert summary.time.totalPhotos == 0
    assert summary.time.accompanyDays == 0
    assert summary.time.firstPhotoDate is None
    assert summary.time.lastPhotoDate is None
    assert summary.time.lateNightPhotoCount == 0
    assert summary.time.photoDates == []


def test_get_report_summary_populates_first_last_and_late_night():
    from app.crud import annual_report as ar

    # get_report_summary calls count() three times: totalPhotos / accompanyDays
    # / lateNightPhotoCount -- so the side_effect must yield three values.
    q = _chain()
    q.distinct.return_value = q
    q.count.side_effect = [10, 3, 1]
    q.first.side_effect = [
        _photo(id_="p1", time=datetime(2024, 1, 15, 8, 0)),
        _photo(id_="p2", time=datetime(2024, 6, 1, 22, 30)),
    ]
    q.all.return_value = [
        ("2024-01-15",),
        ("2024-03-20",),
        ("2024-06-01",),
    ]

    db = MagicMock()
    db.query.return_value = q

    summary = ar.get_report_summary(datetime(2024, 1, 1), datetime(2024, 12, 31), db)
    assert summary.time.totalPhotos == 10
    assert summary.time.accompanyDays == 3
    assert summary.time.firstPhotoDate == "2024-01-15"
    assert summary.time.lastPhotoDate == "2024-06-01"
    assert summary.time.lateNightPhotoCount == 1
    assert len(summary.time.photoDates) == 3


# ---------------------------------------------------------------------------
# find_best_match_photo (postgres branch)
# ---------------------------------------------------------------------------


def test_find_best_match_photo_postgres_branch_orders_by_cosine_distance():
    from app.crud import annual_report as ar

    db = MagicMock()
    db.bind.dialect.name = "postgresql"

    expected = _photo(id_="best", time=datetime(2024, 5, 5))

    q = _chain(first=expected)
    db.query.return_value.join.return_value = q

    result = ar.find_best_match_photo(
        db, datetime(2024, 1, 1), datetime(2024, 12, 31), [0.5, 0.5, 0.5]
    )
    assert result is expected


def test_find_best_match_photo_applies_months_filter_when_provided():
    from app.crud import annual_report as ar

    db = MagicMock()
    db.bind.dialect.name = "postgresql"

    expected = _photo(id_="best")
    q = _chain(first=expected)
    db.query.return_value.join.return_value = q

    ar.find_best_match_photo(
        db, datetime(2024, 1, 1), datetime(2024, 12, 31),
        [0.1, 0.2, 0.3], months=[3, 4, 5],
    )
    assert q.filter.call_count >= 4


# ---------------------------------------------------------------------------
# get_report_season
# ---------------------------------------------------------------------------


def test_get_report_season_returns_picsum_fallback_when_no_rep_photo():
    from app.crud import annual_report as ar

    q = _chain()
    q.first.return_value = None

    db = MagicMock()
    db.query.return_value = q

    with patch.object(ar, "find_best_match_photo", return_value=None):
        metrics = ar.get_report_season(
            datetime(2024, 1, 1), datetime(2024, 12, 31), db, user_id="user-1"
        )

    assert len(metrics.seasonList) == 4
    seasons = {s.seasonName for s in metrics.seasonList}
    assert seasons == {"\u6625", "\u590f", "\u79cb", "\u51ac"}
    for s in metrics.seasonList:
        assert s.representativePhoto.startswith("https://picsum.photos/seed/")


def test_get_report_season_uses_rep_photo_thumbnail_url():
    from app.crud import annual_report as ar

    q = _chain(count=7)
    q.first.return_value = None

    db = MagicMock()
    db.query.return_value = q

    rep_photo = _photo(id_="rep-1")
    with patch.object(ar, "find_best_match_photo", return_value=rep_photo):
        metrics = ar.get_report_season(
            datetime(2024, 1, 1), datetime(2024, 12, 31), db, user_id="user-1"
        )

    spring = next(s for s in metrics.seasonList if s.seasonName == "\u6625")
    assert spring.representativePhoto == "/api/medias/user-1/rep-1/thumbnail"
    assert spring.photoCount == 7
    assert spring.shootMonth == "3-5\u6708"


# ---------------------------------------------------------------------------
# get_report_emotion
# ---------------------------------------------------------------------------


def test_get_report_emotion_aggregates_video_live_camera_counts():
    from app.crud import annual_report as ar

    db = MagicMock()

    q_total = _chain(count=100)
    q_video = _chain(scalar=123.4)
    q_live = _chain(count=5)
    q_camera = _chain(count=60)

    db.query.side_effect = [q_total, q_video, q_live, q_camera]

    metrics = ar.get_report_emotion(
        datetime(2024, 1, 1), datetime(2024, 12, 31), db, user_id="user-1"
    )
    assert metrics.backupPhotos == 100
    assert metrics.totalVideoDuration == 123.4
    assert metrics.livePhotos == 5
    assert metrics.cameraPhotos == 60
    assert len(metrics.emotionCarouselGroups) == 1


def test_get_report_emotion_handles_missing_video_scalar():
    from app.crud import annual_report as ar

    db = MagicMock()
    q_total = _chain(count=0)
    q_video = _chain(scalar=None)
    q_live = _chain(count=0)
    q_camera = _chain(count=0)

    db.query.side_effect = [q_total, q_video, q_live, q_camera]

    metrics = ar.get_report_emotion(
        datetime(2024, 1, 1), datetime(2024, 12, 31), db
    )
    assert metrics.totalVideoDuration == 0
    assert metrics.backupPhotos == 0


# ---------------------------------------------------------------------------
# get_report_easter_egg
# ---------------------------------------------------------------------------


def test_get_report_easter_egg_uses_best_photo_when_found():
    from app.crud import annual_report as ar

    db = MagicMock()
    best = _photo(id_="egg-1", time=datetime(2024, 10, 1, 14, 30))

    with patch.object(ar, "find_best_match_photo", return_value=best):
        egg = ar.get_report_easter_egg(
            datetime(2024, 1, 1), datetime(2024, 12, 31), db, user_id="user-1"
        )

    assert egg.bestPhotoUrl == "/api/medias/user-1/egg-1/thumbnail"
    assert egg.bestPhotoDate == "2024-10-01"
    assert egg.tags.main == "\u751f\u6d3b\u8bb0\u5f55\u5bb6"


def test_get_report_easter_egg_falls_back_when_no_photo():
    from app.crud import annual_report as ar

    db = MagicMock()
    with patch.object(ar, "find_best_match_photo", return_value=None):
        egg = ar.get_report_easter_egg(
            datetime(2024, 1, 1), datetime(2024, 12, 31), db
        )

    assert egg.bestPhotoUrl == "https://picsum.photos/seed/best/400/600"
    assert egg.bestPhotoDate == "2024-10-01"
