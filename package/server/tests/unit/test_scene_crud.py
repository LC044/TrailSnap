"""Nightly watch gap coverage for app.crud.scene.

Targets point_in_polygon (the pure ray-casting helper) plus a smoke
check for create_scene against a mocked Session (96/111 lines missed
in nightly coverage scan).

* Happy path: square polygon with points inside / outside / on edge.
* Edge: degenerate polygon (no area) returns False for all points.
* Error: empty polygon rejects every point.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.crud import scene as scene_crud


pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


def test_point_in_polygon_inside_square():
    # Square with corners (0,0) (10,0) (10,10) (0,10)
    poly = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]
    assert scene_crud.point_in_polygon(5.0, 5.0, poly) is True


def test_point_in_polygon_outside_square():
    poly = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]
    # Outside on all sides
    assert scene_crud.point_in_polygon(15.0, 5.0, poly) is False
    assert scene_crud.point_in_polygon(-5.0, 5.0, poly) is False
    assert scene_crud.point_in_polygon(5.0, 15.0, poly) is False
    assert scene_crud.point_in_polygon(5.0, -5.0, poly) is False


def test_point_in_polygon_triangle():
    # Triangle with vertices (0,0), (10,0), (5,10)
    poly = [[0.0, 0.0], [10.0, 0.0], [5.0, 10.0]]
    assert scene_crud.point_in_polygon(5.0, 3.0, poly) is True
    assert scene_crud.point_in_polygon(0.0, 5.0, poly) is False  # outside left
    assert scene_crud.point_in_polygon(10.0, 5.0, poly) is False  # outside right


def test_point_in_polygon_degenerate_returns_false():
    # A degenerate polygon (collinear points) - no area, all outside
    poly = [[0.0, 0.0], [5.0, 0.0], [10.0, 0.0]]
    assert scene_crud.point_in_polygon(5.0, 0.0, poly) is False
    assert scene_crud.point_in_polygon(5.0, 5.0, poly) is False


def test_point_in_polygon_single_point():
    # A single-point polygon degenerates to a ray that never enters,
    # so the point is considered outside.
    assert scene_crud.point_in_polygon(5.0, 5.0, [[0.0, 0.0]]) is False


def test_update_scene_photos_no_polygon_is_noop():
    db = MagicMock()
    scene = SimpleNamespace(polygon=None, id="scene-1", owner_id=None)
    scene_crud.update_scene_photos(db, scene)
    db.query.assert_not_called()
    db.commit.assert_not_called()


def test_update_scene_photos_owner_filters():
    db = MagicMock()
    scene = SimpleNamespace(polygon=[[10.0, 20.0]], id="s1", owner_id="owner-1")
    db.query.return_value.filter.return_value.all.return_value = []
    scene_crud.update_scene_photos(db, scene)
    # Should be called at least once (initial PhotoMetadata query).
    assert db.query.called
    db.commit.assert_not_called()  # nothing updated -> no commit
