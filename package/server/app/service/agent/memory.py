"""
照片即记忆（Photo-anchored Memory）—— 抗幻觉的长期记忆实现。

记忆锚定在真实照片上，每条记忆携带 photo_id，注入模型前强制校验照片有效性。
记忆锚点存放在"记忆专用会话"下一条 memory 消息的 content_ext 中，不新增表/字段。
"""
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models.photo import Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.image_description import ImageDescription
from app.db.models.image_vector import ImageVector
from app.crud import agent as agent_crud

logger = logging.getLogger(__name__)

# 记忆锚点数量上限，超出后淘汰最旧的
MAX_MEMORY_ANCHORS = 30
# 只有 memory_score 达到该阈值的照片才能成为记忆锚点
MIN_MEMORY_SCORE = 60.0
MEMORY_VERSION = 1
# 语义检索时注入 system prompt 的记忆条数上限
MEMORY_TOP_K = 6
# 照片向量与查询向量的 cosine 距离超过该值视为不相关，直接过滤
MEMORY_MAX_DISTANCE = 0.9


def _empty_memory() -> Dict[str, Any]:
    return {"version": MEMORY_VERSION, "anchors": []}


def load_raw_memory(db: Session, user_id: str) -> Dict[str, Any]:
    """读取用户原始记忆锚点（未校验有效性）。"""
    msg = agent_crud.get_memory_message(db, user_id)
    if not msg or not msg.content_ext:
        return _empty_memory()
    ext = msg.content_ext
    if not isinstance(ext, dict) or "anchors" not in ext:
        return _empty_memory()
    return ext


def get_valid_memory_anchors(db: Session, user_id: str) -> List[Dict[str, Any]]:
    """
    抗幻觉核心：读取记忆锚点，并逐条校验其指向的照片仍然有效。
    校验规则：photo_id 存在 + owner 匹配当前用户 + 未被软删除。
    无效锚点（照片被删/不属于该用户）会被自动剔除，且顺手回写清理后的记忆。
    """
    raw = load_raw_memory(db, user_id)
    anchors = raw.get("anchors", [])
    if not anchors:
        return []

    photo_ids = [a.get("photo_id") for a in anchors if a.get("photo_id")]
    if not photo_ids:
        return []

    # 一次性查出仍然有效的 photo_id（存在 + owner 匹配 + 未软删）
    valid_rows = (
        db.query(Photo.id)
        .filter(
            Photo.id.in_(photo_ids),
            Photo.owner_id == user_id,
            Photo.is_deleted == False,  # noqa: E712
        )
        .all()
    )
    valid_ids = {str(r[0]) for r in valid_rows}

    valid_anchors = [a for a in anchors if a.get("photo_id") in valid_ids]

    # 发现死引用则回写清理后的记忆（自愈）
    if len(valid_anchors) != len(anchors):
        raw["anchors"] = valid_anchors
        try:
            agent_crud.upsert_memory_message(db, user_id, raw)
        except Exception as e:
            logger.warning(f"回写清理后的记忆失败：{e}")

    return valid_anchors


def get_relevant_memory_anchors(
    db: Session, user_id: str, user_input: str, top_k: int = MEMORY_TOP_K
) -> List[Dict[str, Any]]:
    """
    语义记忆检索：用当前用户输入的文本向量，在记忆锚点对应的照片向量（CLIP，跨模态）中
    检索最相关的 top-k 条记忆。

    实现要点（不改动数据库）：
      - 记忆锚点本身没有独立向量，但每条锚点携带 photo_id；
      - image_vectors 表中存有每张照片的 CLIP embedding；
      - CLIP 文本/图像共享同一向量空间，因此可用文本 query 直接与照片向量做 cosine 检索。

    任何异常（如 embedding 服务不可用、无向量数据）都回退到"全部有效锚点"，保证对话不受影响。
    """
    anchors = get_valid_memory_anchors(db, user_id)
    if not anchors:
        return []

    # query 为空或锚点数不多时，检索无意义，直接返回全部
    if not user_input or not user_input.strip() or len(anchors) <= top_k:
        return anchors

    try:
        from app.utils.embedding import get_embedding

        anchor_by_pid = {a.get("photo_id"): a for a in anchors if a.get("photo_id")}
        photo_ids = list(anchor_by_pid.keys())
        if not photo_ids:
            return anchors

        embedding = get_embedding(user_input, user_id, db)
        distance = ImageVector.embedding.cosine_distance(embedding)

        rows = (
            db.query(ImageVector.photo_id, distance.label("distance"))
            .filter(ImageVector.photo_id.in_(photo_ids))
            .order_by(distance.asc())
            .limit(top_k)
            .all()
        )

        relevant: List[Dict[str, Any]] = []
        for photo_id, dist in rows:
            if dist is not None and float(dist) > MEMORY_MAX_DISTANCE:
                continue
            anchor = anchor_by_pid.get(str(photo_id))
            if anchor:
                relevant.append(anchor)

        # 检索命中为空（全部被距离阈值过滤）时，回退到时间上最近的若干条，避免无记忆可用
        if not relevant:
            return anchors[-top_k:]
        return relevant
    except Exception as e:
        logger.warning(f"语义记忆检索失败，回退到全部有效锚点：{e}")
        return anchors


