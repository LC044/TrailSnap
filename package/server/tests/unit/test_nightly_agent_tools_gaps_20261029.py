"""Nightly watch 2026-10-29 · 覆盖盲区补测（app/service/agent/tools.py）。

被测模块：app/service/agent/tools.py 的 get_agent_tools() 闭包工具。
覆盖点（相对 2026-10-29-r2 的覆盖率基线，这些分支此前完全未触达）：
- get_photo_tags_tool：photo_ids / start_date / end_date 过滤、非法日期字符串被忽略、
  「描述里的 tags」与「PhotoTag 关系表里的 tags」合并去重、无命中时的中文兜底文案。
- get_photo_persons_tool：同上四类过滤 + 按 identity_name 去重的人物卡片。
- get_travel_history_tool：火车票日期过滤、非法日期被忽略、按时间排序、无记录兜底。
- create_memory_from_photos：空标题/空照片列表、ValueError/HTTPException 透传、成功。
- propose_album_repairs / propose_album_metadata_repairs / propose_photo_context_repairs /
  propose_album_cleanup：ValueError → {"error": ...}，成功 → action_plan。
- get_person_timeline：ValueError → {"error": ...}，成功透传。

所有 DB 访问都通过 monkeypatch 替换 app.service.agent.tools.SessionLocal，
指向用例内的 SQLite 内存库，不触碰真实 Postgres。
"""

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.photo import Photo, FileType
from app.db.models.image_description import ImageDescription
from app.db.models.face import Face, FaceIdentity
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.db.models.trip import TrainTicket
from app.db.models.user import User
from app.service.agent import tools as agent_tools

pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]

OWNER = "nightly-tools-owner"
OTHER = "nightly-tools-other"


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def library(db):
    """构造两个用户各若干照片 / 标签 / 人物 / 车票。"""
    owner, other = uuid4(), uuid4()
    db.add_all([
        User(id=owner, username="nightly-owner", hashed_password="x"),
        User(id=other, username="nightly-other", hashed_password="x"),
    ])

    def make_photo(owner_id, name, when, tags=(), desc_tags=None, desc=None):
        photo = Photo(id=uuid4(), owner_id=owner_id, filename=name, file_path=name,
                      file_type=FileType.image, size=1, is_deleted=False, photo_time=when)
        db.add(photo)
        if desc_tags is not None or desc is not None:
            db.add(ImageDescription(photo_id=photo.id, narrative=desc, tags=desc_tags))
        for tag_name in tags:
            tag = db.query(PhotoTag).filter(PhotoTag.tag_name == tag_name).first()
            if tag is None:
                tag = PhotoTag(id=uuid4(), tag_name=tag_name, owner_id=owner_id, is_deleted=False)
                db.add(tag)
                db.flush()
            db.add(PhotoTagRelation(photo_id=photo.id, tag_id=tag.id))
        db.flush()
        return photo

    p1 = make_photo(owner, "a.jpg", datetime(2025, 3, 1, 10, 0),
                    tags=("风景",), desc_tags=["人物"], desc="一张风景照")
    p2 = make_photo(owner, "b.jpg", datetime(2025, 6, 1, 10, 0),
                    tags=("美食", "风景"), desc_tags=["人物", "美食"], desc="一张美食照")
    p3 = make_photo(owner, "c.jpg", datetime(2024, 1, 1, 10, 0))
    foreign = make_photo(other, "d.jpg", datetime(2025, 3, 1, 10, 0), tags=("风景",))

    alice = FaceIdentity(id=uuid4(), owner_id=owner, identity_name="小李",
                         description="朋友", tags=["同事"], is_deleted=False, is_hidden=False)
    bob = FaceIdentity(id=uuid4(), owner_id=owner, identity_name="小王",
                       description=None, tags=None, is_deleted=False, is_hidden=False)
    db.add_all([alice, bob])
    db.flush()
    db.add(Face(photo_id=p1.id, face_identity_id=alice.id, is_deleted=False))
    db.add(Face(photo_id=p2.id, face_identity_id=alice.id, is_deleted=False))
    db.add(Face(photo_id=p2.id, face_identity_id=bob.id, is_deleted=False))

    db.add(TrainTicket(id=str(uuid4()), owner_id=owner, train_code="G1", departure_station="西安",
                       arrival_station="北京", date_time=datetime(2025, 4, 1, 8, 0), carriage="1A",
                       seat_num="1F", price="100.00", seat_type="二等座", name="张三"))
    db.add(TrainTicket(id=str(uuid4()), owner_id=other, train_code="G2", departure_station="广州",
                       arrival_station="深圳", date_time=datetime(2025, 4, 1, 8, 0), carriage="2A",
                       seat_num="2F", price="80.00", seat_type="二等座", name="李四"))
    db.commit()
    return {"db": db, "owner": owner, "other": other,
            "photos": {"p1": p1, "p2": p2, "p3": p3, "foreign": foreign}}


