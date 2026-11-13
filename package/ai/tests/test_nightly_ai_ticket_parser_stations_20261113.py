"""Nightly watch 2026-11-13 (round 2): ticket parser station-candidate gaps.

Targets the branches the 2026-11-13 coverage snapshot still reports as
uncovered in ``app/services/ticket_parser.py``:

* ``_station_candidates`` - the leading/trailing ``始``/``终``/``过``/``一``
  markers printed next to the real station name, and the "same row as a train
  service number" fallback for a station that is not in the known list.
* ``_pick_dep_arr_from_station_candidates`` - a single candidate only yields
  the departure station.

Every test exercises already-implemented behaviour; no production change.
"""

from __future__ import annotations

import pytest

from app.services import ticket_parser

pytestmark = [pytest.mark.smoke]


def _poly(x, y, w=60, h=20):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def _names(candidates):
    return [c[0] for c in candidates]


def test_station_candidates_strips_a_leading_start_marker():
    texts = ["始北京站"]
    polys = [_poly(20, 300)]

    candidates = ticket_parser._station_candidates(texts, polys)

    assert "北京" in _names(candidates)


def test_station_candidates_strips_a_trailing_end_marker():
    texts = ["北京终站"]
    polys = [_poly(20, 300)]

    candidates = ticket_parser._station_candidates(texts, polys)

    assert "北京" in _names(candidates)


def test_station_candidates_accepts_an_unknown_station_next_to_a_train_number():
    texts = ["三棵树", "梨园", "北京", "G1234次"]
    polys = [_poly(20, 300), _poly(300, 300), _poly(600, 300), _poly(900, 302)]

    candidates = ticket_parser._station_candidates(texts, polys)

    assert "三棵树" in _names(candidates)


def test_pick_dep_arr_returns_the_only_candidate_as_departure():
    assert ticket_parser._pick_dep_arr_from_station_candidates(
        [("北京", 100.0, 200.0)]
    ) == ("北京", "")


def test_pick_dep_arr_returns_empty_for_no_candidate():
    assert ticket_parser._pick_dep_arr_from_station_candidates([]) == ("", "")

