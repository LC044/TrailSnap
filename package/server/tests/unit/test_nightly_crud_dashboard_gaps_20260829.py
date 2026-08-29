"""Unit tests covering 2026-08-29 nightly coverage gap scan.

Targets `app/crud/dashboard.py` (3 functions, previously no direct unit
coverage; exercised only through `api/stats.py` wrappers). The functions
build a ``DashboardResponse`` / ``HeatmapResponse`` /
``EmotionCalendarResponse`` from several SQLAlchemy queries + a small
amount of Python aggregation.

MagicMock-based: each `db.query(...)` returns a fresh fluent chain so
``filter/.join/.group_by/.order_by`` compose naturally and the terminal
``count/.scalar/.first/.all`` can be set per-call via side_effect
lists. Helpers (face identities list, date helpers) are patched at the
source module to avoid pulling in the rest of the ORM graph.
"""
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# Fluent chain helpers + Row helper
# ---------------------------------------------------------------------------


class Row:
    """Minimal SQLAlchemy ``Row``-like stand-in.

    Supports both attribute access (``.year`` / ``.count``) and tuple
    unpacking so crud/dashboard.py's mixed access patterns (see
    ``year_stats`` iteration) keep working.
    """

    def __init__(self, **kwargs):
        self._fields = tuple(kwargs.keys())
        self._values = tuple(kwargs.values())
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __iter__(self):
        return iter(self._values)

    def __getitem__(self, idx):
        return self._values[idx]

    def __len__(self):
        return len(self._values)


def _chain(terminal):
    """Return a chain whose intermediate calls return self and whose
    terminal methods return values from the provided dict.
    """
    chain = MagicMock(name="query-chain")
    # Wire terminal methods FIRST so the chain method assignments below
    # don't overwrite them via setattr.
    for attr, value in terminal.items():
        method_name = attr.split(".")[0]
        setattr(chain, method_name, MagicMock(return_value=value))
    # Now wire chain methods (filter/join/etc.) to return self.
    chain.filter.return_value = chain
    chain.join.return_value = chain
    chain.group_by.return_value = chain
    chain.order_by.return_value = chain
    chain.outerjoin.return_value = chain
    chain.subquery.return_value = MagicMock(name="subquery")
    chain.label.return_value = MagicMock(name="label")
    return chain


def _db_with_terminals(terminals, spares=8):
    """Build a Mock Session whose successive ``db.query(...)`` calls hand
    out a fresh fluent chain wired to the next terminal dict in
    ``terminals``. ``spares`` extra ``{count.return_value: 0}`` chains are
    appended so callers don't have to count queries exactly.
    """
    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    padded = list(terminals) + [{"count.return_value": 0}] * spares
    iter_t = iter(padded)
    db.query.side_effect = lambda *a, **kw: _chain(next(iter_t))
    return db


# ---------------------------------------------------------------------------
# get_dashboard_stats
# ---------------------------------------------------------------------------


def test_get_dashboard_stats_empty_user_returns_zero_card_and_no_monthly_peak():
    """No photos => card zeros, top_faces empty, monthly_peak fallback."""
    from app.crud import dashboard as crud_dashboard

    terminals = [
        {"count.return_value": 0},  # total_media
        {"count.return_value": 0},  # today_new
        {"scalar.return_value": 0},  # total_size
        {"count.return_value": 0},  # total_identified
        {"count.return_value": 0},  # pending_faces_count
        {"scalar.return_value": 0},  # unidentified_photos
        {"count.return_value": 0},  # photos_count
        {"count.return_value": 0},  # videos_count
        {"count.return_value": 0},  # scenery
        {"count.return_value": 0},  # food
        {"all.return_value": []},  # year_stats
        {"first.return_value": None},  # month_stats
    ]
    db = _db_with_terminals(terminals)
    owner_id = uuid4()

    with patch(
        "app.crud.dashboard.get_identities_with_details", return_value=[]
    ):
        result = crud_dashboard.get_dashboard_stats(db, owner_id=owner_id)

    assert result.card.total_media == 0
    assert result.card.today_new == 0
    assert result.card.storage_used == "0.0GB"
    assert result.face.total_identified == 0
    assert result.face.pending_faces_count == 0
    assert result.face.unidentified_photos_count == 0
    assert result.face.top_faces == []
    assert result.content.photos.total == 0
    assert result.content.videos.total == 0
    assert result.content.scenery_count == 0
    assert result.content.food_count == 0
    assert result.time.chart_data == []
    assert result.time.current_year_percentage == 0
    assert result.time.monthly_peak == "\u6682\u65e0\u6570\u636e"