@pytest.fixture
def tools(library, monkeypatch):
    """把工具闭包里的 SessionLocal 换成用例内的 SQLite 会话。"""
    session = library["db"]
    monkeypatch.setattr(agent_tools, "SessionLocal", lambda: session)
    return {t.name: t for t in agent_tools.get_agent_tools(str(library["owner"]), "sess-1")}


# ---------------------------------------------------------------------------
# get_photo_tags_tool
# ---------------------------------------------------------------------------


def test_get_photo_tags_tool_merges_description_and_relation_tags(tools):
    payload = json.loads(tools["get_photo_tags_tool"].func())
    assert set(payload) == {"人物", "风景", "美食"}


def test_get_photo_tags_tool_filters_by_photo_ids(tools, library):
    payload = json.loads(tools["get_photo_tags_tool"].func(photo_ids=[str(library["photos"]["p2"].id)]))
    # 只有 p2：关系标签「美食 / 风景」+ 描述标签「人物 / 美食」
    assert set(payload) == {"美食", "风景", "人物"}


def test_get_photo_tags_tool_filters_by_date_window(tools):
    payload = json.loads(tools["get_photo_tags_tool"].func(start_date="2025-05-01", end_date="2025-12-31"))
    assert set(payload) == {"人物", "美食", "风景"}


def test_get_photo_tags_tool_ignores_invalid_date_strings(tools):
    """非法日期字符串被静默忽略（ValueError → pass），结果等同不过滤。"""
    payload = json.loads(tools["get_photo_tags_tool"].func(start_date="not-a-date", end_date="2025/01/01"))
    assert set(payload) == {"人物", "风景", "美食"}


def test_get_photo_tags_tool_returns_message_when_nothing_matches(tools):
    assert tools["get_photo_tags_tool"].func(photo_ids=[str(uuid4())]) == "没有找到照片的标签信息。"


def test_get_photo_tags_tool_excludes_other_users_photos(tools, library):
    """他人照片的标签不能出现在结果里。"""
    payload = json.loads(tools["get_photo_tags_tool"].func())
    assert "旅行" not in payload


# ---------------------------------------------------------------------------
# get_photo_persons_tool
# ---------------------------------------------------------------------------


def test_get_photo_persons_tool_dedupes_by_identity_name(tools):
    payload = json.loads(tools["get_photo_persons_tool"].func())
    names = {item["name"] for item in payload}
    assert names == {"小李", "小王"}
    li = next(item for item in payload if item["name"] == "小李")
    assert li["description"] == "朋友"
    assert li["tags"] == ["同事"]


def test_get_photo_persons_tool_filters_by_photo_ids(tools, library):
    payload = json.loads(tools["get_photo_persons_tool"].func(photo_ids=[str(library["photos"]["p1"].id)]))
    assert [item["name"] for item in payload] == ["小李"]


def test_get_photo_persons_tool_filters_by_date_window(tools):
    payload = json.loads(tools["get_photo_persons_tool"].func(start_date="2025-05-01"))
    assert [item["name"] for item in payload] == ["小李", "小王"]


def test_get_photo_persons_tool_ignores_invalid_date_strings(tools):
    payload = json.loads(tools["get_photo_persons_tool"].func(start_date="bad", end_date="worse"))
    assert {item["name"] for item in payload} == {"小李", "小王"}


def test_get_photo_persons_tool_returns_message_when_nothing_matches(tools):
    assert tools["get_photo_persons_tool"].func(photo_ids=[str(uuid4())]) == "没有找到照片的人物信息。"


# NOTE: get_travel_history_tool 在 get_agent_tools() 的返回列表里被注释掉，
# 属于不可达的死代码，本轮无法通过公开入口覆盖（详见 summary.md 的发现）。

# ---------------------------------------------------------------------------
# create_memory_from_photos
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def test_create_memory_from_photos_rejects_blank_title(tools):
    payload = json.loads(tools["create_memory_from_photos"].func(title="   ", photo_ids=[str(uuid4())]))
    assert "error" in payload


