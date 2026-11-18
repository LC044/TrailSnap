"""2026-11-16 nightly coverage for the Agent photo-context location identity.

The 2026-11-16 backend coverage scan showed that
``app/service/agent/actions.py::_location_identity`` was never referenced by
any test.  The helper decides whether two photo snapshots describe the same
place, and it must only trust precise coordinates or an exact address:

* both coordinates -> a rounded GPS identity;
* an address only  -> a normalized (case folded, whitespace collapsed)
  address identity;
* neither         -> no identity at all, so the repair planner must not
  propose a location match.
"""

from __future__ import annotations

import pytest

from app.service.agent import actions as agent_actions


pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


def test_location_identity_prefers_rounded_coordinates():
    identity = agent_actions._location_identity(
        {"latitude": 31.230416, "longitude": 121.473701, "address": "南京东路"}
    )
    assert identity == ("gps", 31.2304, 121.4737)


def test_location_identity_normalizes_an_address():
    identity = agent_actions._location_identity({"address": "  上海市   黄浦区 南京东路 "})
    assert identity == ("address", "上海市 黄浦区 南京东路")


def test_location_identity_ignores_a_partial_coordinate_pair():
    assert agent_actions._location_identity({"latitude": 31.2, "address": "南京东路"}) == \
        ("address", "南京东路")


def test_location_identity_returns_none_without_evidence():
    assert agent_actions._location_identity({}) is None
    assert agent_actions._location_identity({"address": "   "}) is None
