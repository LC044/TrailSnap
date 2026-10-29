"""2026-10-29 nightly coverage for ``app/service/agent/actions.py``.

The nightly coverage scan reported ``service/agent/actions.py`` at 84.7% with
149 uncovered lines.  The whole module is the write path of the album Agent,
so the uncovered half is almost entirely *guard* code:

* the identifier / tag / photo-count validators (``_uuid``, ``_owned_photos``,
  ``_normalize_tags``);
* the plan lifecycle helpers (``get_owned_plan``, ``list_owned_plans``,
  ``expire_stale_plans``, ``mark_plan_failed``);
* the validation branches of ``propose_album_plan``,
  ``update_repair_plan_selection``, ``reject_plan`` and ``undo_plan``.

A guard that silently accepts a bad request would let the Agent mutate a
photo library it must not touch, so each branch is asserted on the exact
error message the API surfaces to the user.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.agent import AgentSession
from app.db.models.agent_action import AgentActionPlan
from app.db.models.album import Album
from app.db.models.photo import FileType, Photo
from app.db.models.user import User
from app.service.agent import actions


pytestmark = [pytest.mark.smoke]


@pytest.fixture()
def db_ctx():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False)()
    owner, stranger = uuid.uuid4(), uuid.uuid4()
    db.add_all([
        User(id=owner, username="actions-owner", hashed_password="x"),
        User(id=stranger, username="actions-stranger", hashed_password="x"),
    ])
    session = AgentSession(id=uuid.uuid4(), user_id=owner, title="organize")
    photos = [
        Photo(id=uuid.uuid4(), owner_id=owner, filename=f"{index}.jpg",
              file_path=f"{index}.jpg", file_type=FileType.image, is_deleted=False)
        for index in range(3)
    ]
    db.add_all([session, *photos])
    db.commit()
    try:
        yield db, owner, stranger, session, photos
    finally:
        db.close()
        engine.dispose()


def _plan(db, owner, **overrides):
    payload = {
        "user_id": owner,
        "plan_type": "album_organize",
        "title": "plan",
        "status": "proposed",
        "operations": {},
        "preview": {},
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
    }
    payload.update(overrides)
    row = AgentActionPlan(**payload)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# identifiers and collection validators
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["not-a-uuid", "", None, 12345])
def test_uuid_rejects_an_unparsable_identifier(value):
    with pytest.raises(ValueError, match="无效的 ID"):
        actions._uuid(value)


def test_uuid_accepts_a_plain_string_identifier():
    assert actions._uuid(str(uuid.uuid4())) is not None


def test_owned_photos_rejects_an_empty_selection(db_ctx):
    db, owner, _, _, _ = db_ctx
    with pytest.raises(ValueError, match="照片数量必须在 1 到"):
        actions._owned_photos(db, owner, [])


def test_owned_photos_rejects_more_than_the_plan_limit(db_ctx):
    db, owner, _, _, _ = db_ctx
    distinct = [uuid.uuid4() for _ in range(actions.MAX_PLAN_PHOTOS + 1)]
    with pytest.raises(ValueError, match="照片数量必须在 1 到"):
        actions._owned_photos(db, owner, distinct)


def test_owned_photos_rejects_a_photo_owned_by_someone_else(db_ctx):
    db, owner, stranger, _, _ = db_ctx
    foreign = Photo(id=uuid.uuid4(), owner_id=stranger, filename="f.jpg",
                    file_path="f.jpg", file_type=FileType.image, is_deleted=False)
    db.add(foreign)
    db.commit()
    with pytest.raises(ValueError, match="部分照片不存在或不属于当前用户"):
        actions._owned_photos(db, owner, [foreign.id])


def test_owned_photos_deduplicates_the_requested_identifiers(db_ctx):
    db, owner, _, _, photos = db_ctx
    resolved = actions._owned_photos(db, owner, [photos[0].id, photos[0].id])
    assert [photo.id for photo in resolved] == [photos[0].id]


def test_normalize_tags_strips_blanks_and_duplicates():
    assert actions._normalize_tags([" 旅行 ", "旅行", "", "   ", "摄影"]) == ["旅行", "摄影"]


def test_normalize_tags_accepts_none():
    assert actions._normalize_tags(None) == []


def test_normalize_tags_rejects_an_overlong_tag_name():
    with pytest.raises(ValueError, match="标签名称不能超过 50 个字符"):
        actions._normalize_tags(["x" * 51])


def test_normalize_tags_rejects_more_than_the_tag_limit():
    with pytest.raises(ValueError, match="一次最多添加"):
        actions._normalize_tags([f"tag{index}" for index in range(actions.MAX_PLAN_TAGS + 1)])


# ---------------------------------------------------------------------------
# plan lifecycle helpers
# ---------------------------------------------------------------------------


def test_get_owned_plan_returns_none_for_a_malformed_identifier(db_ctx):
    db, owner, _, _, _ = db_ctx
    assert actions.get_owned_plan(db, owner, "not-a-uuid") is None


def test_get_owned_plan_returns_none_for_a_foreign_plan(db_ctx):
    db, owner, stranger, _, _ = db_ctx
    plan = _plan(db, stranger)
    assert actions.get_owned_plan(db, owner, plan.id) is None


def test_get_owned_plan_returns_the_owned_plan(db_ctx):
    db, owner, _, _, _ = db_ctx
    plan = _plan(db, owner)
    assert actions.get_owned_plan(db, owner, plan.id).id == plan.id


def test_list_owned_plans_only_returns_the_owners_plans(db_ctx):
    db, owner, stranger, _, _ = db_ctx
    mine = _plan(db, owner, title="mine")
    _plan(db, stranger, title="theirs")
    listed = actions.list_owned_plans(db, owner)
    assert [plan.id for plan in listed] == [mine.id]


def test_list_owned_plans_filters_by_status(db_ctx):
    db, owner, _, _, _ = db_ctx
    proposed = _plan(db, owner, title="proposed")
    _plan(db, owner, title="rejected", status="rejected")
    listed = actions.list_owned_plans(db, owner, status="proposed")
    assert [plan.id for plan in listed] == [proposed.id]


def test_list_owned_plans_filters_by_session(db_ctx):
    db, owner, _, session, _ = db_ctx
    scoped = _plan(db, owner, session_id=session.id)
    _plan(db, owner)
    listed = actions.list_owned_plans(db, owner, session_id=session.id)
    assert [plan.id for plan in listed] == [scoped.id]


def test_list_owned_plans_clamps_the_limit(db_ctx):
    db, owner, _, _, _ = db_ctx
    for index in range(3):
        _plan(db, owner, title=f"plan-{index}")
    assert len(actions.list_owned_plans(db, owner, limit=0)) == 1
    assert len(actions.list_owned_plans(db, owner, limit=1000)) == 3


def test_expire_stale_plans_marks_the_expired_ones(db_ctx):
    db, owner, _, _, _ = db_ctx
    stale = _plan(db, owner, expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    fresh = _plan(db, owner)
    expired_count = actions.expire_stale_plans(db, owner)
    db.refresh(stale)
    db.refresh(fresh)
    assert expired_count == 1
    assert stale.status == "expired"
    assert "已过期" in stale.error_message
    assert fresh.status == "proposed"


def test_expire_stale_plans_ignores_non_proposed_plans(db_ctx):
    db, owner, _, _, _ = db_ctx
    rejected = _plan(db, owner, status="rejected",
                     expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    assert actions.expire_stale_plans(db, owner) == 0
    db.refresh(rejected)
    assert rejected.status == "rejected"


def test_mark_plan_failed_records_the_message_and_bumps_the_attempt(db_ctx):
    db, owner, _, _, _ = db_ctx
    plan = _plan(db, owner)
    failed = actions.mark_plan_failed(db, owner, plan.id, "写入失败")
    assert failed.status == "failed"
    assert failed.attempt_count == 1
    assert failed.error_message == "写入失败"
    assert failed.failed_at is not None


def test_mark_plan_failed_leaves_an_executed_plan_untouched(db_ctx):
    db, owner, _, _, _ = db_ctx
    plan = _plan(db, owner, status="executed")
    result = actions.mark_plan_failed(db, owner, plan.id, "写入失败")
    assert result.status == "executed"


def test_mark_plan_failed_truncates_a_very_long_message(db_ctx):
    db, owner, _, _, _ = db_ctx
    plan = _plan(db, owner)
    failed = actions.mark_plan_failed(db, owner, plan.id, "x" * 5000)
    assert len(failed.error_message) == 2000


# ---------------------------------------------------------------------------
# propose_album_plan guards
# ---------------------------------------------------------------------------


def test_propose_album_plan_rejects_a_blank_name(db_ctx):
    db, owner, _, session, photos = db_ctx
    with pytest.raises(ValueError, match="相册名称不能为空"):
        actions.propose_album_plan(db, owner, session.id, "   ", None, [photos[0].id])


def test_propose_album_plan_rejects_an_overlong_name(db_ctx):
    db, owner, _, session, photos = db_ctx
    with pytest.raises(ValueError, match="相册名称不能为空"):
        actions.propose_album_plan(db, owner, session.id, "x" * 101, None, [photos[0].id])


def test_propose_album_plan_rejects_a_cover_outside_the_selection(db_ctx):
    db, owner, _, session, photos = db_ctx
    other = Photo(id=uuid.uuid4(), owner_id=owner, filename="o.jpg", file_path="o.jpg",
                  file_type=FileType.image, is_deleted=False)
    db.add(other)
    db.commit()
    with pytest.raises(ValueError, match="封面必须来自计划收录的照片"):
        actions.propose_album_plan(db, owner, session.id, "相册", None, [photos[0].id],
                                   cover_photo_id=other.id)


def test_propose_album_plan_rejects_an_unknown_album(db_ctx):
    db, owner, _, session, photos = db_ctx
    with pytest.raises(ValueError, match="目标相册不存在或无权修改"):
        actions.propose_album_plan(db, owner, session.id, "相册", None, [photos[0].id],
                                   album_id=uuid.uuid4())


def test_propose_album_plan_rejects_a_non_user_album(db_ctx):
    db, owner, _, session, photos = db_ctx
    album = Album(name="智能相册", type="smart", owner_id=owner)
    db.add(album)
    db.commit()
    with pytest.raises(ValueError, match="只支持整理普通相册"):
        actions.propose_album_plan(db, owner, session.id, "相册", None, [photos[0].id],
                                   album_id=album.id)


def test_propose_album_plan_rejects_a_foreign_session(db_ctx):
    db, owner, stranger, _, photos = db_ctx
    foreign_session = AgentSession(id=uuid.uuid4(), user_id=stranger, title="theirs")
    db.add(foreign_session)
    db.commit()
    with pytest.raises(ValueError, match="会话不存在或无权访问"):
        actions.propose_album_plan(db, owner, foreign_session.id, "相册", None, [photos[0].id])


def test_propose_album_plan_trims_the_name_and_defaults_the_cover(db_ctx):
    db, owner, _, session, photos = db_ctx
    plan = actions.propose_album_plan(db, owner, session.id, "  云南六日  ", None,
                                       [photos[0].id, photos[1].id])
    assert plan.preview["album_name"] == "云南六日"
    assert plan.preview["cover_photo_id"] == str(photos[0].id)
    assert plan.preview["mode"] == "create"


# ---------------------------------------------------------------------------
# update_repair_plan_selection guards
# ---------------------------------------------------------------------------


def test_update_repair_plan_selection_requires_an_existing_plan(db_ctx):
    db, owner, _, _, _ = db_ctx
    with pytest.raises(ValueError, match="操作计划不存在"):
        actions.update_repair_plan_selection(db, owner, uuid.uuid4(), ["a"])


def test_update_repair_plan_selection_requires_a_proposed_plan(db_ctx):
    db, owner, _, _, _ = db_ctx
    plan = _plan(db, owner, status="executed", plan_type="album_repair")
    with pytest.raises(ValueError, match="只有待确认的修复计划可以调整"):
        actions.update_repair_plan_selection(db, owner, plan.id, ["a"])


def test_update_repair_plan_selection_expires_a_stale_plan(db_ctx):
    db, owner, _, _, _ = db_ctx
    plan = _plan(db, owner, plan_type="album_repair",
                 expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    with pytest.raises(ValueError, match="已过期"):
        actions.update_repair_plan_selection(db, owner, plan.id, ["a"])
    db.refresh(plan)
    assert plan.status == "expired"


def test_update_repair_plan_selection_rejects_an_unsupported_plan_type(db_ctx):
    db, owner, _, _, _ = db_ctx
    plan = _plan(db, owner, plan_type="album_organize")
    with pytest.raises(ValueError, match="该计划不支持调整修复范围"):
        actions.update_repair_plan_selection(db, owner, plan.id, ["a"])


def test_update_repair_plan_selection_requires_at_least_one_item(db_ctx):
    db, owner, _, _, _ = db_ctx
    plan = _plan(db, owner, plan_type="album_repair", operations={"repairs": [{"id": "a"}]})
    with pytest.raises(ValueError, match="请至少选择一个修复项"):
        actions.update_repair_plan_selection(db, owner, plan.id, [])


def test_update_repair_plan_selection_rejects_an_unknown_item(db_ctx):
    db, owner, _, _, _ = db_ctx
    plan = _plan(db, owner, plan_type="album_repair", operations={"repairs": [{"id": "a"}]})
    with pytest.raises(ValueError, match="包含无效的修复项"):
        actions.update_repair_plan_selection(db, owner, plan.id, ["b"])


def test_update_repair_plan_selection_stores_the_selected_ids(db_ctx):
    db, owner, _, _, _ = db_ctx
    plan = _plan(db, owner, plan_type="album_repair",
                 operations={"repairs": [
                     {"id": "a", "album_id": "album-1"},
                     {"id": "b", "album_id": "album-1"},
                 ]})
    updated = actions.update_repair_plan_selection(db, owner, plan.id, ["b", "b"])
    assert updated.operations["selected_repair_ids"] == ["b"]
    assert updated.preview["repair_count"] == 1
    assert updated.preview["candidate_count"] == 2
    assert updated.preview["affected_album_count"] == 1


# ---------------------------------------------------------------------------
# reject_plan / undo_plan
# ---------------------------------------------------------------------------


def test_reject_plan_requires_an_existing_plan(db_ctx):
    db, owner, _, _, _ = db_ctx
    with pytest.raises(ValueError, match="操作计划不存在"):
        actions.reject_plan(db, owner, uuid.uuid4())


def test_reject_plan_requires_a_proposed_plan(db_ctx):
    db, owner, _, _, _ = db_ctx
    plan = _plan(db, owner, status="executed")
    with pytest.raises(ValueError, match="只有待确认的计划可以拒绝"):
        actions.reject_plan(db, owner, plan.id)


def test_reject_plan_records_the_rejection(db_ctx):
    db, owner, _, _, _ = db_ctx
    plan = _plan(db, owner)
    rejected = actions.reject_plan(db, owner, plan.id)
    assert rejected.status == "rejected"
    assert rejected.error_message is None


def test_undo_plan_requires_an_existing_plan(db_ctx):
    db, owner, _, _, _ = db_ctx
    with pytest.raises(ValueError, match="操作计划不存在"):
        actions.undo_plan(db, owner, uuid.uuid4())


def test_undo_plan_requires_an_executed_plan(db_ctx):
    db, owner, _, _, _ = db_ctx
    plan = _plan(db, owner, status="proposed")
    with pytest.raises(ValueError, match="只有已执行的计划可以撤销"):
        actions.undo_plan(db, owner, plan.id)


def test_undo_plan_refuses_to_undo_a_metadata_repair(db_ctx):
    db, owner, _, _, _ = db_ctx
    plan = _plan(db, owner, status="executed", plan_type="album_metadata_repair")
    with pytest.raises(ValueError, match="不可撤销"):
        actions.undo_plan(db, owner, plan.id)

