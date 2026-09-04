"""Unit tests covering 2026-08-14 nightly coverage gap scan.

Modules exercised:
* app/service/agent/tools.py -- get_agent_tools binding, plus
  get_photo_details_tool (empty + populated), get_photo_tags_tool
  (from image_description.tags vs photo.tags), get_photo_persons_tool
  (from face.identity), get_photo_locations_tool (delegates to
  app.crud.location.get_timeline_nodes), search_photos_tool (no results,
  basic happy path with mocked SessionLocal + chained query).
"""
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
    for t in get_agent_tools(user_id):
        if t.name == name:
            return t
    raise AssertionError(f"tool {name} not found")


# ===========================================================================
# app/service/agent/tools.py
# ===========================================================================


def test_get_agent_tools_returns_expected_names():
    from app.service.agent.tools import get_agent_tools
    user_id = str(uuid4())
    names = sorted(t.name for t in get_agent_tools(user_id))
    assert names == sorted([
        "get_photo_details_tool",
        "get_photo_locations_tool",
        "get_photo_persons_tool",
        "get_photo_tags_tool",
        "search_photos_tool",
        "list_skills",
        "load_skill",
        "search_photos_v2",
        "get_photo_context",
        "search_ocr",
        "get_trip_tickets",
        "get_travel_timeline",
        "view_photos",
        "create_contact_sheet",
        "select_representative_photos",
        "create_artifact_draft",
        "get_artifact_context",
        "save_artifact_html_page",
    ])


def test_get_photo_details_tool_empty():
    """If the DB returns no rows, the tool must surface a Chinese fallback."""
    user_id = str(uuid4())
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.all.return_value = []
    with patch("app.service.agent.tools.SessionLocal", _ctx(db)):
        result = _tool("get_photo_details_tool", user_id).func(photo_ids=[str(uuid4())])
    assert "没有找到" in result


def test_get_photo_details_tool_populated():
    user_id = str(uuid4())
    db = MagicMock()
    pid_a, pid_b = uuid4(), uuid4()
    desc_a = SimpleNamespace(photo_id=pid_a, description="湖面", tags=["风景"], narrative="清晨薄雾")
    desc_b = SimpleNamespace(photo_id=pid_b, description="街景", tags=[],
                              narrative=None)
    db.query.return_value.join.return_value.filter.return_value.all.return_value = [desc_a, desc_b]
    with patch("app.service.agent.tools.SessionLocal", _ctx(db)):
        out = _tool("get_photo_details_tool", user_id).func(photo_ids=[str(pid_a), str(pid_b)])
    parsed = json.loads(out)
    assert len(parsed) == 2
    assert parsed[0]["photo_id"] == str(pid_a)
    assert parsed[0]["description"] == "湖面"
    assert parsed[1]["narrative"] is None


def test_get_photo_tags_tool_empty_returns_chinese_fallback():
    user_id = str(uuid4())
    db = MagicMock()
    db.query.return_value.outerjoin.return_value.options.return_value.filter.return_value.order_by.return_value.all.return_value = []
    with patch("app.service.agent.tools.SessionLocal", _ctx(db)):
        result = _tool("get_photo_tags_tool", user_id).func()
    assert "没有找到照片的标签信息" in result


def test_get_photo_tags_tool_merges_description_and_photo_tags():
    user_id = str(uuid4())
    db = MagicMock()
    photo = SimpleNamespace(
        tags=[SimpleNamespace(tag_name="海边"), SimpleNamespace(tag_name="落日")],
    )
    desc = SimpleNamespace(tags=["云彩", "海边"])  # "海边" already present
    db.query.return_value.outerjoin.return_value.options.return_value.filter.return_value.order_by.return_value.all.return_value = [
        (photo, desc)
    ]
    with patch("app.service.agent.tools.SessionLocal", _ctx(db)):
        out = _tool("get_photo_tags_tool", user_id).func()
    parsed = json.loads(out)
    assert set(parsed) == {"海边", "云彩", "落日"}


