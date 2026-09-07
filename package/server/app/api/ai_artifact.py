import base64
import hashlib
import html
import mimetypes
import os
import re
import secrets
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.crud import ai_artifact as artifact_crud
from app.db.models.user import User
from app.dependencies import BaseResponse, get_db
from app.schemas.ai_artifact import AIArtifactRead, AIArtifactUpdate
from app.db.models.ai_artifact import AIArtifact
from app.api.media import _get_thumbnail_path

router = APIRouter()
MAX_PORTABLE_HTML_BYTES = 30 * 1024 * 1024
PORTABLE_CSP = "sandbox allow-scripts; default-src 'none'; base-uri 'none'; form-action 'none'; img-src data: blob:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; font-src data:; media-src data: blob:; connect-src 'none'"


def _structured_html(row: AIArtifact) -> str:
    content = row.content_json or {}
    sections = content.get("sections") if isinstance(content.get("sections"), list) else []
    blocks = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        heading = section.get("heading") or section.get("title") or section.get("location") or "旅途片段"
        body = section.get("body") or section.get("narrative") or section.get("story") or section.get("description") or ""
        photo_ids = section.get("photo_ids") if isinstance(section.get("photo_ids"), list) else []
        images = "".join(
            f'<img src="/api/medias/{row.user_id}/{html.escape(str(photo_id))}/thumbnail?size=medium" alt="旅行照片">'
            for photo_id in photo_ids
        )
        blocks.append(f"<section><h2>{html.escape(str(heading))}</h2><p>{html.escape(str(body))}</p><div class=\"photos\">{images}</div></section>")
    summary = html.escape(str(content.get("summary") or ""))
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(row.title)}</title><style>body{{max-width:960px;margin:auto;padding:32px;font:16px/1.75 system-ui;color:#1f2937}}h1{{font-size:2.2rem}}section{{margin:40px 0}}.photos{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}}img{{width:100%;aspect-ratio:1;object-fit:cover;border-radius:14px}}@media(max-width:640px){{body{{padding:20px}}}}</style></head><body><h1>{html.escape(row.title)}</h1><p>{summary}</p>{''.join(blocks)}</body></html>'''


def _portable_html(row: AIArtifact, db: Session) -> str:
    """Embed owned thumbnails and block network access for a portable export."""
    output = row.html_content or _structured_html(row)
    total_bytes = len(output.encode("utf-8"))
    for raw_id in list(dict.fromkeys(row.source_photo_ids or []))[:100]:
        try:
            photo_id = str(raw_id)
            path = _get_thumbnail_path(row.user_id, raw_id, db, "medium")
            if not os.path.isfile(path):
                path = _get_thumbnail_path(row.user_id, raw_id, db, "small")
            if not os.path.isfile(path):
                continue
            size = os.path.getsize(path)
            if total_bytes + size * 2 > MAX_PORTABLE_HTML_BYTES:
                break
            with open(path, "rb") as image_file:
                encoded = base64.b64encode(image_file.read()).decode("ascii")
            mime = mimetypes.guess_type(path)[0] or "image/jpeg"
            data_uri = f"data:{mime};base64,{encoded}"
            pattern = re.compile(
                rf"(?:https?://[^/\"'\s<>]+)?/api/medias/(?:{re.escape(str(row.user_id))}/)?{re.escape(photo_id)}/thumbnail(?:\?[^\"'\s<>)]*)?",
                re.IGNORECASE,
            )
            output = pattern.sub(data_uri, output)
            total_bytes += len(data_uri)
        except (OSError, ValueError, TypeError):
            continue
    policy = f'<meta http-equiv="Content-Security-Policy" content="{PORTABLE_CSP}"><meta name="referrer" content="no-referrer">'
    if re.search(r"<head(?:\s[^>]*)?>", output, re.IGNORECASE):
        output = re.sub(r"(<head(?:\s[^>]*)?>)", rf"\1{policy}", output, count=1, flags=re.IGNORECASE)
    else:
        output = f"<!doctype html><html><head>{policy}</head><body>{output}</body></html>"
    return output


def _share_digest(token_secret: str) -> str:
    return hashlib.sha256(token_secret.encode("utf-8")).hexdigest()


@router.get("", summary="获取 AI 作品草稿")
def list_artifacts(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = artifact_crud.list_owned(db, current_user.id, skip, limit)
    return BaseResponse.success(data=[AIArtifactRead.model_validate(row).model_dump(mode="json") for row in rows])


@router.get("/{artifact_id}", summary="获取 AI 作品草稿详情")
def get_artifact(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = artifact_crud.get_owned(db, artifact_id, current_user.id)
    if not row:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return BaseResponse.success(data=AIArtifactRead.model_validate(row).model_dump(mode="json"))


@router.get("/public/{share_token}", summary="公开查看已分享的 AI 作品", include_in_schema=False)
def get_shared_artifact(share_token: str, db: Session = Depends(get_db)):
    try:
        artifact_id, token_secret = share_token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Shared artifact not found") from exc
    row = db.query(AIArtifact).filter(AIArtifact.id == artifact_id).first()
    share = (row.html_config or {}).get("share") if row else None
    if not share or not share.get("enabled") or not secrets.compare_digest(
        str(share.get("token_hash") or ""), _share_digest(token_secret)
    ):
        raise HTTPException(status_code=404, detail="Shared artifact not found")
    return Response(_portable_html(row, db), media_type="text/html; charset=utf-8", headers={
        "Content-Security-Policy": PORTABLE_CSP,
        "Referrer-Policy": "no-referrer",
    })


@router.get("/{artifact_id}/export/html", summary="导出可离线查看的 HTML 文件")
def export_artifact_html(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = artifact_crud.get_owned(db, artifact_id, current_user.id)
    if not row:
        raise HTTPException(status_code=404, detail="Artifact not found")
    filename = f"{row.title[:80] or 'trailsnap-story'}.html"
    disposition = f"attachment; filename=trailsnap-story.html; filename*=UTF-8''{quote(filename)}"
    return Response(_portable_html(row, db), media_type="text/html; charset=utf-8", headers={
        "Content-Disposition": disposition, "Referrer-Policy": "no-referrer",
    })


@router.post("/{artifact_id}/share", summary="创建或刷新 AI 作品分享链接")
def share_artifact(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = artifact_crud.get_owned(db, artifact_id, current_user.id)
    if not row:
        raise HTTPException(status_code=404, detail="Artifact not found")
    token_secret = secrets.token_urlsafe(24)
    config = dict(row.html_config or {})
    config["share"] = {
        "enabled": True, "token_hash": _share_digest(token_secret),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    row.html_config = config
    row.version += 1
    db.commit()
    return BaseResponse.success(data={
        "share_path": f"/api/agent/artifacts/public/{row.id}.{token_secret}"
    })


@router.delete("/{artifact_id}/share", summary="撤销 AI 作品分享链接")
def revoke_artifact_share(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = artifact_crud.get_owned(db, artifact_id, current_user.id)
    if not row:
        raise HTTPException(status_code=404, detail="Artifact not found")
    config = dict(row.html_config or {})
    config.pop("share", None)
    row.html_config = config
    row.version += 1
    db.commit()
    return BaseResponse.success(data={"revoked": True})


@router.put("/{artifact_id}", summary="更新 AI 作品草稿")
def update_artifact(
    artifact_id: str,
    payload: AIArtifactUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = artifact_crud.get_owned(db, artifact_id, current_user.id)
    if not row:
        raise HTTPException(status_code=404, detail="Artifact not found")
    row = artifact_crud.update(db, row, payload)
    return BaseResponse.success(data=AIArtifactRead.model_validate(row).model_dump(mode="json"))
