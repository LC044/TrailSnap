"""定时批量生成"朋友圈日文案" job。

遍历所有 is_active 用户，拉出"有照片但没 caption"的日期，依次调
``generate_caption_sync``（force=False 天然幂等）。三层软保护：单次总时限、
单天 sleep、单用户连续失败跳过。调度由 ``JobScheduler`` 根据
``system_config.moment_caption_schedule`` 触发；``mode='off'`` 时不注册。
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import date
from typing import List
from uuid import UUID

from sqlalchemy import cast, Date, select

from app.core.config_manager import config_manager
from app.core.system_config import system_config
from app.db.models.moment_day_caption import MomentDayCaption
from app.db.models.photo import Photo
from app.db.models.user import User
from app.db.session import SessionLocal
from app.service.moment.day_caption_service import generate_caption_sync

logger = logging.getLogger("app.service.jobs.moment_caption")


def _has_chat_llm(user_id: UUID, db) -> bool:
    """判断用户是否配置了可用于文案生成的 chat 或 analysis 连接与模型。"""
    try:
        user_config = config_manager.get_user_config(user_id, db)
    except Exception as e:
        logger.warning(f"moment_caption_job: 读取用户 {user_id} 配置失败：{e}")
        return False
    ai = user_config.ai
    conn_id = ai.chat_connection_id or ai.analysis_connection_id
    model_name = ai.chat_model_name or ai.analysis_model_name
    return bool(conn_id and model_name)


def _find_days_missing_caption(db, user_id: UUID) -> List[date]:
    """SQL 一把梭：拉用户所有"有照片但没 caption"的日期，最近的排在前面。"""
    day_expr = cast(Photo.photo_time, Date)
    existing_days = (
        select(MomentDayCaption.day)
        .where(
            MomentDayCaption.user_id == user_id,
            MomentDayCaption.scope_type == "all",
            MomentDayCaption.scope_id.is_(None),
        )
    )
    stmt = (
        select(day_expr)
        .where(
            Photo.owner_id == user_id,
            Photo.is_deleted.is_(False),
            Photo.photo_time.isnot(None),
            day_expr.notin_(existing_days),
        )
        .group_by(day_expr)
        .order_by(day_expr.desc())
    )
    rows = db.execute(stmt).all()
    return [r[0] for r in rows]


def _generate_for_user(
    db,
    user: User,
    started_at: float,
    cfg,
) -> tuple[int, int, bool]:
    """给单个用户跑一轮生成。返回 (成功数, 失败数, 是否因软超时提前退出)。"""
    if not _has_chat_llm(user.id, db):
        logger.info(f"moment_caption_job: 用户 {user.username} 未配置 LLM，跳过")
        return 0, 0, False

    days = _find_days_missing_caption(db, user.id)
    if not days:
        return 0, 0, False

    logger.info(
        f"moment_caption_job: 用户 {user.username} 待生成 {len(days)} 天"
    )
    ok, fail, consec_fail = 0, 0, 0
    for day in days:
        if time.time() - started_at > cfg.max_run_seconds:
            logger.info(
                f"moment_caption_job: 达到单次 {cfg.max_run_seconds}s 时限，"
                f"用户 {user.username} 剩余 {len(days) - ok - fail} 天留待下次"
            )
            return ok, fail, True

        try:
            asyncio.run(
                generate_caption_sync(
                    user_id=user.id,
                    db=db,
                    day=day,
                    tz_name="Asia/Shanghai",
                    scope_type="all",
                )
            )
            ok += 1
            consec_fail = 0
        except Exception as e:
            fail += 1
            consec_fail += 1
            logger.warning(
                f"moment_caption_job: 用户 {user.username} 生成 {day} 失败：{e}"
            )
            if consec_fail >= cfg.max_consecutive_failures_per_user:
                logger.warning(
                    f"moment_caption_job: 用户 {user.username} 连续失败 "
                    f"{consec_fail} 次，跳过"
                )
                break

        if cfg.per_caption_delay_sec > 0:
            time.sleep(cfg.per_caption_delay_sec)

    return ok, fail, False


def moment_caption_job():
    """入口：APScheduler 到点直接调用。"""
    cfg = system_config.config.moment_caption_schedule
    started_at = time.time()
    db = SessionLocal()
    total_ok = total_fail = 0
    try:
        users = db.query(User).filter(User.is_active.is_(True)).all()
        logger.info(f"moment_caption_job: 开始遍历 {len(users)} 个用户")
        for user in users:
            ok, fail, timed_out = _generate_for_user(db, user, started_at, cfg)
            total_ok += ok
            total_fail += fail
            if timed_out:
                break
    except Exception as e:
        logger.error(f"moment_caption_job 顶层异常：{e}", exc_info=True)
    finally:
        elapsed = time.time() - started_at
        logger.info(
            f"moment_caption_job: 完成，耗时 {elapsed:.1f}s，"
            f"成功 {total_ok} 天，失败 {total_fail} 天"
        )
        db.close()