def test_get_photo_tags_tool_handles_no_description_object():
    user_id = str(uuid4())
    db = MagicMock()
    photo = SimpleNamespace(tags=[SimpleNamespace(tag_name="人物")])
    desc = None  # outerjoined row has no description
    db.query.return_value.outerjoin.return_value.options.return_value.filter.return_value.order_by.return_value.all.return_value = [
        (photo, desc)
    ]
    with patch("app.service.agent.tools.SessionLocal", _ctx(db)):
        out = _tool("get_photo_tags_tool", user_id).func()
    parsed = json.loads(out)
    assert parsed == ["人物"]


def test_get_photo_persons_tool_empty():
    user_id = str(uuid4())
    db = MagicMock()
    db.query.return_value.options.return_value.filter.return_value.order_by.return_value.all.return_value = []
    with patch("app.service.agent.tools.SessionLocal", _ctx(db)):
        result = _tool("get_photo_persons_tool", user_id).func()
    assert "没有找到" in result


def test_get_photo_persons_tool_collects_unique_identities():
    user_id = str(uuid4())
    db = MagicMock()
    photo_a = SimpleNamespace(faces=[
        SimpleNamespace(identity=SimpleNamespace(identity_name="Alice", description="d", tags=[])),
        SimpleNamespace(identity=SimpleNamespace(identity_name="Bob", description="d", tags=[])),
    ])
    photo_b = SimpleNamespace(faces=[
        SimpleNamespace(identity=SimpleNamespace(identity_name="Alice", description="d", tags=[])),
        SimpleNamespace(identity=None),  # dangling face
    ])
    db.query.return_value.options.return_value.filter.return_value.order_by.return_value.all.return_value = [
        photo_a, photo_b
    ]
    with patch("app.service.agent.tools.SessionLocal", _ctx(db)):
        out = _tool("get_photo_persons_tool", user_id).func()
    parsed = json.loads(out)
    names = sorted(p["name"] for p in parsed)
    assert names == ['Alice', 'Bob']


def test_get_photo_locations_tool_delegates_to_location_crud():
    user_id = str(uuid4())
    db = MagicMock()
    payload = {
        "type": "default",
        "startDate": "2026-01-01",
        "endDate": "2026-12-31",
        "locationName": "上海",
        "photoCount": 42,
    }
    fake_model = SimpleNamespace(**{**payload, "model_dump_json": lambda self, **kw: json.dumps(payload, ensure_ascii=False)})
    fake_model.model_dump_json = lambda **kw: json.dumps(payload, ensure_ascii=False)
    with patch("app.crud.location.get_timeline_nodes", return_value=fake_model) as m_loc, \
         patch("app.service.agent.tools.SessionLocal", _ctx(db)):
        result = _tool("get_photo_locations_tool", user_id).func(start_date="2026-01-01")
    parsed = json.loads(result)
    assert parsed["locationName"] == "上海"
    assert parsed["photoCount"] == 42
    assert m_loc.called
    args, kwargs = m_loc.call_args
    assert args[1] == user_id


def test_search_photos_tool_no_results():
    user_id = str(uuid4())
    db = MagicMock()
    chain = db.query.return_value
    chain.outerjoin.return_value = chain
    chain.filter.return_value = chain
    chain.order_by.return_value = chain
    chain.limit.return_value = chain
    chain.all.return_value = []
    chain.order_by.return_value.count.return_value = 0
    with patch("app.service.agent.tools.SessionLocal", _ctx(db)):
        out = _tool("search_photos_tool", user_id).func(limit=10)
    parsed = json.loads(out)
    # 渐进式披露：返回结构新增 truncated / summary 字段
    assert parsed["total"] == 0
    assert parsed["returned"] == 0
    assert parsed["photos"] == []
    assert parsed["truncated"] is False


