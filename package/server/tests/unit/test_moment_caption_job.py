"""Unit tests for moment_caption 定时任务 job。

覆盖：
- ``MomentCaptionScheduleSettings.to_cron_expression``：off/interval/weekly；
- ``_find_days_missing_caption``：能拉出"有照片但没 caption"的天并按 desc 排序（真跑一次 SQL 语法生成，验证 stmt 可执行；实际结果用 mock）；
- ``_generate_for_user``：LLM 未配置跳过、软超时提前返回、连续失败跳过；
- ``moment_caption_job``：遍历所有 is_active 用户、异常不阻断。
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.core.system_config import MomentCaptionScheduleSettings
from app.service.jobs import moment_caption as job


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


# ---------------------------------------------------------------------------
# MomentCaptionScheduleSettings.to_cron_expression
# ---------------------------------------------------------------------------

def test_cron_off_returns_none():
    s = MomentCaptionScheduleSettings(mode="off")
    assert s.to_cron_expression() is None


def test_cron_interval_generates_star_slash():
    s = MomentCaptionScheduleSettings(mode="interval", interval=30)
    assert s.to_cron_expression() == "*/30 * * * *"


def test_cron_weekly_parses_hhmm_and_weekdays():
    s = MomentCaptionScheduleSettings(
        mode="weekly", time="03:15", weekdays=[0, 2, 4]
    )
    assert s.to_cron_expression() == "15 3 * * 0,2,4"


def test_cron_weekly_invalid_time_returns_none():
    s = MomentCaptionScheduleSettings(mode="weekly", time="bad")
    assert s.to_cron_expression() is None


# ---------------------------------------------------------------------------
# _has_chat_llm
# ---------------------------------------------------------------------------

def test_has_chat_llm_true_when_chat_config_present():
    fake_cfg = SimpleNamespace(ai=SimpleNamespace(
        chat_connection_id="c1", chat_model_name="gpt-4",
        analysis_connection_id="", analysis_model_name="",
    ))
    with patch.object(job.config_manager, "get_user_config", return_value=fake_cfg):
        assert job._has_chat_llm(uuid4(), MagicMock()) is True


def test_has_chat_llm_falls_back_to_analysis_config():
    fake_cfg = SimpleNamespace(ai=SimpleNamespace(
        chat_connection_id="", chat_model_name="",
        analysis_connection_id="c2", analysis_model_name="qwen",
    ))
    with patch.object(job.config_manager, "get_user_config", return_value=fake_cfg):
        assert job._has_chat_llm(uuid4(), MagicMock()) is True


def test_has_chat_llm_false_when_nothing_configured():
    fake_cfg = SimpleNamespace(ai=SimpleNamespace(
        chat_connection_id="", chat_model_name="",
        analysis_connection_id="", analysis_model_name="",
    ))
    with patch.object(job.config_manager, "get_user_config", return_value=fake_cfg):
        assert job._has_chat_llm(uuid4(), MagicMock()) is False


def test_has_chat_llm_false_on_exception():
    with patch.object(job.config_manager, "get_user_config", side_effect=RuntimeError("boom")):
        assert job._has_chat_llm(uuid4(), MagicMock()) is False


# ---------------------------------------------------------------------------
# _generate_for_user
# ---------------------------------------------------------------------------

def _cfg(**kwargs):
    return MomentCaptionScheduleSettings(**kwargs)


def _user():
    return SimpleNamespace(id=uuid4(), username="alice")


def test_generate_for_user_skipped_when_no_llm():
    with patch.object(job, "_has_chat_llm", return_value=False):
        ok, fail, timed_out = job._generate_for_user(
            MagicMock(), _user(), started_at=0.0, cfg=_cfg(per_caption_delay_sec=0)
        )
    assert (ok, fail, timed_out) == (0, 0, False)


def test_generate_for_user_no_days_missing():
    with patch.object(job, "_has_chat_llm", return_value=True):
        with patch.object(job, "_find_days_missing_caption", return_value=[]):
            ok, fail, timed_out = job._generate_for_user(
                MagicMock(), _user(), started_at=0.0, cfg=_cfg(per_caption_delay_sec=0)
            )
    assert (ok, fail, timed_out) == (0, 0, False)


def test_generate_for_user_generates_all_days_when_within_time_budget():
    days = [date(2025, 8, 5), date(2025, 8, 4), date(2025, 8, 3)]
    with patch.object(job, "_has_chat_llm", return_value=True):
        with patch.object(job, "_find_days_missing_caption", return_value=days):
            with patch.object(job, "generate_caption_sync") as m_gen:
                with patch.object(job.asyncio, "run", return_value={"caption": "ok"}) as m_run:
                    with patch.object(job.time, "sleep"):
                        ok, fail, timed_out = job._generate_for_user(
                            MagicMock(), _user(),
                            started_at=job.time.time(),
                            cfg=_cfg(per_caption_delay_sec=0, max_run_seconds=999),
                        )
    assert (ok, fail, timed_out) == (3, 0, False)
    assert m_run.call_count == 3
    assert m_gen.call_count == 3


def test_generate_for_user_soft_timeout_returns_early():
    days = [date(2025, 8, 5), date(2025, 8, 4), date(2025, 8, 3)]
    # started_at 设成 100 秒前，max_run_seconds=1 → 立刻软超时
    with patch.object(job, "_has_chat_llm", return_value=True):
        with patch.object(job, "_find_days_missing_caption", return_value=days):
            with patch.object(job, "generate_caption_sync"):
                with patch.object(job.asyncio, "run") as m_run:
                    ok, fail, timed_out = job._generate_for_user(
                        MagicMock(), _user(),
                        started_at=job.time.time() - 100,
                        cfg=_cfg(per_caption_delay_sec=0, max_run_seconds=1),
                    )
    assert timed_out is True
    assert ok == 0
    m_run.assert_not_called()


def test_generate_for_user_consecutive_failures_break():
    days = [date(2025, 8, 5), date(2025, 8, 4), date(2025, 8, 3), date(2025, 8, 2)]
    with patch.object(job, "_has_chat_llm", return_value=True):
        with patch.object(job, "_find_days_missing_caption", return_value=days):
            with patch.object(job, "generate_caption_sync"):
                with patch.object(job.asyncio, "run", side_effect=RuntimeError("boom")):
                    with patch.object(job.time, "sleep"):
                        ok, fail, timed_out = job._generate_for_user(
                            MagicMock(), _user(),
                            started_at=job.time.time(),
                            cfg=_cfg(
                                per_caption_delay_sec=0,
                                max_run_seconds=999,
                                max_consecutive_failures_per_user=2,
                            ),
                        )
    # 连续失败 2 次后跳出，剩下的天不再尝试
    assert ok == 0
    assert fail == 2
    assert timed_out is False


def test_generate_for_user_consec_fail_reset_on_success():
    """失败后成功一次应重置连续失败计数，不会立刻跳出。"""
    days = [date(2025, 8, 5), date(2025, 8, 4), date(2025, 8, 3), date(2025, 8, 2)]
    seq = [RuntimeError("x"), {"caption": "ok"}, RuntimeError("y"), {"caption": "ok"}]
    with patch.object(job, "_has_chat_llm", return_value=True):
        with patch.object(job, "_find_days_missing_caption", return_value=days):
            with patch.object(job, "generate_caption_sync"):
                with patch.object(job.asyncio, "run", side_effect=seq):
                    with patch.object(job.time, "sleep"):
                        ok, fail, timed_out = job._generate_for_user(
                            MagicMock(), _user(),
                            started_at=job.time.time(),
                            cfg=_cfg(
                                per_caption_delay_sec=0,
                                max_run_seconds=999,
                                max_consecutive_failures_per_user=2,
                            ),
                        )
    assert ok == 2
    assert fail == 2
    assert timed_out is False


# ---------------------------------------------------------------------------
# moment_caption_job：遍历用户 + 顶层容错
# ---------------------------------------------------------------------------

def test_moment_caption_job_iterates_active_users_and_stops_on_timeout():
    u1, u2, u3 = _user(), _user(), _user()
    db_mock = MagicMock()
    db_mock.query.return_value.filter.return_value.all.return_value = [u1, u2, u3]

    calls = []

    def fake_gen_for_user(db, user, started_at, cfg):
        calls.append(user.id)
        # u2 触发软超时，u3 应当不被调用
        if user is u2:
            return 0, 0, True
        return 1, 0, False

    with patch.object(job, "SessionLocal", return_value=db_mock):
        with patch.object(job, "_generate_for_user", side_effect=fake_gen_for_user):
            job.moment_caption_job()

    assert calls == [u1.id, u2.id]


def test_moment_caption_job_swallows_top_level_exception():
    """顶层异常不应向上抛（APScheduler 里抛出会污染 job history）。"""
    db_mock = MagicMock()
    db_mock.query.side_effect = RuntimeError("db down")
    with patch.object(job, "SessionLocal", return_value=db_mock):
        # 不抛就是通过
        job.moment_caption_job()
    db_mock.close.assert_called_once()
