"""主动式记忆（那年今日主动关怀）定时 job。

每天为用户生成"N 年前的今天"的主动问候消息，并把高分照片沉淀为长期记忆。
按 anchor_date 幂等；由 JobScheduler 根据 proactive_memory_schedule 触发。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from uuid import UUID

from app.core.config_manager import config_manager
from app.core.system_config import system_config
from app.crud import agent as agent_crud
from app.crud.photo import get_on_this_day_photos
from app.db.models.user import User
from app.db.session import SessionLocal

logger = logging.getLogger("app.service.jobs.proactive_memory")


def _has_llm(user_id: UUID, db) -> bool:
    """判断用户是否配置了可用的 chat 或 analysis 模型。"""
    try:
        ai = config_manager.get_user_config(user_id, db).ai
    except Exception:
        return False
    conn_id = ai.chat_connection_id or ai.analysis_connection_id
    model_name = ai.chat_model_name or ai.analysis_model_name
    return bool(conn_id and model_name)


def _template_greeting(years: int, location: str) -> str:
    """LLM 不可用时的问候语兜底模板。"""
    where = f"在{location}" if location and location != "未知地点" else ""
    return f"{years} 年前的今天，你{where}留下了这些照片，一起来重温吧～"


def _llm_greeting(db, user_id: UUID, years: int, narratives: list[str]) -> str | None:
    """用用户已配置的模型生成一句个性化问候，失败返回 None。"""
    try:
        ai = config_manager.get_user_config(user_id, db).ai
        c_id = ai.chat_connection_id or ai.analysis_connection_id
        m_name = ai.chat_model_name or ai.analysis_model_name
        connection = next((c for c in ai.connections if c.id == c_id), None)
        if not connection or not connection.enable or not connection.api_key:
            return None

        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage

        llm = ChatOpenAI(
            model=m_name,
            api_key=connection.api_key,
            base_url=connection.api_base if connection.api_base else None,
            temperature=0.8,
            timeout=30,
        )
        hint = "；".join(n for n in narratives if n)[:200]
        prompt = (
            f"这是用户 {years} 年前今天拍的照片，画面大致是：{hint}。\n"
            "请用一句温暖、自然、有温度的中文，唤起他对这天的回忆（不超过40字，不要用引号，不要罗列）。"
        )
        resp = llm.invoke([HumanMessage(content=prompt)])
        text = (resp.content or "").strip().strip('"').strip("'")
        return text or None
    except Exception as e:
        logger.warning(f"proactive_memory: 生成问候语失败，用模板兜底：{e}")
        return None


def _build_markdown(greeting: str, photo_ids: list[str]) -> str:
    """拼装可直接渲染的 Markdown：一句问候 + 若干张照片。"""
    lines = [greeting, ""]
    for pid in photo_ids:
        lines.append(f"![回忆](/api/medias/{pid}/thumbnail)")
    return "\n".join(lines)


def _generate_for_user(db, user: User, today: datetime, cfg) -> bool:
    """给单个用户生成今天的主动消息。返回是否生成了内容。"""
    anchor_date = today.strftime("%Y-%m-%d")

    # 幂等：今天已生成过则跳过
    if agent_crud.has_proactive_for_date(db, user.id, anchor_date):
        return False

    photos = get_on_this_day_photos(
        db, user_id=user.id, month=today.month, day=today.day,
        year=today.year, limit=cfg.top_photos,
    )
    if not photos:
        return False

    photo_ids = [str(p.id) for p in photos]
    narratives = [
        p.image_description.narrative
        for p in photos
        if p.image_description and p.image_description.narrative
    ]
    # 取最早那张的年份差作为"N 年前"
    oldest = min((p.photo_time for p in photos if p.photo_time), default=None)
    years = today.year - oldest.year if oldest else 0
    location = ""
    for p in photos:
        if p.metadata_info and p.metadata_info.address:
            location = p.metadata_info.address
            break

    greeting = None
    if _has_llm(user.id, db):
        greeting = _llm_greeting(db, user.id, years, narratives)
    if not greeting:
        greeting = _template_greeting(years, location)

    content = _build_markdown(greeting, photo_ids)
    agent_crud.create_proactive_message(db, user.id, content, anchor_date)

    # 沉淀高分照片为长期记忆
    try:
        from app.service.agent.memory import add_memory_anchor
        note = greeting[:30]
        for pid in photo_ids[:3]:
            add_memory_anchor(db, str(user.id), pid, note)
    except Exception as e:
        logger.warning(f"proactive_memory: 记忆沉淀失败（不影响推送）：{e}")

    logger.info(f"proactive_memory: 用户 {user.username} 生成主动消息（{anchor_date}）")
    return True


def proactive_memory_job():
    """入口：APScheduler 到点直接调用。"""
    cfg = system_config.config.proactive_memory_schedule
    started_at = time.time()
    today = datetime.now()
    db = SessionLocal()
    total = 0
    try:
        users = db.query(User).filter(User.is_active.is_(True)).all()
        logger.info(f"proactive_memory_job: 开始遍历 {len(users)} 个用户")
        for user in users:
            if time.time() - started_at > cfg.max_run_seconds:
                logger.info("proactive_memory_job: 达到单次时限，剩余用户留待下次")
                break
            try:
                if _generate_for_user(db, user, today, cfg):
                    total += 1
            except Exception as e:
                logger.warning(f"proactive_memory_job: 用户 {user.username} 处理失败：{e}")
    except Exception as e:
        logger.error(f"proactive_memory_job 顶层异常：{e}", exc_info=True)
    finally:
        elapsed = time.time() - started_at
        logger.info(f"proactive_memory_job: 完成，耗时 {elapsed:.1f}s，生成 {total} 条")
        db.close()
