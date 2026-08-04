"""Focused unit coverage for API modules found by the nightly gap scan."""

from math import isclose
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.api import annual_report, auth, guess_city, location_stats, storage


pytestmark = pytest.mark.smoke


@pytest.mark.parametrize(
    ("handler", "crud_name", "dates"),
    [
        (location_stats.get_overview, "get_overview", ("2026-01-01", "2026-12-31")),
        (location_stats.get_annual_trend, "get_annual_trend", (None, None)),
        (location_stats.get_monthly_radar, "get_monthly_radar", (None, None)),
        (location_stats.get_heatmap, "get_heatmap_range", (None, None)),
    ],
)
def test_location_stats_delegates_user_and_date_filters(handler, crud_name, dates):
    db = MagicMock()
    user = SimpleNamespace(id="user-1")
    result = {"ok": True}

    with patch.object(location_stats.crud, crud_name, return_value=result) as crud_call:
        actual = handler(
            start_date=dates[0], end_date=dates[1], db=db, current_user=user
        )

    crud_call.assert_called_once_with(db, user.id, *dates)
    assert actual is result


def test_location_places_forwards_all_filters_and_limit():
    db = MagicMock()
    user = SimpleNamespace(id="user-2")

    with patch.object(location_stats.crud, "get_places", return_value={"items": []}) as get_places:
        result = location_stats.get_places(
            level="district", start_date="2026-01-01", end_date="2026-01-31",
            parent_region="湖北省", limit=5, db=db, current_user=user,
        )

    get_places.assert_called_once_with(
        db, user.id, "district", "2026-01-01", "2026-01-31", "湖北省", 5
    )
    assert result == {"items": []}


def test_haversine_distance_is_zero_for_same_point():
    assert annual_report.haversine_distance(30.5, 114.3, 30.5, 114.3) == 0


def test_haversine_distance_matches_known_city_distance():
    distance = annual_report.haversine_distance(31.2304, 121.4737, 39.9042, 116.4074)
    assert isclose(distance, 1067, rel_tol=0.02)


def test_annual_report_photos_forwards_current_user_id():
    db = MagicMock()
    user = SimpleNamespace(id="owner-9")
    start = SimpleNamespace()
    end = SimpleNamespace()

    with patch.object(
        annual_report.crud_annual_report, "get_annual_report_photos", return_value={}
    ) as get_photos:
        result = annual_report.get_annual_report_photos(start, end, db, user)

    get_photos.assert_called_once_with(start, end, db, user_id=user.id)
    assert result == {}


def test_guess_cities_serializes_coordinates_and_missing_values():
    rows = [
        SimpleNamespace(city="武汉市", avg_lat=30.59, avg_lon=114.30),
        SimpleNamespace(city="未知", avg_lat=None, avg_lon=None),
    ]
    db = MagicMock()
    db.query.return_value.filter.return_value.group_by.return_value.all.return_value = rows

    response = guess_city.get_cities(db=db)

    assert response.code == 0
    assert response.data[0] == {"city": "武汉市", "latitude": 30.59, "longitude": 114.3}
    assert response.data[1]["latitude"] == 0.0
    assert response.data[1]["longitude"] == 0.0


def test_guess_city_returns_not_found_when_photo_has_no_metadata():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    request = guess_city.GuessRequest(photo_id="missing", guess_city="武汉市")

    response = guess_city.guess_city(request, db=db)

    assert response.code == 404
    assert response.msg == "Photo or location not found"


def test_storage_folder_stats_aggregates_duplicate_folders_and_empty_path():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [
        ("C:/photos/a.jpg", 10), ("C:/photos/b.jpg", None), (None, 5),
    ]

    response = storage.get_storage_folder_stats(
        db=db, current_user=SimpleNamespace(id="owner-1")
    )

    by_name = {item["name"]: item for item in response.data}
    assert by_name["C:/photos"] == {"name": "C:/photos", "size": 10, "count": 2}
    assert by_name["未知"] == {"name": "未知", "size": 5, "count": 1}