def test_get_dashboard_stats_with_photos_populates_card_face_content_time():
    """Mixed photos/videos/identities => every section filled in."""
    from app.crud import dashboard as crud_dashboard

    current_year = datetime.now().year
    top_face = SimpleNamespace(id=uuid4(), name="alice")
    year_rows = [
        Row(year=2024, count=80),
        Row(year=current_year, count=20),
    ]
    month_row = SimpleNamespace(year=current_year, month=5, count=15)

    terminals = [
        {"count.return_value": 200},  # total_media
        {"count.return_value": 3},  # today_new
        {"scalar.return_value": 5 * 1024 ** 3},  # 5 GB
        {"count.return_value": 12},  # total_identified
        {"count.return_value": 4},  # pending_faces
        {"scalar.return_value": 3},  # unidentified_photos
        {"count.return_value": 150},  # photos
        {"count.return_value": 50},  # videos
        {"count.return_value": 25},  # scenery
        {"count.return_value": 7},  # food
        {"all.return_value": year_rows},  # year_stats
        {"first.return_value": month_row},  # month_stats
    ]
    db = _db_with_terminals(terminals)
    owner_id = uuid4()

    with patch(
        "app.crud.dashboard.get_identities_with_details", return_value=[top_face]
    ) as get_identities:
        result = crud_dashboard.get_dashboard_stats(db, owner_id=owner_id)

    assert result.card.total_media == 200
    assert result.card.today_new == 3
    assert result.card.storage_used == "5.0GB"
    assert result.face.total_identified == 12
    assert len(result.face.top_faces) == 1
    assert str(result.face.top_faces[0].id) == str(top_face.id)
    get_identities.assert_called_once_with(db, owner_id=owner_id, skip=0, limit=3)
    assert result.content.photos.total == 150
    assert result.content.videos.total == 50
    assert result.content.scenery_count == 25
    assert result.content.food_count == 7
    assert len(result.time.chart_data) == 2
    chart_tuples = [(item.year, item.count, item.percentage) for item in result.time.chart_data]
    assert (2024, 80, 80.0) in chart_tuples
    assert (current_year, 20, 20.0) in chart_tuples
    assert result.time.current_year_percentage == 20
    assert str(current_year) in result.time.monthly_peak
    assert "5\u6708" in result.time.monthly_peak
    assert "15\u5f20" in result.time.monthly_peak


def test_get_dashboard_stats_skips_null_year_rows_in_chart():
    """Some DBs can return a NULL year bucket; crud should skip it without
    raising and without polluting chart_data with year=None entries."""
    from app.crud import dashboard as crud_dashboard

    terminals = [
        {"count.return_value": 1},
        {"count.return_value": 0},
        {"scalar.return_value": 0},
        {"count.return_value": 0},
        {"count.return_value": 0},
        {"scalar.return_value": 0},
        {"count.return_value": 1},
        {"count.return_value": 0},
        {"count.return_value": 0},
        {"count.return_value": 0},
        {"all.return_value": [Row(year=None, count=1), Row(year=2025, count=1)]},
        {"first.return_value": None},
    ]
    db = _db_with_terminals(terminals)

    with patch(
        "app.crud.dashboard.get_identities_with_details", return_value=[]
    ):
        result = crud_dashboard.get_dashboard_stats(db, owner_id=uuid4())

    chart_years = [item.year for item in result.time.chart_data]
    assert None not in chart_years
    assert 2025 in chart_years
    # Single valid row contributes one chart entry.
    assert len([y for y in chart_years if y is not None]) == 1


# ---------------------------------------------------------------------------
# get_heatmap_stats
# ---------------------------------------------------------------------------


def test_get_heatmap_stats_with_year_picks_year_window_and_counts_consecutive_days():
    """Year-mode: window is Jan 1 - Dec 31; consecutive days tracked."""
    from app.crud import dashboard as crud_dashboard

    day1 = Row(photo_date=date(2024, 1, 1), count=3)
    day2 = Row(photo_date=date(2024, 1, 2), count=1)
    day4 = Row(photo_date=date(2024, 1, 4), count=2)
    year_rows = [Row(year=2024), Row(year=2023)]

    terminals = [
        {"all.return_value": [day1, day2, day4]},  # main query
        {"all.return_value": year_rows},  # years query
    ]
    db = _db_with_terminals(terminals)
    owner_id = uuid4()

    with patch.object(crud_dashboard, "date_only", return_value=MagicMock(name="date_expr")):
        result = crud_dashboard.get_heatmap_stats(db, owner_id=owner_id, year=2024)

    assert result.total_photos == 6
    assert result.total_days == 3
    # day1 + day2 = 2 consecutive; day4 breaks the streak.
    assert result.max_consecutive_days == 2
    assert [item.date for item in result.data] == [
        "2024-01-01",
        "2024-01-02",
        "2024-01-04",
    ]
    assert result.available_years == [2024, 2023]


