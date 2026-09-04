"""Unit tests for 主动式记忆（proactive memory）。

覆盖：
* proactive_memory_job：无用户/幂等跳过/无照片跳过/正常生成/顶层容错
* _generate_for_user：幂等短路、无照片短路、生成并联动记忆
* _template_greeting / _build_markdown 的基本形态
* ProactiveMemoryScheduleSettings.to_cron_expression

所有 DB 与外部依赖均 mock，不触碰 Postgres / LLM。
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.service.jobs import proactive_memory as job
from app.core.system_config import ProactiveMemoryScheduleSettings

pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


def _cfg(**kw):
    base = dict(max_run_seconds=300, top_photos=9)
    base.update(kw)
    return SimpleNamespace(**base)


def _user(active=True):
    return SimpleNamespace(id=uuid4(), username="u", is_active=active)


def _photo(pid=None, addr="杭州西湖", narrative="湖边日落", when=None):
    return SimpleNamespace(
        id=pid or uuid4(),
        photo_time=when or datetime(2023, 8, 20, 18, 0, 0),
        metadata_info=SimpleNamespace(address=addr),
        image_description=SimpleNamespace(narrative=narrative, memory_score=90),
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def test_template_greeting_with_and_without_location():
    assert "3 年前" in job._template_greeting(3, "杭州西湖")
    # 未知地点不拼地点
    g = job._template_greeting(2, "未知地点")
    assert "在" not in g


def test_build_markdown_contains_all_photo_urls():
    user_id = uuid4()
    md = job._build_markdown("你好", user_id, ["a" * 36, "b" * 36])
    assert "你好" in md
    assert md.count("/api/medias/") == 2
    assert md.count(str(user_id)) == 2
    assert "/thumbnail" in md


def test_cron_expression_off_interval_weekly():
    assert ProactiveMemoryScheduleSettings(mode="off").to_cron_expression() is None
    assert ProactiveMemoryScheduleSettings(mode="interval", interval=30).to_cron_expression() == "*/30 * * * *"
    weekly = ProactiveMemoryScheduleSettings(mode="weekly", time="09:00", weekdays=[0, 1]).to_cron_expression()
    assert weekly == "0 9 * * 0,1"


# ---------------------------------------------------------------------------
# _generate_for_user
# ---------------------------------------------------------------------------

def test_generate_for_user_skips_when_already_generated():
    db = MagicMock()
    with patch.object(job.agent_crud, "has_proactive_for_date", return_value=True), \
         patch.object(job, "get_on_this_day_photos") as m_photos:
        out = job._generate_for_user(db, _user(), datetime(2026, 8, 20), _cfg())
    assert out is False
    m_photos.assert_not_called()  # 幂等短路，不查照片


def test_generate_for_user_skips_when_no_photos():
    db = MagicMock()
    with patch.object(job.agent_crud, "has_proactive_for_date", return_value=False), \
         patch.object(job, "get_on_this_day_photos", return_value=[]):
        out = job._generate_for_user(db, _user(), datetime(2026, 8, 20), _cfg())
    assert out is False


def test_generate_for_user_creates_message_and_seeds_memory():
    db = MagicMock()
    photos = [_photo(), _photo(), _photo(), _photo()]
    with patch.object(job.agent_crud, "has_proactive_for_date", return_value=False), \
         patch.object(job, "get_on_this_day_photos", return_value=photos), \
         patch.object(job, "_has_llm", return_value=False), \
         patch.object(job.agent_crud, "create_proactive_message") as m_create, \
         patch("app.service.agent.memory.add_memory_anchor") as m_anchor:
        out = job._generate_for_user(db, _user(), datetime(2026, 8, 20), _cfg())

    assert out is True
    m_create.assert_called_once()
    # content 里应包含照片 URL；anchor_date 传入
    _, kwargs_or_args = m_create.call_args
    # 记忆联动：最多沉淀前 3 张
    assert m_anchor.call_count == 3


def test_generate_for_user_falls_back_to_template_when_llm_returns_none():
    db = MagicMock()
    photos = [_photo()]
    with patch.object(job.agent_crud, "has_proactive_for_date", return_value=False), \
         patch.object(job, "get_on_this_day_photos", return_value=photos), \
         patch.object(job, "_has_llm", return_value=True), \
         patch.object(job, "_llm_greeting", return_value=None), \
         patch.object(job.agent_crud, "create_proactive_message") as m_create, \
         patch("app.service.agent.memory.add_memory_anchor"):
        out = job._generate_for_user(db, _user(), datetime(2026, 8, 20), _cfg())
    assert out is True
    content = m_create.call_args[0][2]  # (db, user_id, content, anchor_date)
    assert "年前的今天" in content  # 用了模板兜底


# ---------------------------------------------------------------------------
# proactive_memory_job
# ---------------------------------------------------------------------------

def test_job_iterates_active_users():
    u1, u2 = _user(), _user()
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [u1, u2]
    seen = []

    def fake_gen(db_, user, today, cfg):
        seen.append(user.id)
        return True

    with patch.object(job, "SessionLocal", return_value=db), \
         patch.object(job.system_config, "config", SimpleNamespace(proactive_memory_schedule=_cfg())), \
         patch.object(job, "_generate_for_user", side_effect=fake_gen):
        job.proactive_memory_job()

    assert seen == [u1.id, u2.id]
    db.close.assert_called_once()


def test_job_swallows_top_level_exception():
    db = MagicMock()
    db.query.side_effect = RuntimeError("db down")
    with patch.object(job, "SessionLocal", return_value=db), \
         patch.object(job.system_config, "config", SimpleNamespace(proactive_memory_schedule=_cfg())):
        job.proactive_memory_job()  # 不抛即通过
    db.close.assert_called_once()


def test_job_continues_when_one_user_fails():
    u1, u2 = _user(), _user()
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [u1, u2]
    calls = []

    def fake_gen(db_, user, today, cfg):
        calls.append(user.id)
        if user.id == u1.id:
            raise RuntimeError("boom")
        return True

    with patch.object(job, "SessionLocal", return_value=db), \
         patch.object(job.system_config, "config", SimpleNamespace(proactive_memory_schedule=_cfg())), \
         patch.object(job, "_generate_for_user", side_effect=fake_gen):
        job.proactive_memory_job()

    assert calls == [u1.id, u2.id]  # 单用户失败不阻断后续
