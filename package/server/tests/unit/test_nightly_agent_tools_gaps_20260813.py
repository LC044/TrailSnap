"""Nightly gap-fill tests for app.service.agent.tools.

The six LangChain tools constructed by get_agent_tools(user_id)
were at 12.3pct coverage before this file (171/195 lines missed). Each
tool opens its own SessionLocal() context manager and builds a
non-trivial SQLAlchemy chain, so we mock SessionLocal to yield a
MagicMock db plus the document / AI / path helpers, and drive the
tool functions end-to-end without touching Postgres / AI / filesystem.

Coverage targets per section 4.5 (highest priority by line count):
* search_photos_tool - happy / empty / description+embedding /
  missing PhotoMetadata fallback / filter branches / bad date fallback.
* get_photo_locations_tool - delegates to crud.location and forwards
  start_date / end_date / level.
* get_photo_tags_tool - merges tag set from desc + photo.tags;
  empty-result branch surfaces the localized message; desc.tags=None.
* get_photo_persons_tool - dedupes persons by identity_name; skips
  unnamed identities; empty branch surfaces the localized message.
* get_photo_details_tool - owner-scoped ImageDescription lookup;
  empty branch surfaces the localized message.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]

USER_ID = "user-tools-gap-001"


def _static_chain_all(value):
    """Self-referencing MagicMock chain whose .all() returns ``value``."""
    chain = MagicMock()
    chain.filter.return_value = chain
    chain.join.return_value = chain
    chain.outerjoin.return_value = chain
    chain.options.return_value = chain
    chain.limit.return_value = chain
    chain.offset.return_value = chain
    chain.order_by.return_value = chain
    chain.add_columns.return_value = chain
    chain.all.return_value = value
    chain.count.return_value = len(value) if isinstance(value, list) else 0
    return chain


def _photo(pid=None, file_path=None, **overrides):
    base = {
        "id": pid or uuid4(),
        "file_path": file_path or "C:/Photos/2026/IMG_0001.jpg",
        "photo_time": datetime(2026, 8, 1, 12, 0, 0),
        "owner_id": USER_ID,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _meta(address="West Lake", province="Zhejiang", city="Hangzhou", district="Xihu"):
    return SimpleNamespace(address=address, province=province, city=city, district=district)


def _desc(narrative="Sunset at the lake", tags=None, quality_score=0.9):
    return SimpleNamespace(
        narrative=narrative,
        tags=tags or ["scenery", "sunset"],
        quality_score=quality_score,
        memory_score=0.8,
        description="long description ...",
    )


@contextmanager
def _patch_session_local(db):
    """Replace SessionLocal() in tools.py with a CM that yields db."""
    @contextmanager
    def _factory():
        yield db
    with patch("app.service.agent.tools.SessionLocal", _factory):
        yield




def _get_tool(tools_list, name):
    """Find the tool by its ``.name`` attribute (stable identifier)."

    Searching by description is unreliable because multiple tools share keywords
    (e.g. "标签" / tag) — the ``.name`` from langchain is a stable identifier.
    """
    return next(t for t in tools_list if t.name == name)

# -------- search_photos_tool --------

def test_search_photos_tool_returns_total_and_items():
    db = MagicMock()
    photo = _photo()
    db.query.return_value = _static_chain_all([(photo, _meta(), _desc())])
    with _patch_session_local(db):
        with patch("app.service.agent.tools.get_user_roots", return_value=[("D:/Photos", "Photos")]):
            with patch("app.service.agent.tools.compute_browse_path", return_value=("2026", "IMG_0001.jpg")):
                from app.service.agent.tools import get_agent_tools
                tools_list = get_agent_tools(USER_ID)
                raw = tools_list[0].func(limit=5)
    payload = json.loads(raw)
    assert payload["total"] == 1
    assert payload["returned"] == 1
    item = payload["photos"][0]
    assert item["photo_id"] == str(photo.id)
    assert item["location"] == "West Lake"
    assert item["folder"] == "2026"
    assert item["filename"] == "IMG_0001.jpg"
    assert item["narrative"] == "Sunset at the lake"
    assert "similarity" not in item

def test_search_photos_tool_empty_results_yields_empty_payload():
    db = MagicMock()
    db.query.return_value = _static_chain_all([])
    with _patch_session_local(db):
        from app.service.agent.tools import get_agent_tools
        tools_list = get_agent_tools(USER_ID)
        raw = tools_list[0].func(location="Beijing")
    assert json.loads(raw) == {"total": 0, "returned": 0, "photos": []}

def test_search_photos_tool_with_description_attaches_similarity_score():
    db = MagicMock()
    photo = _photo()
    db.query.return_value = _static_chain_all([(photo, _meta(), _desc(), 0.2)])
    with _patch_session_local(db):
        with patch("app.service.agent.tools.get_embedding", return_value=[0.1, 0.2]) as embed_patch:
            with patch("app.service.agent.tools.get_user_roots", return_value=[]):
                with patch("app.service.agent.tools.compute_browse_path", return_value=(None, None)):
                    from app.service.agent.tools import get_agent_tools
                    tools_list = get_agent_tools(USER_ID)
                    raw = tools_list[0].func(description="sunset")
    payload = json.loads(raw)
    embed_patch.assert_called_once()
    assert payload["returned"] == 1
    assert 0.0 <= payload["photos"][0]["similarity"] <= 1.0

def test_search_photos_tool_meta_missing_falls_back_to_unknown_address():
    db = MagicMock()
    photo = _photo()
    db.query.return_value = _static_chain_all([(photo, None, _desc())])
    with _patch_session_local(db):
        with patch("app.service.agent.tools.get_user_roots", return_value=[]):
            with patch("app.service.agent.tools.compute_browse_path", return_value=(None, None)):
                from app.service.agent.tools import get_agent_tools
                tools_list = get_agent_tools(USER_ID)
                raw = tools_list[0].func(limit=10)
    payload = json.loads(raw)
    assert payload["photos"][0]["location"] == _UNKNOWN_ADDRESS
    assert payload["photos"][0]["narrative"] == "Sunset at the lake"

def test_search_photos_tool_filter_branches_exercise_chain():
    db = MagicMock()
    chain = _static_chain_all([])
    db.query.return_value = chain
    with _patch_session_local(db):
        from app.service.agent.tools import get_agent_tools
        tools_list = get_agent_tools(USER_ID)
        raw = tools_list[0].func(
            start_date="2026-08-01", end_date="2026-08-13", location="HZ",
            provinces=["ZJ"], cities=["HZ"], districts=["XH"],
            scenes=["Lake"], tags=["scenery"], persons=["Alice"], folders=["2026"],
            sort_by="memory_score",
        )
    assert json.loads(raw) == {"total": 0, "returned": 0, "photos": []}
    assert chain.filter.called
    assert chain.order_by.called
    assert chain.count.called
    assert chain.limit.called

def test_search_photos_tool_invalid_date_string_falls_back_silently():
    db = MagicMock()
    chain = _static_chain_all([])
    db.query.return_value = chain
    with _patch_session_local(db):
        from app.service.agent.tools import get_agent_tools
        tools_list = get_agent_tools(USER_ID)
        raw = tools_list[0].func(start_date="not-a-date", end_date="also-bad")
    assert json.loads(raw)["returned"] == 0

# -------- get_photo_locations_tool --------

def test_get_photo_locations_tool_delegates_to_crud_location():
    db = MagicMock()
    expected = SimpleNamespace(nodes=[1, 2, 3])
    expected.model_dump_json = lambda: '{"nodes":[1,2,3]}'
    with _patch_session_local(db):
        with patch("app.crud.location.get_timeline_nodes", return_value=expected) as crud:
            from app.service.agent.tools import get_agent_tools
            tools_list = get_agent_tools(USER_ID)
            locations_tool = _get_tool(tools_list, "get_photo_locations_tool")
            raw = locations_tool.func(level="cities")
    assert raw == '{"nodes":[1,2,3]}'
    crud.assert_called_once_with(db, USER_ID, "cities", start_date=None, end_date=None)

def test_get_photo_locations_tool_forwards_date_window():
    db = MagicMock()
    expected = SimpleNamespace(nodes=[])
    expected.model_dump_json = lambda: '{"nodes":[]}'
    with _patch_session_local(db):
        with patch("app.crud.location.get_timeline_nodes", return_value=expected) as crud:
            from app.service.agent.tools import get_agent_tools
            tools_list = get_agent_tools(USER_ID)
            locations_tool = _get_tool(tools_list, "get_photo_locations_tool")
            locations_tool.func(start_date="2026-08-01", end_date="2026-08-13")
    crud.assert_called_once_with(db, USER_ID, None, start_date="2026-08-01", end_date="2026-08-13")

# -------- get_photo_tags_tool --------

def test_get_photo_tags_tool_merges_desc_and_photo_tags():
    db = MagicMock()
    photo = _photo()
    photo.tags = [SimpleNamespace(tag_name="yolo:animal")]
    db.query.return_value = _static_chain_all([(photo, _desc(tags=["scenery", "sunset"]))])
    with _patch_session_local(db):
        from app.service.agent.tools import get_agent_tools
        tools_list = get_agent_tools(USER_ID)
        tags_tool = _get_tool(tools_list, "get_photo_tags_tool")
        parsed = json.loads(tags_tool.func(limit=10))
    assert set(parsed) >= {"scenery", "sunset", "yolo:animal"}

def test_get_photo_tags_tool_empty_returns_localized_message():
    db = MagicMock()
    db.query.return_value = _static_chain_all([])
    with _patch_session_local(db):
        from app.service.agent.tools import get_agent_tools
        tools_list = get_agent_tools(USER_ID)
        tags_tool = _get_tool(tools_list, "get_photo_tags_tool")
        raw = tags_tool.func(limit=10)
    assert raw == _NO_TAGS_MSG

def test_get_photo_tags_tool_handles_desc_tags_none():
    db = MagicMock()
    photo = _photo()
    photo.tags = [SimpleNamespace(tag_name="only-from-photo")]
    desc = SimpleNamespace(narrative="", tags=None, quality_score=0.0)
    db.query.return_value = _static_chain_all([(photo, desc)])
    with _patch_session_local(db):
        from app.service.agent.tools import get_agent_tools
        tools_list = get_agent_tools(USER_ID)
        tags_tool = _get_tool(tools_list, "get_photo_tags_tool")
        parsed = json.loads(tags_tool.func(limit=10))
    assert parsed == ["only-from-photo"]

# -------- get_photo_persons_tool --------

def _face(identity):
    return SimpleNamespace(identity=identity)

def _identity(name="Alice", description="a friend", tags=None):
    return SimpleNamespace(identity_name=name, description=description, tags=tags or ["family"])

def test_get_photo_persons_tool_dedupes_by_identity_name():
    db = MagicMock()
    p1 = _photo()
    p1.faces = [_face(_identity("Alice")), _face(_identity("Bob"))]
    p2 = _photo()
    p2.faces = [_face(_identity("Carol"))]
    db.query.return_value = _static_chain_all([p1, p2])
    with _patch_session_local(db):
        from app.service.agent.tools import get_agent_tools
        tools_list = get_agent_tools(USER_ID)
        persons_tool = _get_tool(tools_list, "get_photo_persons_tool")
        parsed = json.loads(persons_tool.func(limit=10))
    by_name = {entry["name"]: entry for entry in parsed}
    assert set(by_name) == {"Alice", "Bob", "Carol"}
    assert by_name["Alice"]["description"] == "a friend"
    assert by_name["Alice"]["tags"] == ["family"]

def test_get_photo_persons_tool_skips_unnamed_identity():
    db = MagicMock()
    p1 = _photo()
    p1.faces = [_face(None), _face(SimpleNamespace(identity_name=None)), _face(_identity("Alice"))]
    db.query.return_value = _static_chain_all([p1])
    with _patch_session_local(db):
        from app.service.agent.tools import get_agent_tools
        tools_list = get_agent_tools(USER_ID)
        persons_tool = _get_tool(tools_list, "get_photo_persons_tool")
        parsed = json.loads(persons_tool.func(limit=10))
    assert parsed == [{"name": "Alice", "description": "a friend", "tags": ["family"]}]

def test_get_photo_persons_tool_empty_returns_localized_message():
    db = MagicMock()
    db.query.return_value = _static_chain_all([])
    with _patch_session_local(db):
        from app.service.agent.tools import get_agent_tools
        tools_list = get_agent_tools(USER_ID)
        persons_tool = _get_tool(tools_list, "get_photo_persons_tool")
        raw = persons_tool.func()
    assert raw == _NO_PERSONS_MSG

# -------- get_photo_details_tool --------

def test_get_photo_details_tool_returns_owner_scoped_descriptions():
    db = MagicMock()
    pid_a = uuid4()
    pid_b = uuid4()
    desc_a = SimpleNamespace(photo_id=pid_a, description="desc A", tags=["a"], narrative="narr A")
    desc_b = SimpleNamespace(photo_id=pid_b, description="desc B", tags=["b"], narrative="narr B")
    db.query.return_value = _static_chain_all([desc_a, desc_b])
    with _patch_session_local(db):
        from app.service.agent.tools import get_agent_tools
        tools_list = get_agent_tools(USER_ID)
        details_tool = _get_tool(tools_list, "get_photo_details_tool")
        raw = details_tool.func(photo_ids=[str(pid_a), str(pid_b)])
    parsed = json.loads(raw)
    assert {p["photo_id"] for p in parsed} == {str(pid_a), str(pid_b)}
    descriptions = {p["description"] for p in parsed}
    assert descriptions == {"desc A", "desc B"}

def test_get_photo_details_tool_empty_returns_localized_message():
    db = MagicMock()
    db.query.return_value = _static_chain_all([])
    with _patch_session_local(db):
        from app.service.agent.tools import get_agent_tools
        tools_list = get_agent_tools(USER_ID)
        details_tool = _get_tool(tools_list, "get_photo_details_tool")
        raw = details_tool.func(photo_ids=[str(uuid4())])
    assert raw == _NO_DETAILS_MSG

# -------- factory sanity --------

def test_get_agent_tools_returns_non_empty_tool_list():
    from app.service.agent.tools import get_agent_tools
    tools_list = get_agent_tools(USER_ID)
    assert isinstance(tools_list, list)
    # search / locations / tags / persons / details exposed; travel is commented out.
    assert len(tools_list) == 5

def test_get_agent_tools_returns_distinct_closures_per_user():
    from app.service.agent.tools import get_agent_tools
    a = get_agent_tools("user-a")
    b = get_agent_tools("user-b")
    assert a is not b
    assert len(a) == len(b)
    assert a[0].func is not b[0].func


# -------- constants resolved at module load from tools.py --------

# These four strings are hard-coded return values in tools.py. We assert against
# them directly without translation so any future edit in tools.py fails the
# tests loudly (the comment documents where each constant comes from).
_UNKNOWN_ADDRESS = "未知地点"  # tools.py default for missing meta.address
_NO_TAGS_MSG = "没有找到照片的标签信息。"  # tools.py: empty tag list
_NO_PERSONS_MSG = "没有找到照片的人物信息。"  # tools.py: empty person list
_NO_DETAILS_MSG = "没有找到这些照片的详细信息。"  # tools.py: empty details