def build_memory_prompt(db: Session, user_id: str, user_input: Optional[str] = None) -> str:
    """
    生成注入 system prompt 的记忆片段，无有效记忆时返回空字符串。

    传入 user_input 时启用语义检索，仅注入与当前问题最相关的若干条记忆（节省上下文）；
    不传时退化为注入全部有效锚点（兼容旧行为）。
    """
    if user_input:
        anchors = get_relevant_memory_anchors(db, user_id, user_input)
    else:
        anchors = get_valid_memory_anchors(db, user_id)
    if not anchors:
        return ""

    lines = [
        "\n【关于这位用户的长期记忆】",
        "以下是你在过往对话中记住的、与这位用户相关的重要回忆。每条记忆都对应一张真实存在的照片（photo_id 可信，可直接用于展示）。",
        "当用户提到相关话题时，你可以自然地引用这些回忆；但不要凭空编造未列出的记忆。",
    ]
    for a in anchors:
        note = a.get("note", "").strip()
        pid = a.get("photo_id")
        when = a.get("photo_time") or "时间未知"
        where = a.get("location") or "地点未知"
        lines.append(f"- {note}（时间：{when}；地点：{where}；photo_id：{pid}）")
    return "\n".join(lines) + "\n"


def _fetch_photo_snapshot(db: Session, user_id: str, photo_id: str) -> Optional[Dict[str, Any]]:
    """校验并抓取一张照片的元数据快照。"""
    row = (
        db.query(Photo, PhotoMetadata, ImageDescription)
        .outerjoin(PhotoMetadata, Photo.id == PhotoMetadata.photo_id)
        .outerjoin(ImageDescription, Photo.id == ImageDescription.photo_id)
        .filter(
            Photo.id == photo_id,
            Photo.owner_id == user_id,
            Photo.is_deleted == False,  # noqa: E712
        )
        .first()
    )
    if not row:
        return None
    photo, meta, desc = row
    return {
        "photo_id": str(photo.id),
        "photo_time": photo.photo_time.strftime("%Y-%m-%d %H:%M:%S") if photo.photo_time else None,
        "location": (meta.address if meta else None) or "未知地点",
        "memory_score": desc.memory_score if desc else None,
        "narrative": desc.narrative if desc else None,
    }


def add_memory_anchor(
    db: Session, user_id: str, photo_id: str, note: str
) -> bool:
    """新增一条记忆锚点：校验照片有效性与 memory_score 门槛，去重并按上限淘汰最旧锚点。"""
    snapshot = _fetch_photo_snapshot(db, user_id, photo_id)
    if not snapshot:
        return False

    # memory_score 未达门槛（含 None）则拒绝
    score = snapshot.get("memory_score")
    if score is None or score < MIN_MEMORY_SCORE:
        return False

    raw = load_raw_memory(db, user_id)
    anchors = raw.get("anchors", [])

    # 去重：同一张照片只保留最新一条
    anchors = [a for a in anchors if a.get("photo_id") != photo_id]

    anchors.append({
        "photo_id": photo_id,
        "note": note.strip(),
        "photo_time": snapshot.get("photo_time"),
        "location": snapshot.get("location"),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })

    # 超上限淘汰最旧的锚点
    if len(anchors) > MAX_MEMORY_ANCHORS:
        anchors = anchors[-MAX_MEMORY_ANCHORS:]

    raw["anchors"] = anchors
    raw["version"] = MEMORY_VERSION
    agent_crud.upsert_memory_message(db, user_id, raw)
    return True


def _get_extraction_llm(db: Session, user_id: str):
    """复用用户已配置的分析模型做记忆抽取，返回 (llm, ok)。"""
    from app.core.config_manager import config_manager
    from langchain_openai import ChatOpenAI

    user_config = config_manager.get_user_config(user_id, db)
    ai_settings = user_config.ai
    c_id = ai_settings.analysis_connection_id
    m_name = ai_settings.analysis_model_name
    if not c_id or not m_name:
        return None, False
    connection = next((c for c in ai_settings.connections if c.id == c_id), None)
    if not connection or not connection.enable or not connection.api_key:
        return None, False
    llm = ChatOpenAI(
        model=m_name,
        api_key=connection.api_key,
        base_url=connection.api_base if connection.api_base else None,
        temperature=0.2,  # 抽取需稳定，用低温度
        timeout=30,
    )
    return llm, True