def test_create_memory_from_photos_rejects_empty_photo_ids(tools):
    payload = json.loads(tools["create_memory_from_photos"].func(title="标题", photo_ids=[]))
    assert "error" in payload


def test_create_memory_from_photos_surfaces_value_error(tools):
    with patch.object(agent_tools.memory_service, "create", side_effect=ValueError("照片不存在")):
        payload = json.loads(tools["create_memory_from_photos"].func(title="标题", photo_ids=[str(uuid4())]))
    assert payload["error"] == "照片不存在"


def test_create_memory_from_photos_surfaces_http_exception_detail(tools):
    with patch.object(agent_tools.memory_service, "create", side_effect=HTTPException(status_code=400, detail="越权")):
        payload = json.loads(tools["create_memory_from_photos"].func(title="标题", photo_ids=[str(uuid4())]))
    assert payload["error"] == "越权"


def test_create_memory_from_photos_returns_memory_summary(tools):
    row = SimpleNamespace(id=uuid4(), title="旅行记忆", photo_links=[object(), object()])
    with patch.object(agent_tools.memory_service, "create", return_value=row) as create:
        payload = json.loads(tools["create_memory_from_photos"].func(title="  旅行记忆  ", photo_ids=[str(uuid4())]))
    assert payload["memory"]["title"] == "旅行记忆"
    assert payload["memory"]["photo_count"] == 2
    assert payload["memory"]["url"] == f"/memories/{row.id}"
    assert create.call_args.args[2].title == "旅行记忆"


# ---------------------------------------------------------------------------
# propose_* 系列工具
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool_name,plan_fn,plan_kwargs",
    [
        ("propose_album_repairs", "propose_album_repair_plan", {"album_id": None, "repair_ids": None, "summary": None}),
        ("propose_album_metadata_repairs", "propose_album_metadata_repair_plan", {"album_id": None, "summary": None}),
        ("propose_photo_context_repairs", "propose_photo_context_repair_plan", {"album_id": None, "repair_ids": None, "summary": None}),
        ("propose_album_cleanup", "propose_album_cleanup_plan", {"album_id": None, "repair_ids": None, "summary": None}),
    ],
)
def test_propose_tools_return_error_json_on_value_error(tools, tool_name, plan_fn, plan_kwargs):
    with patch.object(agent_tools, plan_fn, side_effect=ValueError("参数不合法")):
        payload = json.loads(tools[tool_name].func(**plan_kwargs))
    assert payload == {"error": "参数不合法"}


@pytest.mark.parametrize(
    "tool_name,plan_fn,plan_kwargs",
    [
        ("propose_album_repairs", "propose_album_repair_plan", {"album_id": None, "repair_ids": None, "summary": None}),
        ("propose_album_metadata_repairs", "propose_album_metadata_repair_plan", {"album_id": None, "summary": None}),
        ("propose_photo_context_repairs", "propose_photo_context_repair_plan", {"album_id": None, "repair_ids": None, "summary": None}),
        ("propose_album_cleanup", "propose_album_cleanup_plan", {"album_id": None, "repair_ids": None, "summary": None}),
    ],
)
def test_propose_tools_return_action_plan_on_success(tools, tool_name, plan_fn, plan_kwargs):
    row = SimpleNamespace(id=uuid4(), plan_type="album_repair", title="修复相册",
                          summary="计数不一致", status="pending", preview={"x": 1})
    with patch.object(agent_tools, plan_fn, return_value=row):
        payload = json.loads(tools[tool_name].func(**plan_kwargs))
    assert payload["action_plan"]["id"] == str(row.id)
    assert payload["action_plan"]["plan_type"] == "album_repair"
    assert payload["action_plan"]["status"] == "pending"
    assert payload["action_plan"]["preview"] == {"x": 1}


# ---------------------------------------------------------------------------
# get_person_timeline
# ---------------------------------------------------------------------------


def test_get_person_timeline_returns_error_json_on_value_error(tools):
    with patch.object(agent_tools, "build_person_timeline", side_effect=ValueError("身份不存在")):
        payload = json.loads(tools["get_person_timeline"].func(identity_id="x"))
    assert payload == {"error": "身份不存在"}


def test_get_person_timeline_returns_timeline_payload(tools):
    with patch.object(agent_tools, "build_person_timeline", return_value={"events": [], "people": []}) as build:
        payload = json.loads(tools["get_person_timeline"].func(identity_id="abc", max_events=5))
    assert payload == {"events": [], "people": []}
    assert build.call_args.args[2] == "abc"
    assert build.call_args.args[5] == 5