def test_search_photos_tool_basic_happy_path():
    user_id = str(uuid4())
    db = MagicMock()
    chain = db.query.return_value
    chain.outerjoin.return_value = chain
    chain.filter.return_value = chain
    chain.order_by.return_value = chain
    chain.limit.return_value = chain

    pid = uuid4()
    photo = SimpleNamespace(
        id=pid,
        file_path="/photos/2026/IMG.jpg",
        photo_time=None,  # exercise the `no time` branch
    )
    meta = SimpleNamespace(address="北京·朝阳")
    desc = SimpleNamespace(narrative=None, quality_score=None)
    chain.all.return_value = [(photo, meta, desc)]
    chain.order_by.return_value.count.return_value = 1

    with patch("app.service.agent.tools.SessionLocal", _ctx(db)), \
         patch("app.service.agent.tools.get_user_roots", return_value={"/photos": "/photos"}), \
         patch("app.service.agent.tools.compute_browse_path", return_value=("/photos/2026", "IMG.jpg")):
        out = _tool("search_photos_tool", user_id).func(limit=10)
    parsed = json.loads(out)
    assert parsed["total"] == 1
    assert parsed["returned"] == 1
    item = parsed["photos"][0]
    assert item["photo_id"] == str(pid)
    assert item["location"] == "北京·朝阳"
    assert item["folder"] == "/photos/2026"
    assert item["filename"] == "IMG.jpg"


def test_search_photos_tool_invalid_dates_are_ignored():
    user_id = str(uuid4())
    db = MagicMock()
    chain = db.query.return_value
    chain.outerjoin.return_value = chain
    chain.filter.return_value = chain
    chain.order_by.return_value = chain
    chain.limit.return_value = chain
    chain.all.return_value = []
    chain.order_by.return_value.count.return_value = 0
    with patch("app.service.agent.tools.SessionLocal", _ctx(db)):
        # Invalid date format -> still returns well-formed JSON without exception
        out = _tool("search_photos_tool", user_id).func(start_date="not-a-date", end_date="also-bad")
    parsed = json.loads(out)
    assert parsed["returned"] == 0


# ---------------------------------------------------------------------------
# 渐进式披露（降级版）：样本截断 + 九宫格保护
# ---------------------------------------------------------------------------

def _mk_photo(idx):
    return SimpleNamespace(
        id=uuid4(),
        file_path=f"/photos/IMG_{idx}.jpg",
        photo_time=None,
    )


def _search_chain(db, sample_rows, total):
    """构造 search_photos_tool 用的链式 mock：limit(N) 返回前 N 行，count 返回 total。"""
    chain = db.query.return_value
    chain.outerjoin.return_value = chain
    chain.filter.return_value = chain
    chain.order_by.return_value = chain
    chain.order_by.return_value.count.return_value = total

    def _limit(n):
        limited = MagicMock()
        limited.all.return_value = sample_rows[:n]
        return limited

    chain.limit.side_effect = _limit


def test_search_photos_tool_truncates_large_result_into_sample():
    """探索性搜索（limit 很大）：命中很多时只返回少量样本，truncated=True。"""
    user_id = str(uuid4())
    db = MagicMock()
    total = 300
    rows = [(_mk_photo(i), SimpleNamespace(address="杭州"),
             SimpleNamespace(narrative=None, quality_score=None)) for i in range(50)]
    _search_chain(db, rows, total)

    with patch("app.service.agent.tools.SessionLocal", _ctx(db)), \
         patch("app.service.agent.tools.get_user_roots", return_value={}), \
         patch("app.service.agent.tools.compute_browse_path", return_value=("f", "n")):
        out = _tool("search_photos_tool", user_id).func(limit=100)
    parsed = json.loads(out)
    assert parsed["total"] == 300
    # 大 limit 下样本被压到 SAMPLE_LIMIT(8)
    assert parsed["returned"] == 8
    assert parsed["truncated"] is True
    assert "summary" in parsed


def test_search_photos_tool_gallery_mode_returns_full_no_truncate():
    """九宫格保护：limit<=12 时按需全量返回，不截断。"""
    user_id = str(uuid4())
    db = MagicMock()
    rows = [(_mk_photo(i), SimpleNamespace(address="上海"),
             SimpleNamespace(narrative=None, quality_score=None)) for i in range(9)]
    _search_chain(db, rows, total=9)

    with patch("app.service.agent.tools.SessionLocal", _ctx(db)), \
         patch("app.service.agent.tools.get_user_roots", return_value={}), \
         patch("app.service.agent.tools.compute_browse_path", return_value=("f", "n")):
        out = _tool("search_photos_tool", user_id).func(limit=9)
    parsed = json.loads(out)
    assert parsed["returned"] == 9
    assert parsed["truncated"] is False