_EXTRACTION_PROMPT = """你是一个记忆抽取器。请阅读用户与相册助手的一轮对话，判断其中是否出现了"值得长期记住、且与某张具体照片强相关"的重要回忆。

判定标准（从严）：
- 只有当对话明确指向某张具体照片（有 photo_id）、且承载了值得日后回忆的情感或事件（如重要的人、特殊的地点、纪念性时刻）时，才抽取。
- 普通的检索、闲聊、笼统的多张照片罗列，一律不抽取。
- 宁缺毋滥，不确定就不抽取。

对话中出现的照片会以 `photo_id: <uuid>` 的形式给出。你只能引用这些真实出现过的 photo_id，绝不能编造。

请严格输出 JSON（不要额外解释），格式：
{{"memories": [{{"photo_id": "对话中真实出现的uuid", "note": "一句话记忆描述（不超过30字）"}}]}}
如果没有值得记住的内容，输出：{{"memories": []}}

对话内容：
{conversation}
"""


def extract_and_store_memory_task(
    user_id: str,
    user_input: str,
    assistant_reply: str,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
):
    """后台任务：从本轮对话抽取记忆锚点并持久化，独立 db session，失败不影响主流程。"""
    try:
        # 收集本轮真实出现过的 photo_id 作为抽取白名单
        appeared_ids = _collect_photo_ids(assistant_reply, tool_calls)
        if not appeared_ids:
            return

        conversation = (
            f"用户：{user_input}\n"
            f"助手：{assistant_reply}\n"
            f"本轮对话中出现的照片：\n"
            + "\n".join(f"photo_id: {pid}" for pid in appeared_ids)
        )

        with SessionLocal() as db:
            llm, ok = _get_extraction_llm(db, user_id)
            if not ok:
                return

            from langchain_core.messages import HumanMessage
            resp = llm.invoke([
                HumanMessage(content=_EXTRACTION_PROMPT.format(conversation=conversation))
            ])
            content = (resp.content or "").strip()
            memories = _parse_extraction_result(content)
            if not memories:
                return

            for m in memories:
                pid = m.get("photo_id")
                note = m.get("note", "")
                # 防幻觉：photo_id 必须真实出现在本轮对话中
                if not pid or pid not in appeared_ids or not note:
                    continue
                add_memory_anchor(db, user_id, pid, note)
    except Exception as e:
        logger.warning(f"记忆抽取任务失败（不影响主流程）：{e}")


def _collect_photo_ids(assistant_reply: str, tool_calls: Optional[List[Dict[str, Any]]]) -> set:
    """从助手回复的图片 URL 与工具返回中收集真实出现过的 photo_id。"""
    import re
    ids = set()
    if assistant_reply:
        for m in re.finditer(r"/medias/([a-f0-9\-]{36})", assistant_reply, re.IGNORECASE):
            ids.add(m.group(1))
    if tool_calls:
        for tc in tool_calls:
            ret = tc.get("tool_return")
            if not ret:
                continue
            text = ret if isinstance(ret, str) else json.dumps(ret, ensure_ascii=False)
            for m in re.finditer(r'"photo_id"\s*:\s*"([a-f0-9\-]{36})"', text, re.IGNORECASE):
                ids.add(m.group(1))
    return ids


def remove_memory_anchor(db: Session, user_id: str, photo_id: str) -> bool:
    """删除指定 photo_id 的记忆锚点，返回是否删除了内容。用户可借此手动遗忘某条记忆。"""
    raw = load_raw_memory(db, user_id)
    anchors = raw.get("anchors", [])
    new_anchors = [a for a in anchors if a.get("photo_id") != photo_id]
    if len(new_anchors) == len(anchors):
        return False
    raw["anchors"] = new_anchors
    agent_crud.upsert_memory_message(db, user_id, raw)
    return True


def _parse_extraction_result(content: str) -> List[Dict[str, Any]]:
    """稳健解析抽取模型输出的 JSON（容忍 ```json 包裹等情况）。"""
    if not content:
        return []
    text = content.strip()
    # 去掉可能的代码块围栏
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    # 尝试截取第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
    try:
        data = json.loads(text)
        mems = data.get("memories", [])
        return mems if isinstance(mems, list) else []
    except Exception:
        return []