def test_storage_folder_stats_returns_empty_list_without_photos():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []

    response = storage.get_storage_folder_stats(
        db=db, current_user=SimpleNamespace(id="owner-1")
    )

    assert response.code == 0
    assert response.data == []


def test_auth_status_reports_user_presence_and_registration_flag():
    db = MagicMock()
    db.query.return_value.count.return_value = 2

    with patch.object(auth.system_config.config.security, "allow_registration", False):
        result = auth.get_auth_status(db=db)

    assert result["has_users"] is True
    assert result["allow_registration"] is False
    assert isinstance(result["demo_mode"], bool)


def test_auth_status_allows_empty_installation_state():
    db = MagicMock()
    db.query.return_value.count.return_value = 0

    result = auth.get_auth_status(db=db)

    assert result["has_users"] is False
# ---------------------------------------------------------------------------
# Moment router (package/server/app/api/moment.py)
# ---------------------------------------------------------------------------
from datetime import date as _date

import pytest
from fastapi import HTTPException

from app.api import moment as moment_api
from app.schemas.moment import MomentDayCaptionGenerateRequest, MomentDayCaptionUpsert


def test_moment_list_captions_rejects_inverted_date_range():
    db = MagicMock()
    user = SimpleNamespace(id="user-moment-1")

    with pytest.raises(HTTPException) as exc:
        moment_api.list_day_captions(
            start=_date(2025, 8, 6),
            end=_date(2025, 8, 5),
            scope_type="all",
            scope_id=None,
            current_user=user,
            db=db,
        )

    assert exc.value.status_code == 400
    assert "start" in exc.value.detail


def test_moment_list_captions_rejects_range_longer_than_one_year():
    db = MagicMock()
    user = SimpleNamespace(id="user-moment-2")

    with pytest.raises(HTTPException) as exc:
        moment_api.list_day_captions(
            start=_date(2024, 1, 1),
            end=_date(2025, 12, 31),
            scope_type="all",
            scope_id=None,
            current_user=user,
            db=db,
        )

    assert exc.value.status_code == 400
    assert "366" in exc.value.detail or "区间" in exc.value.detail


def test_moment_upsert_caption_strips_and_validates_payload():
    db = MagicMock()
    user = SimpleNamespace(id="user-moment-3")

    payload = MomentDayCaptionUpsert(caption="   ")
    with pytest.raises(HTTPException) as exc:
        moment_api.upsert_day_caption(
            day=_date(2025, 8, 5),
            payload=payload,
            scope_type="all",
            scope_id=None,
            current_user=user,
            db=db,
        )
    assert exc.value.status_code == 400
    assert "不能为空" in exc.value.detail


def test_moment_upsert_caption_delegates_to_crud_with_source_manual():
    db = MagicMock()
    user = SimpleNamespace(id="user-moment-4")
    expected = SimpleNamespace(id=42, caption="hello")
    with patch.object(
        moment_api.moment_crud, "upsert_caption", return_value=expected
    ) as upsert:
        result = moment_api.upsert_day_caption(
            day=_date(2025, 8, 5),
            payload=MomentDayCaptionUpsert(caption="  hello  "),
            scope_type="all",
            scope_id=None,
            current_user=user,
            db=db,
        )
    upsert.assert_called_once_with(
        db,
        user.id,
        "all",
        None,
        _date(2025, 8, 5),
        "hello",
        source="manual",
    )
    assert result is expected


def test_moment_generate_rejects_non_all_scope():
    db = MagicMock()
    user = SimpleNamespace(id="user-moment-5")
    request = MomentDayCaptionGenerateRequest(
        day=_date(2025, 8, 5),
        scope_type="album",
        scope_id="abc",
    )

    # 非 all 场景在 router 内被直接拒绝为 400，未触达下游服务。
    import asyncio
    with pytest.raises(HTTPException) as exc:
        asyncio.run(moment_api.generate_day_caption(request=request, current_user=user, db=db))
    assert exc.value.status_code == 400
    assert "scope_type" in exc.value.detail