def test_get_heatmap_stats_no_year_uses_trailing_year_window_and_handles_empty():
    """No-year mode should still work and return zero streak on empty data."""
    from app.crud import dashboard as crud_dashboard

    terminals = [
        {"all.return_value": []},  # main query
        {"all.return_value": []},  # years query
    ]
    db = _db_with_terminals(terminals)
    owner_id = uuid4()

    with patch.object(crud_dashboard, "date_only", return_value=MagicMock(name="date_expr")):
        result = crud_dashboard.get_heatmap_stats(db, owner_id=owner_id, year=None)

    assert result.total_photos == 0
    assert result.total_days == 0
    assert result.max_consecutive_days == 0
    assert result.data == []
    assert result.available_years == []


def test_get_heatmap_stats_filters_out_null_year_rows_from_available_years():
    """Available-years list must skip NULL year buckets from raw query."""
    from app.crud import dashboard as crud_dashboard

    terminals = [
        {"all.return_value": [Row(photo_date=date(2025, 6, 1), count=2)]},
        {"all.return_value": [Row(year=None), Row(year=2025)]},
    ]
    db = _db_with_terminals(terminals)

    with patch.object(crud_dashboard, "date_only", return_value=MagicMock(name="date_expr")):
        result = crud_dashboard.get_heatmap_stats(db, owner_id=uuid4(), year=2025)

    assert result.available_years == [2025]


# ---------------------------------------------------------------------------
# get_emotion_calendar_stats
# ---------------------------------------------------------------------------


def test_get_emotion_calendar_stats_year_mode_aggregates_per_day_without_color_records():
    """Year-mode + no PhotoColor rows -> per-day items have None color hints
    but still carry photo_count + top_categories from yolo tag map."""
    from app.crud import dashboard as crud_dashboard

    photo_a = uuid4()
    photo_b = uuid4()
    day1 = Row(photo_date=date(2024, 7, 1), count=2)
    day2 = Row(photo_date=date(2024, 7, 2), count=1)

    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    main_chain = MagicMock()
    main_chain.filter.return_value = main_chain
    main_chain.all.side_effect = [
        [day1, day2],  # date_counts
        [  # photo_date_rows
            Row(photo_date=date(2024, 7, 1), photo_id=photo_a),
            Row(photo_date=date(2024, 7, 1), photo_id=photo_b),
            Row(photo_date=date(2024, 7, 2), photo_id=photo_a),
        ],
        [],  # PhotoColor query (empty)
        [  # tag_rows via JOIN
            SimpleNamespace(photo_id=photo_a, tag_name="dog"),
            SimpleNamespace(photo_id=photo_a, tag_name="cat"),
            SimpleNamespace(photo_id=photo_b, tag_name="dog"),
        ],
        [Row(year=2024)],  # available_years
    ]
    db.query.return_value = main_chain
    # Wire ALL intermediate fluent methods on main_chain back to itself so
    # .all() always lands on the same mock and side_effect items are
    # consumed in order across queries that include group_by/order_by/join.
    for _method in ("filter", "join", "outerjoin", "group_by", "order_by"):
        setattr(main_chain, _method, MagicMock(return_value=main_chain))
    owner_id = uuid4()

    with patch.object(crud_dashboard, "date_only", return_value=MagicMock(name="date_expr")), \
         patch.object(crud_dashboard, "as_date_string", side_effect=lambda d: d.isoformat()):
        result = crud_dashboard.get_emotion_calendar_stats(db, owner_id=owner_id, year=2024)

    assert result.total_photos == 3
    assert result.total_days == 2
    assert result.available_years == [2024]
    by_date = {item.date: item for item in result.data}
    assert set(by_date) == {"2024-07-01", "2024-07-02"}
    assert by_date["2024-07-01"].photo_count == 2
    assert by_date["2024-07-01"].top_categories == ["dog", "cat"]
    assert by_date["2024-07-01"].dominant_color is None
    assert by_date["2024-07-01"].emotion_hint is None
    assert by_date["2024-07-02"].photo_count == 1


