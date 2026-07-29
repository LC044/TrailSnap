"""朋友圈日文案生成服务。

职责：
1. 按 (user, scope, day) 聚合当天照片素材（地点 / 人物 / 单图描述 / 标签）；
2. 组装 prompt，调用用户配置的 LLM，支持同步与 SSE 流式；
3. 通过用户级 asyncio.Lock 串行化，避免并发把本地 LLM / 外部 API 打爆；
4. 生成完成后持久化到 moment_day_captions 表。

photos.photo_time 存的是拍摄本地墙上时间（naive datetime，EXIF 原样），
因此当天聚合直接按 naive 边界 ``[day 00:00, day+1 00:00)`` 切分，无需 tz 换算；
前端也是按浏览器本地 tz 从同一份 naive 字段分组，两侧语义一致。
``tz_name`` 参数保留只为兼容既有调用签名，函数内部不再使用。
"""

from __future__ import annotations

import asyncio
import logging
import re
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
from app.service.agent.service import FixedChatOpenAI


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 思考剥离：部分模型（MiniMax / Qwen 等）会把 <think>...</think> 直接混在
# content 字符串里流式吐出，需要在跨 chunk 边界上做状态机剥离。
# ---------------------------------------------------------------------------
_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class _ThinkStripper:
    """跨 chunk 状态机，剥离 content 字符串中的 <think>...</think> 段。

    - 正常态：遇到 '<' 起进入缓冲观察，累计够 '<think>' 即切到思考态；
      若缓冲后续字符与 '<think>' 前缀不符，则整段缓冲作为正文补发。
    - 思考态：所有字符丢弃，直到检测到 '</think>' 后切回正常态。
    - flush()：流结束时把未定型的缓冲当作正文补发（若还在思考态则丢弃）。
    """

    def __init__(self) -> None:
        self._in_think = False
        self._buf = ""

    def feed(self, text: str) -> str:
        if not text:
            return ""
        out: List[str] = []
        for ch in text:
            if self._in_think:
                self._buf += ch
                # 命中闭合标签，切回正常态并清空缓冲
                if self._buf.lower().endswith(_THINK_CLOSE):
                    self._in_think = False
                    self._buf = ""
                # 缓冲过长且未见闭合，保留末尾足够识别 </think> 的窗口即可
                elif len(self._buf) > len(_THINK_CLOSE) * 4:
                    self._buf = self._buf[-len(_THINK_CLOSE):]
                continue

            # 正常态
            if self._buf:
                self._buf += ch
                lower = self._buf.lower()
                if lower == _THINK_OPEN:
                    # 命中开标签，进入思考态，丢弃缓冲
                    self._in_think = True
                    self._buf = ""
                elif _THINK_OPEN.startswith(lower):
                    # 仍是 <think> 的前缀，继续等
                    continue
                else:
                    # 前缀失配，缓冲整体判定为正文，补发
                    out.append(self._buf)
                    self._buf = ""
            elif ch == "<":
                self._buf = ch
            else:
                out.append(ch)
        return "".join(out)

    def flush(self) -> str:
        if self._in_think:
            # 思考未闭合，直接丢弃缓冲
            self._buf = ""
            return ""
        remainder = self._buf
        self._buf = ""
        return remainder


def _strip_think_blocks(text: str) -> str:
    """落库前兜底：全局清掉所有 <think>...</think>（含跨行）。"""
    if not text:
        return text
    return _THINK_BLOCK_RE.sub("", text)


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
    """返回 ``day`` 那天在 photos.photo_time 语义下的查询边界 ``[start, end)``。

    photo_time 是 naive 的墙上时间，直接构造 naive 边界即可，无需 tz 换算。
    ``tz_name`` 与函数名 ``_utc`` 均只为兼容既有调用签名保留。
    """
    _ = tz_name  # 兼容保留
    start_naive = datetime(day.year, day.month, day.day, 0, 0, 0)
    end_naive = start_naive + timedelta(days=1)
    return start_naive, end_naive


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
    # 与 app.service.agent.service.get_agent_executor 对齐：使用 FixedChatOpenAI
    # 把 OpenRouter 兼容格式下 delta.reasoning 从 content 里剥离到 additional_kwargs；
    # 不再往请求体里注入任何 "关闭思考" 兼容字段（严格网关会 400 Unknown parameter）。
    return FixedChatOpenAI(
        model=model_name,
        api_key=connection.api_key,
        base_url=connection.api_base if connection.api_base else None,
        timeout=60,
        temperature=0.8,
        streaming=streaming,
        max_completion_tokens=512,
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
        # 思考走 additional_kwargs，正文走 content，直接取即可。
        raw = response.content or ""
        if isinstance(raw, list):
            # 部分模型 content 为分段 list，只取 type=='text' 段
            raw = "".join(
                c.get("text", "") for c in raw
                if isinstance(c, dict) and c.get("type") == "text"
            )
        # 兜底剥离 content 内嵌 <think>...</think>（MiniMax / Qwen 等）
        raw = _strip_think_blocks(raw)
        caption = raw.strip().strip('"').strip()
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
    """SSE 流式生成。每 chunk 以 ``data: {...}\n\n`` 输出，结束以 ``data: [DONE]\n\n``。"""
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

        # 与 agent.service.stream_chat_with_agent 对齐的流式处理：
        #   - str content，非空 -> 正文，外发（先经 _ThinkStripper 剥离 <think> 段）
        #   - list content，type=='text' -> 正文，外发（同样经状态机剥离）
        #   - additional_kwargs.summary / type=='reasoning' -> 思考，识别但丢弃
        # 使用 llm.astream + async for，chunk 一到即 yield。
        full_caption_parts: List[str] = []
        stripper = _ThinkStripper()

        try:
            async for chunk in llm.astream(messages):
                contents = getattr(chunk, "content", None)
                additional_kwargs = getattr(chunk, "additional_kwargs", None) or {}
                if isinstance(contents, str):
                    if contents:
                        visible = stripper.feed(contents)
                        if visible:
                            full_caption_parts.append(visible)
                            yield f"data: {json.dumps({'content': visible})}\n\n"
                    elif additional_kwargs:
                        # 思考通道：识别但不外发
                        _ = additional_kwargs.get('summary') or []
                elif isinstance(contents, list):
                    for c in contents:
                        if not isinstance(c, dict):
                            continue
                        content_type = c.get('type')
                        if content_type == 'text':
                            text = c.get("text", "")
                            if text:
                                visible = stripper.feed(text)
                                if visible:
                                    full_caption_parts.append(visible)
                                    yield f"data: {json.dumps({'content': visible})}\n\n"
                        elif content_type == 'reasoning':
                            # 思考通道：识别但不外发
                            _ = c.get('summary') or []

            # 冲洗剥离器残留缓冲
            tail = stripper.flush()
            if tail:
                full_caption_parts.append(tail)
                yield f"data: {json.dumps({'content': tail})}\n\n"

            # 落库前再兜底一次，防状态机 corner case 漏切
            caption = _strip_think_blocks("".join(full_caption_parts)).strip().strip('"').strip()
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
