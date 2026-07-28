"""朋友圈日文案生成服务。

职责：
1. 按 (user, scope, day, timezone) 聚合当天照片素材（地点 / 人物 / 单图描述 / 标签）；
2. 组装 prompt，调用用户配置的 LLM（走对话或分析连接），支持同步与 SSE 流式；
3. 通过用户级 asyncio.Lock 串行化，避免并发把本地 llama.cpp / 外部 API 打爆；
4. 生成完成后持久化到 moment_day_captions 表。

时区处理：前端按用户本地时区聚合日期，服务端也必须按用户传入的 IANA 时区把
photos.photo_time（naive UTC）归到"用户视角下的同一天"，两侧才对得上。
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone as _tz
from typing import AsyncGenerator, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9
    ZoneInfo = None  # type: ignore

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config_manager import config_manager
from app.db.models.face import Face, FaceIdentity
from app.db.models.image_description import ImageDescription
from app.db.models.photo import FileType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.scene import Scene
from app.crud import moment as moment_crud

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 用户级串行队列：同一用户同一时刻只处理 1 个生成请求，避免打爆本地 LLM。
# ---------------------------------------------------------------------------
_user_locks: Dict[str, asyncio.Lock] = {}
_user_locks_guard = asyncio.Lock()


async def _get_user_lock(user_id: str) -> asyncio.Lock:
    async with _user_locks_guard:
        lock = _user_locks.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            _user_locks[user_id] = lock
        return lock


# ---------------------------------------------------------------------------
# 时区与日期区间
# ---------------------------------------------------------------------------
def _resolve_tz(tz_name: str):
    if not tz_name:
        return _tz.utc
    if ZoneInfo is None:
        return _tz.utc
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return _tz.utc


def day_bounds_utc(day: date, tz_name: str) -> Tuple[datetime, datetime]:
    """把"用户时区下的某一天"转成 photos.photo_time 可查询的 UTC naive 边界。

    photos.photo_time 存的是 naive datetime（历史上按拍摄本地时刻写入），
    所以返回也用 naive datetime，直接与 DB 字段比较。
    """
    tz = _resolve_tz(tz_name)
    start_local = datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    # 转换到 UTC 并去掉时区信息，用于与 DB naive datetime 比较
    start_utc = start_local.astimezone(_tz.utc).replace(tzinfo=None)
    end_utc = end_local.astimezone(_tz.utc).replace(tzinfo=None)
    return start_utc, end_utc


# ---------------------------------------------------------------------------
# 素材聚合
# ---------------------------------------------------------------------------
def _fetch_day_photos(
    db: Session,
    user_id: UUID,
    day: date,
    tz_name: str,
) -> List[Photo]:
    start_utc, end_utc = day_bounds_utc(day, tz_name)
    q = (
        db.query(Photo)
        .filter(
            Photo.owner_id == user_id,
            Photo.is_deleted.is_(False),
            Photo.photo_time.isnot(None),
            Photo.photo_time >= start_utc,
            Photo.photo_time < end_utc,
        )
        .order_by(Photo.photo_time.asc())
    )
    return q.all()


def _build_materials(db: Session, photos: List[Photo]) -> Dict:
    """把当日照片聚合成给 LLM 用的素材字典。

    素材层次由粗到细：
    - locations: 该天出现过的城市/地点集合（去重）
    - people: 该天有身份的人脸姓名（去重，按出现次数排序取 Top 5）
    - descriptions: 每张照片的简短描述（首选 narrative，退化到 description）
    - tags: 全部照片标签的 Top 10
    - counts: 图片/视频数量
    """
    if not photos:
        return {"locations": [], "people": [], "descriptions": [], "tags": [], "counts": {"image": 0, "video": 0}}

    photo_ids = [p.id for p in photos]

    # locations —— 景区优先，退化到 city / district / address
    # 通过 outerjoin 让没有 scene_id 的照片也能落到 PhotoMetadata
    metas_with_scene = (
        db.query(PhotoMetadata, Scene.name)
        .outerjoin(Scene, PhotoMetadata.scene_id == Scene.id)
        .filter(PhotoMetadata.photo_id.in_(photo_ids))
        .all()
    )
    loc_set: List[str] = []
    seen_loc = set()
    for m, scene_name in metas_with_scene:
        if scene_name:
            candidate = scene_name.strip()
        else:
            parts = [p for p in (m.city, m.district) if p]
            candidate = " · ".join(parts) if parts else (m.address or "").strip()
        if candidate and candidate not in seen_loc:
            seen_loc.add(candidate)
            loc_set.append(candidate)
        if len(loc_set) >= 5:
            break

    # people
    face_rows = (
        db.query(FaceIdentity.identity_name)
        .join(Face, Face.face_identity_id == FaceIdentity.id)
        .filter(
            Face.photo_id.in_(photo_ids),
            Face.is_deleted.is_(False),
            FaceIdentity.is_deleted.is_(False),
            FaceIdentity.is_hidden.is_(False),
            FaceIdentity.identity_name.isnot(None),
        )
        .all()
    )
    people_counter: Dict[str, int] = defaultdict(int)
    for (name,) in face_rows:
        if name:
            people_counter[name] += 1
    people = [n for n, _ in sorted(people_counter.items(), key=lambda x: x[1], reverse=True)][:5]

    # descriptions & tags
    descs = (
        db.query(ImageDescription)
        .filter(ImageDescription.photo_id.in_(photo_ids))
        .all()
    )
    descriptions: List[str] = []
    tag_counter: Dict[str, int] = defaultdict(int)
    for d in descs:
        text = (d.narrative or "").strip() or (d.description or "").strip()
        if text:
            # 单条素材文本控制在 60 字内，避免 prompt 过长
            descriptions.append(text[:60])
        if isinstance(d.tags, list):
            for t in d.tags:
                if isinstance(t, str) and t:
                    tag_counter[t] += 1
    # 描述最多保留 8 条，太多反而干扰模型主线
    descriptions = descriptions[:8]
    top_tags = [t for t, _ in sorted(tag_counter.items(), key=lambda x: x[1], reverse=True)][:10]

    # counts
    image_cnt = sum(1 for p in photos if p.file_type == FileType.image)
    video_cnt = sum(1 for p in photos if p.file_type == FileType.video)

    return {
        "locations": loc_set,
        "people": people,
        "descriptions": descriptions,
        "tags": top_tags,
        "counts": {"image": image_cnt, "video": video_cnt},
    }


def _format_materials_for_prompt(day: date, materials: Dict, style: Optional[str]) -> str:
    lines: List[str] = []
    lines.append(f"日期（仅供你理解，不要写进文案）：{day.isoformat()}")
    if style:
        lines.append(f"期望风格：{style}")
    counts = materials.get("counts", {})
    if counts:
        lines.append(f"照片数量：{counts.get('image', 0)} 张图 / {counts.get('video', 0)} 个视频")
    people = materials.get("people") or []
    if people:
        lines.append("一起出现的人物：" + "、".join(people))
    locations = materials.get("locations") or []
    if locations:
        lines.append("主要地点：" + " / ".join(locations))
    tags = materials.get("tags") or []
    if tags:
        lines.append("常见标签：" + "、".join(tags))
    descs = materials.get("descriptions") or []
    if descs:
        lines.append("照片描述（可能不完整，允许忽略）：")
        for i, d in enumerate(descs, 1):
            lines.append(f"  {i}) {d}")
    else:
        lines.append("（当日照片尚未生成视觉描述，请仅基于时间、地点、人物、标签写作，避免虚构细节。）")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM 客户端构建：复用 agent 已有的连接选择规则，但独立成小函数便于其他模块共用。
# ---------------------------------------------------------------------------
def _resolve_connection_and_model(
    user_id: UUID,
    db: Session,
    connection_id: Optional[str],
    model_name: Optional[str],
    prefer: str = "chat",
):
    """选出 LLM 连接与模型名。prefer='chat' 优先对话连接，其次分析连接。"""
    user_config = config_manager.get_user_config(user_id, db)
    ai_settings = user_config.ai

    if prefer == "chat":
        default_conn = ai_settings.chat_connection_id or ai_settings.analysis_connection_id
        default_model = ai_settings.chat_model_name or ai_settings.analysis_model_name
    else:
        default_conn = ai_settings.analysis_connection_id or ai_settings.chat_connection_id
        default_model = ai_settings.analysis_model_name or ai_settings.chat_model_name

    c_id = connection_id or default_conn
    m_name = model_name or default_model

    if not c_id or not m_name:
        raise ValueError("未配置 AI 模型，请在「系统设置 -> AI相关配置」中配置连接和模型。")

    connection = next((c for c in ai_settings.connections if c.id == c_id), None)
    if connection is None:
        raise ValueError(f"未找到指定的 AI 连接配置: {c_id}，请在「系统设置」中检查。")
    if not connection.enable:
        raise ValueError(f"选中的 AI 连接已禁用: {c_id}，请在「系统设置」中启用或更换。")
    if not connection.api_key:
        raise ValueError(f"选中的 AI 连接未配置 API Key: {c_id}，请在「系统设置」中补充。")

    return connection, m_name, ai_settings.moment_day_caption_prompt


def _build_llm(connection, model_name: str, streaming: bool) -> ChatOpenAI:
    return ChatOpenAI(
        model=model_name,
        api_key=connection.api_key,
        base_url=connection.api_base if connection.api_base else None,
        timeout=60,
        temperature=0.8,
        streaming=streaming,
        max_completion_tokens=512,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        reasoning_effort="none",
    )


# ---------------------------------------------------------------------------
# 生成入口（同步 & 流式）
# ---------------------------------------------------------------------------
def _prepare_context(
    user_id: UUID,
    db: Session,
    day: date,
    tz_name: str,
    scope_type: str,
    scope_id: Optional[str],
    style: Optional[str],
    connection_id: Optional[str],
    model_name: Optional[str],
    force: bool,
) -> Tuple[Optional[str], Dict]:
    """准备生成所需的所有上下文；若命中缓存且不 force，则 cached_caption 直接返回。"""
    if scope_type != "all":
        raise ValueError("目前只支持全部照片视图（scope='all'）的朋友圈文案生成。")

    if not force:
        existing = moment_crud.get_caption(db, user_id, scope_type, scope_id, day)
        if existing is not None:
            return existing.caption, {}

    photos = _fetch_day_photos(db, user_id, day, tz_name)
    if not photos:
        raise ValueError("这一天没有照片，无法生成文案。")

    materials = _build_materials(db, photos)
    materials["_photo_count"] = len(photos)

    connection, m_name, system_prompt = _resolve_connection_and_model(
        user_id, db, connection_id, model_name, prefer="chat"
    )

    materials["_connection"] = connection
    materials["_model_name"] = m_name
    materials["_system_prompt"] = system_prompt
    materials["_user_prompt"] = _format_materials_for_prompt(day, materials, style)
    return None, materials


async def generate_caption_sync(
    user_id: UUID,
    db: Session,
    day: date,
    tz_name: str,
    scope_type: str = "all",
    scope_id: Optional[str] = None,
    style: Optional[str] = None,
    connection_id: Optional[str] = None,
    model_name: Optional[str] = None,
    force: bool = False,
) -> Dict:
    """一次性返回。命中缓存直接返回，否则生成并入库。"""
    lock = await _get_user_lock(str(user_id))
    async with lock:
        cached, materials = await asyncio.to_thread(
            _prepare_context, user_id, db, day, tz_name,
            scope_type, scope_id, style, connection_id, model_name, force,
        )
        if cached is not None:
            return {"caption": cached, "cached": True, "source": "existing"}

        llm = _build_llm(materials["_connection"], materials["_model_name"], streaming=False)
        messages = [
            SystemMessage(content=materials["_system_prompt"]),
            HumanMessage(content=materials["_user_prompt"]),
        ]
        response = await asyncio.to_thread(llm.invoke, messages)
        caption = (response.content or "").strip().strip('"').strip()
        if not caption:
            raise RuntimeError("LLM 返回为空，请稍后重试。")

        obj = await asyncio.to_thread(
            moment_crud.upsert_caption,
            db, user_id, scope_type, scope_id, day, caption, "ai",
            materials["_model_name"], materials.get("_photo_count", 0),
        )
        return {"caption": obj.caption, "cached": False, "source": "ai", "model_name": obj.model_name}


async def generate_caption_stream(
    user_id: UUID,
    db: Session,
    day: date,
    tz_name: str,
    scope_type: str = "all",
    scope_id: Optional[str] = None,
    style: Optional[str] = None,
    connection_id: Optional[str] = None,
    model_name: Optional[str] = None,
    force: bool = False,
) -> AsyncGenerator[str, None]:
    """SSE 流式生成。每 chunk 以 ``data: {...}\\n\\n`` 输出，结束以 ``data: [DONE]\\n\\n``。"""
    import json

    lock = await _get_user_lock(str(user_id))
    async with lock:
        try:
            cached, materials = await asyncio.to_thread(
                _prepare_context, user_id, db, day, tz_name,
                scope_type, scope_id, style, connection_id, model_name, force,
            )
        except ValueError as ve:
            yield f"data: {json.dumps({'error': str(ve)})}\n\n"
            yield "data: [DONE]\n\n"
            return
        except Exception as e:
            logger.error(f"prepare context failed: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': f'内部错误: {e}'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        if cached is not None:
            yield f"data: {json.dumps({'content': cached, 'cached': True})}\n\n"
            yield "data: [DONE]\n\n"
            return

        llm = _build_llm(materials["_connection"], materials["_model_name"], streaming=True)
        messages = [
            SystemMessage(content=materials["_system_prompt"]),
            HumanMessage(content=materials["_user_prompt"]),
        ]

        full_caption_parts: List[str] = []
        try:
            # ChatOpenAI.stream 是同步生成器，转到线程里 pull
            def _pull():
                return list(llm.stream(messages))

            chunks = await asyncio.to_thread(_pull)
            for chunk in chunks:
                text = getattr(chunk, "content", None)
                if isinstance(text, list):
                    for c in text:
                        if isinstance(c, dict) and c.get("type") == "text":
                            piece = c.get("text", "")
                            if piece:
                                full_caption_parts.append(piece)
                                yield f"data: {json.dumps({'content': piece})}\n\n"
                elif isinstance(text, str) and text:
                    full_caption_parts.append(text)
                    yield f"data: {json.dumps({'content': text})}\n\n"

            caption = "".join(full_caption_parts).strip().strip('"').strip()
            if not caption:
                yield f"data: {json.dumps({'error': 'LLM 返回为空，请稍后重试。'})}\n\n"
                yield "data: [DONE]\n\n"
                return

            obj = await asyncio.to_thread(
                moment_crud.upsert_caption,
                db, user_id, scope_type, scope_id, day, caption, "ai",
                materials["_model_name"], materials.get("_photo_count", 0),
            )
            yield f"data: {json.dumps({'done': True, 'caption': obj.caption, 'source': obj.source, 'updated_at': obj.updated_at.isoformat()})}\n\n"
            yield "data: [DONE]\n\n"
        except asyncio.CancelledError:
            logger.info(f"caption stream cancelled for user={user_id} day={day}")
            raise
        except Exception as e:
            logger.error(f"caption stream failed: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': f'生成失败：{e}'})}\n\n"
            yield "data: [DONE]\n\n"