def test_moment_generate_wraps_internal_errors_in_500():
    db = MagicMock()
    user = SimpleNamespace(id="user-moment-6")
    # stream=False 走 generate_caption_sync 路径，便于同步断言 500 包装。
    request = MomentDayCaptionGenerateRequest(day=_date(2025, 8, 5), stream=False)

    # 当下游服务（非 ValueError 非 HTTPException）抛异常时，router 应包装为 500。
    import asyncio
    async def _boom(**_kwargs):
        raise RuntimeError("LLM down")

    with patch.object(moment_api, "generate_caption_sync", side_effect=_boom):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(moment_api.generate_day_caption(request=request, current_user=user, db=db))
    assert exc.value.status_code == 500
    assert "LLM" in exc.value.detail


# ---------------------------------------------------------------------------
# Dashboard CRUD (package/server/app/crud/dashboard.py) — 7.2% → 目标 ≥ 60%
# 覆盖 §4.5 优先级 3：crud 业务逻辑。get_dashboard_stats / get_heatmap_stats。
# ---------------------------------------------------------------------------
from collections import namedtuple
from datetime import date as _date
from uuid import uuid4

from app.crud import dashboard as crud_dashboard

_YearRow = namedtuple("_YearRow", ["year", "count"])
_YearAvail = namedtuple("_YearAvail", ["year"])


def _make_query_mock(*, count=0, scalar=0, first=None, all_value=()):
    """生成一个独立的 SQLAlchemy-like query mock：chain 操作均返回 self。"""
    q = MagicMock(name="query")
    q.filter.return_value = q
    q.filter_by.return_value = q
    q.join.return_value = q
    q.group_by.return_value = q
    q.order_by.return_value = q
    q.offset.return_value = q
    q.limit.return_value = q
    q.count.return_value = count
    q.scalar.return_value = scalar
    q.first.return_value = first
    q.all.return_value = list(all_value)
    return q


def _build_dashboard_queries(*, total_media=0, today_new=0, storage_bytes=0,
                             year_rows=(), month_peak=None):
    """按 dashboard.py 调用顺序生成 12 个 query mock。"""
    return [
        _make_query_mock(count=total_media),       # 0 total_media
        _make_query_mock(count=today_new),         # 1 today_new
        _make_query_mock(scalar=storage_bytes),    # 2 storage sum
        _make_query_mock(count=0),                 # 3 total_identified
        _make_query_mock(count=0),                 # 4 pending_faces
        _make_query_mock(scalar=0),                # 5 unidentified_photos
        _make_query_mock(count=0),                 # 6 scenery_count
        _make_query_mock(count=0),                 # 7 food_count
        _make_query_mock(count=0),                 # 8 photos_count
        _make_query_mock(count=0),                 # 9 videos_count
        _make_query_mock(all_value=list(year_rows)),  # 10 year_stats
        _make_query_mock(first=month_peak),        # 11 month_stats
    ]


def test_dashboard_stats_returns_zero_totals_on_empty_library():
    user_id = uuid4()
    queries = _build_dashboard_queries()
    db = MagicMock()
    db.query.side_effect = lambda *a, **kw: queries[db.query.call_count - 1]

    with patch("app.crud.dashboard.get_identities_with_details", return_value=[]):
        result = crud_dashboard.get_dashboard_stats(db, user_id)

    assert result.card.total_media == 0
    assert result.card.today_new == 0
    assert result.card.storage_used == "0.0GB"
    assert result.face.total_identified == 0
    assert result.face.top_faces == []
    assert result.face.pending_faces_count == 0
    assert result.content.photos.total == 0
    assert result.content.videos.total == 0
    assert result.time.chart_data == []
    assert result.time.monthly_peak == "暂无数据"


