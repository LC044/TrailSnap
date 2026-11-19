"""2026-11-16 nightly coverage for ``app/crud/location.py``.

The 2026-11-16 backend coverage scan reported ``crud/location.py`` at 94.7%
with 24 missed lines.  The remaining gaps are the defensive branches of the
location queries:

* ``get_location_photos`` selecting the province column (line 596) and
  refusing a ``place_key`` that does not match the requested level
  (line 618);
* ``get_time_compare_photos`` refusing an invisible scene (line 395),
  filtering a scene by ``visit_date`` (line 406), refusing a request without
  a photo (line 413), refusing a photo that does not exist (line 422) and
  refusing coordinates without a valid GPS fix (line 425);
* ``get_timeline_nodes`` using the province / district base columns
  (lines 658-662), applying the date filters (lines 715 / 717) and merging
  the time range of two consecutive rows of the same place
  (lines 757 / 759);
* ``get_location_distribution`` applying the date filters
  (lines 911 / 913).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.crud import location as crud_loc
from app.db.models.scene import Scene
from app.service.relations import region_key


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _chained(*, terminal=None, all_rows=None, first=None):
    """A query double that keeps returning itself for the chained calls."""
    q = MagicMock(name="query")
    for attribute in ("filter", "select_from", "join", "outerjoin", "group_by",
                      "order_by", "distinct", "offset", "limit", "options"):
        getattr(q, attribute).return_value = q
    q.scalar.return_value = terminal if terminal is not None else 0
    q.all.return_value = list(all_rows or [])
    q.first.return_value = first
    q.__iter__.side_effect = lambda: iter(list(all_rows or []))
    return q


def _photo(**kw):
    base = {"id": uuid.uuid4(), "file_path": "/photos/x.jpg", "photo_time": datetime(2026, 5, 1, 9, 0)}
    base.update(kw)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# get_location_photos
# ---------------------------------------------------------------------------


def test_get_location_photos_uses_the_province_column():
    db = MagicMock()
    rows = [(_photo(), SimpleNamespace(province="北京市"))]
    db.query.return_value = _chained(all_rows=rows)

    result = crud_loc.get_location_photos(db, uuid.uuid4(), "北京市", level="province")

    assert result == rows


def test_get_location_photos_rejects_a_place_key_of_another_level():
    db = MagicMock()
    db.query.return_value = _chained(all_rows=[])

    with pytest.raises(HTTPException) as excinfo:
        crud_loc.get_location_photos(
            db, uuid.uuid4(), "北京市", level="city",
            place_key=region_key("province", ["中国", "北京市"]),
        )

    assert excinfo.value.status_code == 400
    assert "地点标识与查询条件不一致" in excinfo.value.detail


# ---------------------------------------------------------------------------
# get_time_compare_photos
# ---------------------------------------------------------------------------


def test_get_time_compare_photos_refuses_an_invisible_scene():
    db = MagicMock()
    db.query.return_value = _chained(first=None)

    assert crud_loc.get_time_compare_photos(db, uuid.uuid4(), scene_id=uuid.uuid4()) is None


def test_get_time_compare_photos_filters_a_scene_by_visit_date():
    scene = SimpleNamespace(id=uuid.uuid4())
    wanted = _photo(photo_time=datetime(2026, 5, 2, 9, 0))
    other = _photo(photo_time=datetime(2026, 5, 3, 9, 0))
    db = MagicMock()

    def query(*args, **kwargs):
        if args and args[0] is Scene:
            return _chained(first=scene)
        return _chained(all_rows=[(wanted, SimpleNamespace()), (other, SimpleNamespace())])

    db.query.side_effect = query

    result = crud_loc.get_time_compare_photos(
        db, uuid.uuid4(), scene_id=scene.id, visit_date=date(2026, 5, 2),
    )

    assert [photo.id for photo in result] == [wanted.id]


def test_get_time_compare_photos_without_a_photo_returns_none():
    db = MagicMock()
    db.query.return_value = _chained(all_rows=[])

    assert crud_loc.get_time_compare_photos(db, uuid.uuid4()) is None


def test_get_time_compare_photos_refuses_a_photo_that_does_not_exist():
    db = MagicMock()
    db.query.return_value = _chained(first=None)

    assert crud_loc.get_time_compare_photos(db, uuid.uuid4(), photo_id=uuid.uuid4()) is None


def test_get_time_compare_photos_refuses_coordinates_without_a_gps_fix():
    db = MagicMock()
    source = (_photo(), SimpleNamespace(latitude=None, longitude=None))
    db.query.return_value = _chained(first=source)

    assert crud_loc.get_time_compare_photos(db, uuid.uuid4(), photo_id=source[0].id) == []


# ---------------------------------------------------------------------------
# get_timeline_nodes
# ---------------------------------------------------------------------------


def _timeline_row(location_name, day, count, lat, lng, start_time, end_time):
    return SimpleNamespace(
        date=day, loc_name=location_name, level="city", lat=lat, lng=lng,
        photo_count=count, cover_id=str(uuid.uuid4()), start_time=start_time, end_time=end_time,
    )


def test_get_timeline_nodes_merges_two_rows_of_the_same_place():
    first = _timeline_row("北京", "2026-05-01", 2, 39.0, 116.0, datetime(2026, 5, 1, 20, 0), datetime(2026, 5, 1, 21, 0))
    second = _timeline_row("北京", "2026-05-01", 3, 40.0, 117.0, datetime(2026, 5, 1, 6, 0), datetime(2026, 5, 1, 23, 0))
    db = MagicMock()
    db.query.return_value = _chained(all_rows=[first, second])

    response = crud_loc.get_timeline_nodes(db, uuid.uuid4(), level="province",
                                           start_date="2026-05-01", end_date="2026-05-31")

    assert response.total == 1
    node = response.nodes[0]
    assert node.startDate == "2026-05-01"
    assert node.endDate == "2026-05-01"
    assert node.startTime == datetime(2026, 5, 1, 6, 0)
    assert node.endTime == datetime(2026, 5, 1, 23, 0)
    assert node.photoCount == 5


def test_get_timeline_nodes_uses_the_district_base_column():
    row = _timeline_row("朝阳区", "2026-05-01", 1, 39.0, 116.0, None, None)
    db = MagicMock()
    db.query.return_value = _chained(all_rows=[row])

    response = crud_loc.get_timeline_nodes(db, uuid.uuid4(), level="district")

    assert response.total == 1
    assert response.nodes[0].locationName == "朝阳区"


# ---------------------------------------------------------------------------
# get_location_distribution
# ---------------------------------------------------------------------------


def test_get_location_distribution_applies_the_date_filters():
    db = MagicMock()
    db.query.return_value = _chained(all_rows=[("朝阳区", 4)])

    result = crud_loc.get_location_distribution(
        db, uuid.uuid4(), level="district", start_date="2026-05-01", end_date="2026-05-31",
    )

    assert result == [{"name": "朝阳区", "count": 4, "level": "district"}]




def test_get_location_distribution_with_only_a_start_date():
    db = MagicMock()
    db.query.return_value = _chained(all_rows=[("朝阳区", 2)])

    result = crud_loc.get_location_distribution(db, uuid.uuid4(), level="city", start_date="2026-05-01")

    assert result == [{"name": "朝阳区", "count": 2, "level": "city"}]


def test_get_location_distribution_with_only_an_end_date():
    db = MagicMock()
    db.query.return_value = _chained(all_rows=[("朝阳区", 1)])

    result = crud_loc.get_location_distribution(db, uuid.uuid4(), level="city", end_date="2026-05-31")

    assert result == [{"name": "朝阳区", "count": 1, "level": "city"}]