def test_get_emotion_calendar_stats_handles_photo_color_query_failure_gracefully():
    """If the PhotoColor table doesn't exist, the inner except logs and
    falls back to an empty color_map. Items still render with None colors."""
    from app.crud import dashboard as crud_dashboard

    photo_a = uuid4()
    day1 = Row(photo_date=date(2025, 3, 10), count=1)

    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    main_chain = MagicMock()
    main_chain.filter.return_value = main_chain
    for _method in ("join", "outerjoin", "group_by", "order_by"):
        setattr(main_chain, _method, MagicMock(return_value=main_chain))
    color_query = MagicMock()
    color_query.filter.return_value = color_query
    color_query.all.side_effect = Exception("relation photo_colors does not exist")

    def query_router(*args, **kwargs):
        # The arg is the class itself, so check the class's __name__, not
        # type(arg).__name__ (which is "type" for any class object).
        if args and getattr(args[0], "__name__", "") == "PhotoColor":
            return color_query
        return main_chain

    db.query.side_effect = query_router
    main_chain.all.side_effect = [
        [day1],  # date_counts
        [Row(photo_date=date(2025, 3, 10), photo_id=photo_a)],  # photo_date_rows
        [],  # tag_rows (no tags)
        [Row(year=2025)],  # available_years
    ]
    db.rollback = MagicMock()

    with patch.object(crud_dashboard, "date_only", return_value=MagicMock(name="date_expr")), \
         patch.object(crud_dashboard, "as_date_string", side_effect=lambda d: d.isoformat()):
        result = crud_dashboard.get_emotion_calendar_stats(db, owner_id=uuid4(), year=2025)

    db.rollback.assert_called()
    assert result.total_photos == 1
    assert result.data[0].dominant_color is None
    assert result.data[0].top_categories == []


def test_get_emotion_calendar_stats_picks_dominant_color_and_emotion_hint():
    """When PhotoColor rows exist, dominant_color + emotion_hint reflect
    the most frequent hex + emotion_hint across photos on that day."""
    from app.crud import dashboard as crud_dashboard

    photo_a = uuid4()
    photo_b = uuid4()
    day1 = Row(photo_date=date(2025, 8, 15), count=2)

    def color_record(photo_id, emotion, brightness, saturation, hex_):
        return SimpleNamespace(
            photo_id=photo_id,
            emotion_hint=emotion,
            brightness=brightness,
            saturation=saturation,
            dominant_colors=[{"hex": hex_}],
        )

    color_records = [
        color_record(photo_a, "happy", 0.7, 0.5, "#ff0000"),
        color_record(photo_b, "happy", 0.3, 0.5, "#00ff00"),
    ]

    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    main_chain = MagicMock()
    main_chain.filter.return_value = main_chain
    for _method in ("join", "outerjoin", "group_by", "order_by"):
        setattr(main_chain, _method, MagicMock(return_value=main_chain))
    main_chain.all.side_effect = [
        [day1],
        [
            Row(photo_date=date(2025, 8, 15), photo_id=photo_a),
            Row(photo_date=date(2025, 8, 15), photo_id=photo_b),
        ],
        color_records,  # PhotoColor records
        [],  # tag rows
        [Row(year=2025)],  # available_years
    ]
    db.query.return_value = main_chain

    with patch.object(crud_dashboard, "date_only", return_value=MagicMock(name="date_expr")), \
         patch.object(crud_dashboard, "as_date_string", side_effect=lambda d: d.isoformat()):
        result = crud_dashboard.get_emotion_calendar_stats(db, owner_id=uuid4(), year=2025)

    item = result.data[0]
    assert item.emotion_hint == "happy"
    assert item.dominant_color in {"#ff0000", "#00ff00"}
    assert item.brightness == pytest.approx(0.5)
    assert item.saturation == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Regression: face identity list must propagate even when Pydantic normalises
# the SimpleNamespace to FaceIdentitySchema in DashboardFace.
# ---------------------------------------------------------------------------


def test_get_dashboard_stats_face_top_faces_preserves_identity_ids():
    """The mock returns SimpleNamespace-like objects; Pydantic wraps them as
    FaceIdentitySchema in DashboardFace, so we assert by id rather than by
    object equality."""
    from app.crud import dashboard as crud_dashboard
    from app.schemas.face import FaceIdentitySchema

    top_face_a = SimpleNamespace(id=uuid4(), name="alice")
    top_face_b = SimpleNamespace(id=uuid4(), name="bob")

    terminals = [
        {"count.return_value": 5},  # total_media
        {"count.return_value": 0},  # today_new
        {"scalar.return_value": 0},  # total_size
        {"count.return_value": 2},  # total_identified
        {"count.return_value": 0},  # pending_faces
        {"scalar.return_value": 0},  # unidentified_photos
        {"count.return_value": 5},  # photos
        {"count.return_value": 0},  # videos
        {"count.return_value": 0},  # scenery
        {"count.return_value": 0},  # food
        {"all.return_value": []},  # year_stats
        {"first.return_value": None},  # month_stats
    ]
    db = _db_with_terminals(terminals)
    owner_id = uuid4()

    with patch(
        "app.crud.dashboard.get_identities_with_details",
        return_value=[top_face_a, top_face_b],
    ):
        result = crud_dashboard.get_dashboard_stats(db, owner_id=owner_id)

    assert len(result.face.top_faces) == 2
    assert all(isinstance(f, FaceIdentitySchema) for f in result.face.top_faces)
    assert {str(f.id) for f in result.face.top_faces} == {
        str(top_face_a.id),
        str(top_face_b.id),
    }
