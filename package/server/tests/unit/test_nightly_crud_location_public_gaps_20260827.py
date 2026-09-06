"""Unit tests for the gap-remaining public functions in crud/location.

Why this file exists:

* The nightly gap scan flagged ``app/crud/location.py`` as 59.2% covered
  (75 missed lines out of 184). The previous round
  (``test_nightly_crud_photo_location_album_gaps_20260812.py``) covers
  ``get_location_years`` + the invalid-level fallbacks for
  ``get_locations`` / ``get_location_photos`` /
  ``get_location_distribution`` + ``search_locations`` happy path.
  This file fills the remaining uncovered surface:

  - ``get_locations`` valid-level cover fetch (city / province / district /
    scene -- including the cover-map fallback when ``.all()`` returns no
    rows the second time)
  - ``get_location_photos`` valid-level filter (city / scene branches)
  - ``get_map_markers`` happy path + the date-filter branch
  - ``get_timeline_nodes`` -- city level with consecutive same-location
    rows (merge) and a fresh location append; also the scene level branch
    that returns the full coalesce/case expression.
"""

from datetime import date as _date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.crud import location as crud_loc


pytestmark = [pytest.mark.smoke, pytest.mark.module_location]


def _chained(*, terminal=None, all_rows=None):
    q = MagicMock(name="query")
    q.filter.return_value = q
    q.join.return_value = q
    q.outerjoin.return_value = q
    q.group_by.return_value = q
    q.order_by.return_value = q
    q.distinct.return_value = q
    q.offset.return_value = q
    q.limit.return_value = q
    q.subquery.return_value = MagicMock(name="subq")
    q.scalar.return_value = terminal if terminal is not None else 0
    if all_rows is not None:
        q.all.return_value = all_rows
    return q


def _photo(**kw):
    base = {"id": uuid4(), "file_path": "/photos/x.jpg", "photo_time": None}
    base.update(kw)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# get_locations -- valid-level cover fetch
# ---------------------------------------------------------------------------


def test_get_locations_city_level_returns_locations_with_cover():
    """City level -> each row carries the cover photo looked up by name."""
    db = MagicMock()
    cover_photo = _photo(id=uuid4(), file_path="/photos/cover.jpg")
    main_q = _chained(all_rows=[("Wuhan", 10), ("Beijing", 5)])
    cover_q = _chained(all_rows=[(cover_photo, "Wuhan"), (_photo(file_path="/photos/b.jpg"), "Beijing")])
    db.query.side_effect = [main_q, cover_q]

    out = crud_loc.get_locations(db, owner_id=uuid4(), level="city")

    assert len(out) == 2
    by_name = {loc["name"]: loc for loc in out}
    assert by_name["Wuhan"]["count"] == 10
    assert by_name["Wuhan"]["level"] == "city"
    assert by_name["Wuhan"]["cover"] is cover_photo


def test_get_locations_scene_level_returns_id_and_is_custom():
    """Scene level -> result includes the Scene.id and is_custom flag."""
    db = MagicMock()
    scene_id = uuid4()
    main_q = _chained(all_rows=[("Bund", scene_id, False, 7)])
    cover_q = _chained(all_rows=[])
    db.query.side_effect = [main_q, cover_q]

    out = crud_loc.get_locations(db, owner_id=uuid4(), level="scene")

    assert len(out) == 1
    assert out[0]["name"] == "Bund"
    assert out[0]["id"] == str(scene_id)
    assert out[0]["is_custom"] is False
    assert out[0]["count"] == 7


def test_get_locations_empty_results_returns_empty_list():
    """If the main query yields no rows, no cover lookup runs and the
    function returns ``[]`` immediately."""
    db = MagicMock()
    db.query.return_value = _chained(all_rows=[])

    out = crud_loc.get_locations(db, owner_id=uuid4(), level="city")

    assert out == []


# ---------------------------------------------------------------------------
# get_location_photos -- valid-level branches
# ---------------------------------------------------------------------------


def test_get_location_photos_city_level_returns_photos():
    """city level: filter on PhotoMetadata.city == name."""
    db = MagicMock()
    photos = [_photo(), _photo(), _photo()]
    db.query.return_value = _chained(all_rows=photos)

    out = crud_loc.get_location_photos(db, owner_id=uuid4(), name="Wuhan", level="city")

    assert out == photos


def test_get_location_photos_scene_level_joins_scene_table():
    """scene level joins Scene via PhotoMetadata.scene_id (separate branch)."""
    db = MagicMock()
    photos = [_photo()]
    db.query.return_value = _chained(all_rows=photos)

    out = crud_loc.get_location_photos(db, owner_id=uuid4(), name="Bund", level="scene")

    assert out == photos


# ---------------------------------------------------------------------------
# get_map_markers
# ---------------------------------------------------------------------------


def test_get_map_markers_returns_dicts_with_float_coords():
    """Each row's lat/lng become float dict values keyed by photo id string."""
    db = MagicMock()
    pid1 = uuid4()
    pid2 = uuid4()
    db.query.return_value = _chained(all_rows=[
        (pid1, 30.5, 114.3),
        (pid2, 31.2, 121.5),
    ])

    out = crud_loc.get_map_markers(db, owner_id=uuid4())

    assert out == [
        {"id": str(pid1), "lat": 30.5, "lng": 114.3},
        {"id": str(pid2), "lat": 31.2, "lng": 121.5},
    ]


