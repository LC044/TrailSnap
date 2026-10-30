"""Unit tests for the remaining ``app/crud/location.py`` helpers.

Coverage scan 2026-10-30 showed the module at 88.1% with 53 missed lines.
Most of them sit in the time-compare helpers, which rank photos against a
reference row:

* ``_cosine_similarity`` must return ``None`` for a zero vector instead of
  dividing by zero;
* ``_photo_orientation`` must recognise a square photo;
* ``_embedding_map`` must short-circuit for an empty id list;
* ``_recommended_pair`` must skip candidates with a different orientation
  and report "no pair" when nothing is comparable;
* ``_recommended_pair`` must sample very large scenes instead of comparing
  every pair.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest


pytestmark = [pytest.mark.smoke]


from app.crud import location as location_crud  # noqa: E402


class _FakeQuery:
    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return []


class _FakeDB:
    def query(self, *args, **kwargs):
        return _FakeQuery()


def _metadata(latitude=31.0, longitude=121.0):
    return SimpleNamespace(latitude=latitude, longitude=longitude)


def _photo(photo_id, photo_time, width=100, height=100):
    return SimpleNamespace(id=photo_id, photo_time=photo_time, width=width, height=height)


def _row(photo_id, photo_time, width=100, height=100):
    return (_photo(photo_id, photo_time, width, height), _metadata())


# -------------------------------------------------------------------------
# pure helpers
# -------------------------------------------------------------------------


def test_cosine_similarity_returns_none_for_zero_vector():
    assert location_crud._cosine_similarity([0.0, 0.0], [1.0, 2.0]) is None


def test_photo_orientation_detects_a_square_photo():
    assert location_crud._photo_orientation(_photo("p", datetime(2024, 1, 1), 100, 100)) == "square"


def test_embedding_map_short_circuits_for_empty_ids():
    assert location_crud._embedding_map(_FakeDB(), []) == {}


# -------------------------------------------------------------------------
# _recommended_pair
# -------------------------------------------------------------------------


def test_recommended_pair_is_none_when_orientations_do_not_match():
    rows = [
        _row("p-1", datetime(2024, 1, 1), width=200, height=100),
        _row("p-2", datetime(2023, 1, 1), width=100, height=200),
    ]

    left, right = location_crud._recommended_pair(_FakeDB(), rows)

    assert (left, right) == (None, None)


def test_recommended_pair_picks_a_comparable_pair():
    rows = [
        _row("p-1", datetime(2024, 1, 1)),
        _row("p-2", datetime(2023, 6, 1)),
    ]

    left, right = location_crud._recommended_pair(_FakeDB(), rows)

    assert left is not None and right is not None
    assert left.photo_time <= right.photo_time


def test_recommended_pair_samples_very_large_scenes():
    start = datetime(2020, 1, 1)
    rows = []
    for index in range(120):
        rows.append(_row(f"a-{index}", start + timedelta(days=index)))
    for index in range(120):
        rows.append(_row(f"b-{index}", datetime(2023, 1, 1) + timedelta(days=index)))

    left, right = location_crud._recommended_pair(_FakeDB(), rows)

    assert left is not None and right is not None
    assert left.photo_time.year != right.photo_time.year
