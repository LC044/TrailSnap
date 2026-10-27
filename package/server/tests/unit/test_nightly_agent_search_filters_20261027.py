"""Nightly coverage for the agent photo-search filters.

The 2026-10-27 backend coverage scan (round 2) reported ``service/agent/tools.py``
at 72.1% with 113 missed lines -- the third largest backend gap.  The missed
code is the *filter* half of the two search tools:

* ``search_photos_tool`` -- the place, province/city/district, scene, tag,
  person, folder and text-embedding filters plus the ``sort_by`` variants.
* ``search_photos_v2`` -- the OCR text, media type, orientation, "has people"
  and quality/memory score filters plus the cursor pagination.

Every filter is a narrowing clause: a wrong one silently hides photos from
the agent.  The tools are driven against a mocked session (the established
pattern of ``test_nightly_agent_tools_gaps_20260814.py``) so no database is
required.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _ctx(db):
    """Build a MagicMock that works as ``with SessionLocal() as db:``."""

    @contextmanager
    def _cm():
        try:
            yield db
        finally:
            pass

    cm = MagicMock()
    cm.__enter__.return_value = db
    cm.__exit__.return_value = False
    cm.return_value = _cm()
    return cm


def _tool(name, user_id):
    from app.service.agent.tools import get_agent_tools

    for tool in get_agent_tools(user_id):
        if tool.name == name:
            return tool
    raise AssertionError(f"tool {name} not found")


def _empty_chain(db):
    """A query chain that returns no rows but accepts every filter."""
    chain = db.query.return_value
    chain.outerjoin.return_value = chain
    chain.join.return_value = chain
    chain.filter.return_value = chain
    chain.order_by.return_value = chain
    chain.limit.return_value = chain
    chain.offset.return_value = chain
    chain.distinct.return_value = chain
    chain.add_columns.return_value = chain
    chain.all.return_value = []
    chain.order_by.return_value.count.return_value = 0
    return chain


def _search_photos(user_id, **kwargs):
    db = MagicMock()
    _empty_chain(db)
    with patch("app.service.agent.tools.SessionLocal", _ctx(db)):
        out = _tool("search_photos_tool", user_id).func(**kwargs)
    return json.loads(out)


def _search_photos_v2(user_id, **kwargs):
    db = MagicMock()
    _empty_chain(db)
    with patch("app.service.agent.tools.SessionLocal", _ctx(db)):
        out = _tool("search_photos_v2", user_id).func(**kwargs)
    return json.loads(out)


# ---------------------------------------------------------------------------
# search_photos_tool -- filters
# ---------------------------------------------------------------------------


def test_search_photos_applies_a_valid_date_range():
    user_id = str(uuid4())

    result = _search_photos(user_id, start_date="2026-01-01", end_date="2026-12-31")

    assert result["total"] == 0
    assert result["photos"] == []


def test_search_photos_applies_a_location_filter():
    user_id = str(uuid4())

    result = _search_photos(user_id, location="杭州")

    assert result["returned"] == 0


def test_search_photos_applies_the_province_city_and_district_filters():
    user_id = str(uuid4())

    result = _search_photos(user_id, provinces=["浙江省"], cities=["杭州市"], districts=["西湖区"])

    assert result["total"] == 0


def test_search_photos_applies_a_scene_filter():
    user_id = str(uuid4())

    result = _search_photos(user_id, scenes=["西湖"])

    assert result["total"] == 0


def test_search_photos_applies_a_tag_filter():
    user_id = str(uuid4())

    result = _search_photos(user_id, tags=["风景"])

    assert result["total"] == 0


def test_search_photos_applies_a_person_filter():
    user_id = str(uuid4())

    result = _search_photos(user_id, persons=["Alice"])

    assert result["total"] == 0


def test_search_photos_applies_a_folder_filter():
    user_id = str(uuid4())

    result = _search_photos(user_id, folders=["旅游"])

    assert result["total"] == 0


def test_search_photos_ignores_an_empty_folder_filter():
    user_id = str(uuid4())

    result = _search_photos(user_id, folders=["", None])

    assert result["total"] == 0


@pytest.mark.parametrize("sort_by", ["quality_score", "memory_score", "photo_time", "unknown"])
def test_search_photos_supports_every_sort_order(sort_by):
    user_id = str(uuid4())

    result = _search_photos(user_id, sort_by=sort_by, limit=10)

    assert result["total"] == 0


def test_search_photos_applies_a_text_description_filter():
    """The embedding filter joins the vector table and adds a similarity."""
    user_id = str(uuid4())
    db = MagicMock()
    _empty_chain(db)

    def fake_get_embedding(description, owner_id, db):
        return [0.1, 0.2, 0.3]

    with patch("app.service.agent.tools.SessionLocal", _ctx(db)), \
         patch("app.service.agent.tools.get_embedding", fake_get_embedding):
        out = _tool("search_photos_tool", user_id).func(description="湖边日落", limit=10)

    parsed = json.loads(out)
    assert parsed["total"] == 0


# ---------------------------------------------------------------------------
# search_photos_v2 -- filters
# ---------------------------------------------------------------------------


def test_search_photos_v2_applies_a_date_range():
    user_id = str(uuid4())

    result = _search_photos_v2(user_id, start_date="2026-01-01", end_date="2026-12-31")

    assert result["total"] == 0
    assert result["photos"] == []


def test_search_photos_v2_applies_a_location_filter():
    user_id = str(uuid4())

    result = _search_photos_v2(user_id, location="西湖")

    assert result["total"] == 0


def test_search_photos_v2_applies_an_ocr_filter():
    user_id = str(uuid4())

    result = _search_photos_v2(user_id, ocr_text="G1234")

    assert result["total"] == 0


def test_search_photos_v2_applies_a_media_type_filter():
    user_id = str(uuid4())

    result = _search_photos_v2(user_id, media_type="image")

    assert result["total"] == 0


@pytest.mark.parametrize("orientation", ["landscape", "portrait", "square"])
def test_search_photos_v2_applies_every_orientation_filter(orientation):
    user_id = str(uuid4())

    result = _search_photos_v2(user_id, orientation=orientation)

    assert result["total"] == 0


@pytest.mark.parametrize("has_people", [True, False])
def test_search_photos_v2_applies_the_people_filter(has_people):
    user_id = str(uuid4())

    result = _search_photos_v2(user_id, has_people=has_people)

    assert result["total"] == 0


def test_search_photos_v2_applies_the_quality_and_memory_score_filters():
    user_id = str(uuid4())

    result = _search_photos_v2(user_id, min_quality_score=0.5, min_memory_score=0.2)

    assert result["total"] == 0


def test_search_photos_v2_pages_with_a_cursor():
    user_id = str(uuid4())

    result = _search_photos_v2(user_id, cursor="10", limit=30)

    assert result["total"] == 0


def test_search_photos_v2_ignores_a_broken_cursor():
    """A non-numeric cursor must not raise; it falls back to the first page."""
    user_id = str(uuid4())

    result = _search_photos_v2(user_id, cursor="not-a-number", limit=30)

    assert result["total"] == 0


def test_search_photos_v2_clamps_the_page_size():
    user_id = str(uuid4())

    result = _search_photos_v2(user_id, limit=0)

    assert result["total"] == 0
