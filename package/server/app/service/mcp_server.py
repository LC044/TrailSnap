"""TrailSnap's read-only Model Context Protocol surface.

The MCP transport deliberately reuses Agent Tokens instead of accepting user
JWTs. Each tool resolves the owner from the verified token and checks its own
least-privilege scope before touching the database.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlparse
from uuid import UUID

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from sqlalchemy import String, cast, func, or_

from app.crud import album as crud_album
from app.crud.agent_token import get_token_by_string
from app.db.models.face import Face, FaceIdentity
from app.db.models.image_description import ImageDescription
from app.db.models.ocr import OCR
from app.db.models.photo import Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.session import SessionLocal
from app.service.agent.album_p0 import build_person_timeline, investigate_memory_clues, photo_contexts


READ_SCOPES = frozenset({"photos:read", "albums:read", "people:read"})
READ_ONLY_ANNOTATIONS = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)


class AgentTokenVerifier(TokenVerifier):
    """Adapt TrailSnap Agent Tokens to the MCP SDK resource-server contract."""

    async def verify_token(self, token: str) -> AccessToken | None:
        if not token.startswith("ts_"):
            return None
        with SessionLocal() as db:
            agent_token = get_token_by_string(db, token)
            if not agent_token or agent_token.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
                return None
            scopes = [scope for scope in (agent_token.scopes or []) if scope in READ_SCOPES]
            return AccessToken(
                token=token,
                client_id=str(agent_token.id),
                subject=str(agent_token.user_id),
                scopes=scopes,
                expires_at=int(agent_token.expires_at.replace(tzinfo=timezone.utc).timestamp()),
                claims={"token_name": agent_token.name},
            )


def _endpoint_urls() -> tuple[str, str]:
    explicit = os.getenv("TRAILSNAP_MCP_URL", "").strip().rstrip("/")
    if explicit:
        parsed = urlparse(explicit)
        return f"{parsed.scheme}://{parsed.netloc}", f"{explicit}/"
    public = os.getenv("TRAILSNAP_PUBLIC_URL", "").strip().rstrip("/")
    if public:
        return f"{public}/api", f"{public}/api/mcp/"
    return "http://localhost:8000", "http://localhost:8000/mcp/"


def _transport_security() -> TransportSecuritySettings | None:
    """Keep localhost-safe defaults, but support the configured public host."""
    _, resource_url = _endpoint_urls()
    parsed = urlparse(resource_url)
    configured = [item.strip() for item in os.getenv("TRAILSNAP_MCP_ALLOWED_HOSTS", "").split(",") if item.strip()]
    if not os.getenv("TRAILSNAP_PUBLIC_URL", "").strip() and not os.getenv("TRAILSNAP_MCP_URL", "").strip() and not configured:
        return None
    hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    if parsed.hostname:
        hosts.extend([parsed.hostname, f"{parsed.hostname}:*"])
    hosts.extend(configured)
    origins = [f"{parsed.scheme}://{parsed.netloc}"] if parsed.scheme and parsed.netloc else []
    return TransportSecuritySettings(
        allowed_hosts=list(dict.fromkeys(hosts)),
        allowed_origins=origins,
    )


def _principal(required_scope: str) -> UUID:
    access_token = get_access_token()
    if not access_token or not access_token.subject:
        raise ToolError("无法识别 Agent Token 所属用户")
    if required_scope not in access_token.scopes:
        raise ToolError(f"Agent Token 缺少权限: {required_scope}")
    try:
        return UUID(access_token.subject)
    except ValueError as exc:  # pragma: no cover - verifier always emits UUID subjects
        raise ToolError("Agent Token 用户标识无效") from exc


def _parse_date(value: str | None, label: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ToolError(f"{label}格式必须为 YYYY-MM-DD") from exc


issuer_url, resource_url = _endpoint_urls()
mcp = MCPServer(
    "TrailSnap",
    title="TrailSnap 相册",
    description="安全查询当前用户的照片、相册、人物与回忆线索。",
    instructions="所有结果均属于 Agent Token 的所有者。候选回忆是可解释线索，不应被当作已确认事实。",
    version="0.1.0",
    token_verifier=AgentTokenVerifier(),
    auth=AuthSettings(
        issuer_url=issuer_url,
        resource_server_url=resource_url,
        required_scopes=[],
    ),
)


@mcp.tool(structured_output=True, annotations=READ_ONLY_ANNOTATIONS)
def search_photos(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    location: Optional[str] = None,
    ocr_text: Optional[str] = None,
    media_type: Optional[str] = None,
    orientation: Optional[str] = None,
    has_people: Optional[bool] = None,
    min_quality_score: Optional[float] = None,
    min_memory_score: Optional[float] = None,
    cursor: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    """多维搜索照片，返回安全元数据和缩略图 URL，不返回原始文件路径。"""
    user_id = _principal("photos:read")
    start, end = _parse_date(start_date, "开始日期"), _parse_date(end_date, "结束日期")
    if start and end and start > end:
        raise ToolError("开始日期不能晚于结束日期")
    if orientation and orientation not in {"landscape", "portrait", "square"}:
        raise ToolError("orientation 只能是 landscape、portrait 或 square")
    offset, page_size = max(cursor, 0), min(max(limit, 1), 30)

    with SessionLocal() as db:
        query = (
            db.query(Photo.id, Photo.photo_time)
            .outerjoin(PhotoMetadata, PhotoMetadata.photo_id == Photo.id)
            .outerjoin(ImageDescription, ImageDescription.photo_id == Photo.id)
            .filter(Photo.owner_id == user_id, Photo.is_deleted.is_(False))
        )
        if start:
            query = query.filter(Photo.photo_time >= start)
        if end:
            query = query.filter(Photo.photo_time < end + timedelta(days=1))
        if location:
            pattern = f"%{location}%"
            query = query.filter(or_(
                PhotoMetadata.country.ilike(pattern), PhotoMetadata.province.ilike(pattern),
                PhotoMetadata.city.ilike(pattern), PhotoMetadata.district.ilike(pattern),
                PhotoMetadata.address.ilike(pattern),
            ))
        if ocr_text:
            query = query.join(OCR, OCR.photo_id == Photo.id).filter(OCR.text.ilike(f"%{ocr_text}%"))
        if media_type:
            query = query.filter(cast(Photo.file_type, String) == media_type)
        if orientation == "landscape":
            query = query.filter(Photo.width > Photo.height)
        elif orientation == "portrait":
            query = query.filter(Photo.height > Photo.width)
        elif orientation == "square":
            query = query.filter(Photo.height == Photo.width)
        if has_people is True:
            query = query.filter(Photo.faces.any(Face.is_deleted.is_(False)))
        elif has_people is False:
            query = query.filter(~Photo.faces.any(Face.is_deleted.is_(False)))
        if min_quality_score is not None:
            query = query.filter(ImageDescription.quality_score >= min_quality_score)
        if min_memory_score is not None:
            query = query.filter(ImageDescription.memory_score >= min_memory_score)

        total = query.order_by(None).distinct().count()
        ids = [
            str(row[0]) for row in query.distinct()
            .order_by(Photo.photo_time.desc().nulls_last())
            .offset(offset).limit(page_size).all()
        ]
        return {
            "total": total,
            "returned": len(ids),
            "next_cursor": offset + len(ids) if offset + len(ids) < total else None,
            "photos": photo_contexts(db, str(user_id), ids),
        }


@mcp.tool(structured_output=True, annotations=READ_ONLY_ANNOTATIONS)
def list_albums(cursor: int = 0, limit: int = 30) -> dict[str, Any]:
    """列出当前用户可访问的相册及封面、类型和照片数量。"""
    user_id = _principal("albums:read")
    offset, page_size = max(cursor, 0), min(max(limit, 1), 100)
    with SessionLocal() as db:
        albums = crud_album.get_albums(db, skip=offset, limit=page_size + 1, user_id=user_id)
        has_more = len(albums) > page_size
        albums = albums[:page_size]
        return {
            "next_cursor": offset + page_size if has_more else None,
            "albums": [{
                "album_id": str(album.id),
                "name": album.name,
                "description": album.description,
                "type": album.type,
                "photo_count": album.num_photos or 0,
                "created_at": album.create_time.isoformat() if album.create_time else None,
                "cover_photo_id": str(album.cover_id) if album.cover_id else None,
                "cover_thumbnail_url": f"/api/medias/{album.cover_id}/thumbnail" if album.cover_id else None,
                "shared_with_me": album.owner_id != user_id,
            } for album in albums],
        }


@mcp.tool(structured_output=True, annotations=READ_ONLY_ANNOTATIONS)
def list_people(cursor: int = 0, limit: int = 30) -> dict[str, Any]:
    """列出当前用户的可见人物及其照片数量，供人物时间线选择 identity_id。"""
    user_id = _principal("people:read")
    offset, page_size = max(cursor, 0), min(max(limit, 1), 100)
    with SessionLocal() as db:
        counts = (
            db.query(Face.face_identity_id, func.count(func.distinct(Face.photo_id)).label("photo_count"))
            .join(Photo, Photo.id == Face.photo_id)
            .filter(Photo.owner_id == user_id, Photo.is_deleted.is_(False), Face.is_deleted.is_(False))
            .group_by(Face.face_identity_id).subquery()
        )
        query = (
            db.query(FaceIdentity, func.coalesce(counts.c.photo_count, 0))
            .outerjoin(counts, counts.c.face_identity_id == FaceIdentity.id)
            .filter(
                FaceIdentity.owner_id == user_id,
                FaceIdentity.is_deleted.is_(False),
                FaceIdentity.is_hidden.is_(False),
            )
            .order_by(func.coalesce(counts.c.photo_count, 0).desc(), FaceIdentity.identity_name)
        )
        total = query.order_by(None).count()
        rows = query.offset(offset).limit(page_size).all()
        return {
            "total": total,
            "next_cursor": offset + len(rows) if offset + len(rows) < total else None,
            "people": [{
                "identity_id": str(identity.id), "name": identity.identity_name,
                "description": identity.description, "tags": identity.tags or [],
                "photo_count": count,
                "default_face_id": identity.default_face_id,
            } for identity, count in rows],
        }


@mcp.tool(structured_output=True, annotations=READ_ONLY_ANNOTATIONS)
def investigate_memory(
    query_text: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    locations: Optional[list[str]] = None,
    persons: Optional[list[str]] = None,
    text_terms: Optional[list[str]] = None,
    semantic_photo_ids: Optional[list[str]] = None,
    max_events: int = 8,
) -> dict[str, Any]:
    """融合日期、地点、人物、OCR/描述文字等模糊线索，返回可解释的候选回忆事件。"""
    user_id = _principal("photos:read")
    with SessionLocal() as db:
        try:
            return investigate_memory_clues(
                db, str(user_id), query_text, start_date, end_date, locations,
                persons, text_terms, semantic_photo_ids, max_events,
            )
        except ValueError as exc:
            raise ToolError(str(exc)) from exc


@mcp.tool(structured_output=True, annotations=READ_ONLY_ANNOTATIONS)
def get_person_timeline(
    identity_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_events: int = 20,
) -> dict[str, Any]:
    """按人物聚合年份、事件、地点、同行者和代表照片，生成只读人物时间线。"""
    user_id = _principal("people:read")
    with SessionLocal() as db:
        try:
            return build_person_timeline(db, str(user_id), identity_id, start_date, end_date, max_events)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc


mcp_http_app = mcp.streamable_http_app(
    streamable_http_path="/",
    json_response=True,
    stateless_http=True,
    transport_security=_transport_security(),
)