def test_get_map_markers_with_date_range_passes_filter_args():
    """Date range params route through the same chain (covered by ``.all````)."""
    db = MagicMock()
    db.query.return_value = _chained(all_rows=[])

    out = crud_loc.get_map_markers(
        db, owner_id=uuid4(), start_date="2026-01-01", end_date="2026-12-31"
    )

    assert out == []


# ---------------------------------------------------------------------------
# get_timeline_nodes
# ---------------------------------------------------------------------------


def test_get_timeline_nodes_city_level_merges_consecutive_same_location():
    """Two consecutive rows with the same ``loc_name`` collapse into one
    TimelineNode whose ``photoCount`` is the sum and lat/lng are averaged."""
    db = MagicMock()
    db.query.return_value = _chained(all_rows=[
        SimpleNamespace(
            date=_date(2026, 8, 10),
            loc_name="Wuhan",
            level="city",
            photo_count=3,
            lat=30.5,
            lng=114.3,
            cover_id=str(uuid4()),
        ),
        SimpleNamespace(
            date=_date(2026, 8, 12),
            loc_name="Wuhan",
            level="city",
            photo_count=5,
            lat=30.6,
            lng=114.4,
            cover_id=str(uuid4()),
        ),
    ])

    out = crud_loc.get_timeline_nodes(db, owner_id=uuid4(), level="city")

    assert out.total == 1
    node = out.nodes[0]
    assert node.locationName == "Wuhan"
    assert node.photoCount == 8
    # Weighted average of (30.5 with 3) and (30.6 with 5).
    assert abs(node.lat - (30.5 * 3 + 30.6 * 5) / 8) < 1e-9


def test_get_timeline_nodes_appends_new_node_on_location_change():
    """A second row with a different ``loc_name`` creates a new node."""
    db = MagicMock()
    db.query.return_value = _chained(all_rows=[
        SimpleNamespace(
            date=_date(2026, 8, 10),
            loc_name="Wuhan",
            level="city",
            photo_count=3,
            lat=30.5,
            lng=114.3,
            cover_id=str(uuid4()),
        ),
        SimpleNamespace(
            date=_date(2026, 9, 1),
            loc_name="Beijing",
            level="city",
            photo_count=2,
            lat=39.9,
            lng=116.4,
            cover_id=str(uuid4()),
        ),
    ])

    out = crud_loc.get_timeline_nodes(db, owner_id=uuid4(), level="city")

    assert out.total == 2
    assert [n.locationName for n in out.nodes] == ["Wuhan", "Beijing"]


def test_get_timeline_nodes_scene_level_returns_response():
    """Scene level exercises the full coalesce/case expression."""
    db = MagicMock()
    db.query.return_value = _chained(all_rows=[])

    out = crud_loc.get_timeline_nodes(db, owner_id=uuid4(), level="scene")

    assert out.total == 0
    assert out.nodes == []


def test_get_timeline_nodes_respects_skip_and_limit():
    """``skip`` slices from the front; ``limit`` slices the result."""
    db = MagicMock()
    rows = []
    for idx, (name, day) in enumerate([
        ("Wuhan", 1), ("Beijing", 5), ("Shanghai", 10), ("Urumqi", 15),
    ]):
        rows.append(SimpleNamespace(
            date=_date(2026, 8, day),
            loc_name=name,
            level="city",
            photo_count=idx + 1,
            lat=30.0 + idx,
            lng=110.0 + idx,
            cover_id=str(uuid4()),
        ))
    db.query.return_value = _chained(all_rows=rows)

    out = crud_loc.get_timeline_nodes(db, owner_id=uuid4(), level="city", skip=1, limit=2)

    assert out.total == 4
    assert [n.locationName for n in out.nodes] == ["Beijing", "Shanghai"]


def test_get_trajectory_points_keeps_capture_order_and_collapses_nearby_photos():
    first_id, second_id, third_id = uuid4(), uuid4(), uuid4()
    rows = [
        SimpleNamespace(id=first_id, photo_time=datetime(2026, 5, 1, 8), latitude=30.0000,
                        longitude=120.0000, province="浙江", city="杭州", district="西湖区", scene_name=None),
        SimpleNamespace(id=second_id, photo_time=datetime(2026, 5, 1, 8, 5), latitude=30.0001,
                        longitude=120.0001, province="浙江", city="杭州", district="西湖区", scene_name=None),
        SimpleNamespace(id=third_id, photo_time=datetime(2026, 5, 1, 10), latitude=30.0200,
                        longitude=120.0200, province="浙江", city="杭州", district="西湖区", scene_name="西湖"),
    ]
    db = MagicMock()
    db.query.return_value = _chained(all_rows=rows)

    out = crud_loc.get_trajectory_points(db, uuid4(), "2026-05-01", "2026-05-01", 360)

    assert out.totalPhotos == 3
    assert len(out.points) == 2
    assert out.points[0].photoCount == 2
    assert out.points[0].capturedAt == datetime(2026, 5, 1, 8)
    assert out.points[1].locationName == "西湖"
    assert out.points[1].level == "scene"
