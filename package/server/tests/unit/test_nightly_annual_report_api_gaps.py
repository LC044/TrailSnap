"""Nightly gap-fill tests for app.api.annual_report endpoints that delegate to
``crud_annual_report`` plus the /memory fallback branches.

Targets (priority by §4.1 nightly coverage scan 2026-08-09):

* ``GET /annual-report/photos``     — delegates to ``crud_annual_report.get_annual_report_photos``
* ``GET /annual-report/summary``    — delegates to ``crud_annual_report.get_report_summary``
* ``GET /annual-report/season``     — delegates to ``crud_annual_report.get_report_season``
* ``GET /annual-report/emotion``    — delegates to ``crud_annual_report.get_report_emotion``
* ``GET /annual-report/easter-egg`` — delegates to ``crud_annual_report.get_report_easter_egg``
* ``GET /annual-report/memory``     — covers the fallback branches when the
  user has no top-tags / top-person / top-location / top-feature.

The crud layer is patched so no Postgres is touched. Schemas are exercised
through their public constructors.
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.api import annual_report as report_api
from app.schemas.annual_report import (
    EasterEgg,
    EasterEggTags,
    EmotionMetrics,
    MemoryMetrics,
    SeasonData,
    SeasonMetrics,
    TimeMetrics,
    UserInfo,
)


pytestmark = pytest.mark.smoke


def _user():
    return SimpleNamespace(id=str(uuid4()))


def _range():
    return {
        "start_time": datetime(2026, 1, 1),
        "end_time": datetime(2026, 12, 31, 23, 59, 59),
    }


# ---------------------------------------------------------------------------
# delegation endpoints
# ---------------------------------------------------------------------------


def test_get_annual_report_photos_delegates_to_crud():
    db = MagicMock()
    user = _user()
    fake = {2026: [SimpleNamespace(id=uuid4(), file_path="/p/1.jpg")]}
    with patch.object(report_api.crud_annual_report, "get_annual_report_photos", return_value=fake) as mocked:
        result = report_api.get_annual_report_photos(
            start_time=_range()["start_time"],
            end_time=_range()["end_time"],
            db=db,
            current_user=user,
        )
    assert result is fake
    mocked.assert_called_once()
    kwargs = mocked.call_args.kwargs
    assert kwargs["user_id"] == user.id
    assert mocked.call_args.args[2] is db


def test_get_report_summary_delegates_to_crud():
    db = MagicMock()
    user = _user()
    summary = report_api.ReportSummary(
        user=UserInfo(nickname="tester", avatarUrl="/a.png"),
        time=TimeMetrics(totalPhotos=10, accompanyDays=5),
    )
    with patch.object(report_api.crud_annual_report, "get_report_summary", return_value=summary) as mocked:
        result = report_api.get_report_summary(
            start_time=_range()["start_time"],
            end_time=_range()["end_time"],
            db=db,
            current_user=user,
        )
    assert result is summary
    assert mocked.call_args.kwargs["user_id"] == user.id


def test_get_report_season_delegates_to_crud():
    db = MagicMock()
    user = _user()
    seasons = [
        SeasonData(seasonName="spring", photoCount=1, topTag="x", representativePhoto="/p.png", highlight="h", shootMonth="2026-04"),
        SeasonData(seasonName="summer", photoCount=2, topTag="x", representativePhoto="/p.png", highlight="h", shootMonth="2026-07"),
        SeasonData(seasonName="autumn", photoCount=3, topTag="x", representativePhoto="/p.png", highlight="h", shootMonth="2026-10"),
        SeasonData(seasonName="winter", photoCount=4, topTag="x", representativePhoto="/p.png", highlight="h", shootMonth="2026-12"),
    ]
    season = SeasonMetrics(seasonList=seasons)
    with patch.object(report_api.crud_annual_report, "get_report_season", return_value=season) as mocked:
        result = report_api.get_report_season(
            start_time=_range()["start_time"],
            end_time=_range()["end_time"],
            db=db,
            current_user=user,
        )
    assert result is season
    assert mocked.call_args.kwargs["user_id"] == user.id


def test_get_report_emotion_delegates_to_crud():
    db = MagicMock()
    user = _user()
    emotion = EmotionMetrics(
        livePhotos=0,
        backupPhotos=0,
        totalVideoDuration=0.0,
        cameraPhotos=0,
        emotionCarouselGroups=[],
    )
    with patch.object(report_api.crud_annual_report, "get_report_emotion", return_value=emotion) as mocked:
        result = report_api.get_report_emotion(
            start_time=_range()["start_time"],
            end_time=_range()["end_time"],
            db=db,
            current_user=user,
        )
    assert result is emotion
    assert mocked.call_args.kwargs["user_id"] == user.id


def test_get_report_easter_egg_delegates_to_crud():
    db = MagicMock()
    user = _user()
    egg = EasterEgg(
        bestPhotoUrl="/p.png",
        bestPhotoDate="2026-01-01",
        tags=EasterEggTags(main="x", sub=[]),
    )
    with patch.object(report_api.crud_annual_report, "get_report_easter_egg", return_value=egg) as mocked:
        result = report_api.get_report_easter_egg(
            start_time=_range()["start_time"],
            end_time=_range()["end_time"],
            db=db,
            current_user=user,
        )
    assert result is egg
    assert mocked.call_args.kwargs["user_id"] == user.id


# ---------------------------------------------------------------------------
# /annual-report/memory fallback branches
# ---------------------------------------------------------------------------


def _empty_query_chain():
    """Build a MagicMock chain that supports .filter().first() etc. and returns empty results."""
    chain = MagicMock()
    chain.filter.return_value = chain
    chain.join.return_value = chain
    chain.group_by.return_value = chain
    chain.order_by.return_value = chain
    chain.with_entities.return_value = chain
    chain.count.return_value = 0
    chain.first.return_value = None
    chain.all.return_value = []
    chain.scalar.return_value = 0
    return chain


def test_get_report_memory_falls_back_when_no_tags_no_people_no_location():
    db = MagicMock()
    user = _user()
    db.query.return_value = _empty_query_chain()
    result = report_api.get_report_memory(
        start_time=_range()["start_time"],
        end_time=_range()["end_time"],
        db=db,
        current_user=user,
    )
    assert isinstance(result, MemoryMetrics)
    # No tags → fallback to 生活日常 with total=0
    assert len(result.categoryDistribution) == 1
    assert result.categoryDistribution[0].name == "生活日常"
    assert result.categoryDistribution[0].value == 0
    assert result.topPersonName == ""
    assert result.topPersonCount == 0
    assert result.topLocation == "未知"
    assert result.maxPhotoDayCount == 0
    assert result.topFeature == "未知"
    assert result.topFeatureCount == 0
    assert result.topMake == ""
    assert result.topModel == ""


def test_get_report_memory_excludes_screenshot_and_qr_tags():
    db = MagicMock()
    user = _user()
    call_count = {"n": 0}

    def query_side_effect(*args, **kwargs):
        call_count["n"] += 1
        # First db.query → top_tags chain. Provide excluded tags only.
        if call_count["n"] == 1:
            chain = MagicMock()
            chain.filter.return_value = chain
            chain.join.return_value = chain
            chain.group_by.return_value = chain
            chain.order_by.return_value = chain
            chain.with_entities.return_value = chain
            chain.count.return_value = 1
            chain.scalar.return_value = 0
            chain.first.return_value = None
            chain.all.return_value = [("二维码", 3), ("文档/截图", 2)]
            return chain
        return _empty_query_chain()

    db.query.side_effect = query_side_effect
    result = report_api.get_report_memory(
        start_time=_range()["start_time"],
        end_time=_range()["end_time"],
        db=db,
        current_user=user,
    )
    # Excluded tags dropped → still falls back to synthetic bucket.
    assert len(result.categoryDistribution) == 1
    assert result.categoryDistribution[0].name == "生活日常"


# ---------------------------------------------------------------------------
# haversine_distance helper
# ---------------------------------------------------------------------------


def test_haversine_distance_is_zero_for_same_point():
    assert report_api.haversine_distance(39.9, 116.4, 39.9, 116.4) == pytest.approx(0.0, abs=1e-6)


def test_haversine_distance_matches_known_city_pair():
    # Beijing -> Shanghai ~1067 km
    distance = report_api.haversine_distance(39.9042, 116.4074, 31.2304, 121.4737)
    assert distance == pytest.approx(1067.0, abs=50.0)