def test_dashboard_stats_aggregates_year_groups_and_monthly_peak():
    user_id = uuid4()
    # year_stats 需同时支持 .count 属性访问 + (year, count) tuple 解包
    year_rows = [_YearRow(2024, 5), _YearRow(2025, 3)]
    month_peak = MagicMock(year=2025, month=7, count=4)
    queries = _build_dashboard_queries(
        total_media=1, today_new=1, storage_bytes=2 * 1024 ** 3,
        year_rows=year_rows, month_peak=month_peak,
    )
    db = MagicMock()
    db.query.side_effect = lambda *a, **kw: queries[db.query.call_count - 1]

    with patch("app.crud.dashboard.get_identities_with_details", return_value=[]):
        result = crud_dashboard.get_dashboard_stats(db, user_id)

    assert result.card.total_media == 1
    assert result.card.storage_used == "2.0GB"
    assert len(result.time.chart_data) == 2
    current_year_item = next((c for c in result.time.chart_data if c.year == 2025), None)
    assert current_year_item is not None
    assert current_year_item.percentage == 37.5
    assert result.time.monthly_peak == "2025年7月拍摄最多：4张"


def test_heatmap_stats_year_filter_collects_consecutive_days():
    user_id = uuid4()
    rows = [
        MagicMock(photo_date=_date(2025, 1, 1), count=2),
        MagicMock(photo_date=_date(2025, 1, 2), count=3),
        MagicMock(photo_date=_date(2025, 1, 3), count=1),
        MagicMock(photo_date=_date(2025, 1, 6), count=4),
    ]
    year_rows = [_YearAvail(2025), _YearAvail(2024)]
    queries = [_make_query_mock(all_value=rows), _make_query_mock(all_value=year_rows)]
    db = MagicMock()
    db.query.side_effect = lambda *a, **kw: queries[db.query.call_count - 1]

    result = crud_dashboard.get_heatmap_stats(db, user_id, year=2025)

    assert result.total_photos == 10
    assert result.total_days == 4
    assert result.max_consecutive_days == 3
    assert result.data[0].count == 2
    assert result.available_years == [2025, 2024]


# ---------------------------------------------------------------------------
# Vector CRUD (package/server/app/crud/crud_vector.py) — 34.6% → 目标 ≥ 80%
# 覆盖 §4.5 优先级 5：create_or_update_vector / get_vector / search_similar_vectors。
# ---------------------------------------------------------------------------
from app.crud import crud_vector
from app.db.models.image_vector import ImageVector


def test_crud_vector_create_inserts_new_row_when_missing():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    crud_vector.create_or_update_vector(db, photo_id=uuid4(), embedding=[0.1] * 4, model_name="clip-test")

    db.add.assert_called_once()
    db.commit.assert_called_once()
    db.refresh.assert_called_once()


def test_crud_vector_update_overwrites_existing_row():
    db = MagicMock()
    existing = MagicMock()
    existing.embedding = [0.0] * 4
    existing.model_name = "old-model"
    db.query.return_value.filter.return_value.first.return_value = existing

    crud_vector.create_or_update_vector(db, photo_id=uuid4(), embedding=[0.9] * 4, model_name="new-model")

    assert existing.embedding == [0.9] * 4
    assert existing.model_name == "new-model"
    db.add.assert_not_called()
    db.commit.assert_called_once()


def test_crud_vector_get_returns_existing_or_none():
    db = MagicMock()
    existing = MagicMock(spec=ImageVector)
    db.query.return_value.filter.return_value.first.return_value = existing

    result = crud_vector.get_vector(db, photo_id=uuid4())

    assert result is existing
    db.query.return_value.filter.return_value.first.assert_called_once()


def test_crud_vector_search_similar_applies_user_and_limit_filters():
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [
        (MagicMock(spec=ImageVector), 0.05),
        (MagicMock(spec=ImageVector), 0.12),
    ]

    results = crud_vector.search_similar_vectors(
        db, embedding=[0.1] * 4, limit=2, offset=0, user_id=uuid4()
    )

    assert len(results) == 2
    db.query.assert_called_once()
    db.query.return_value.join.assert_called_once()
