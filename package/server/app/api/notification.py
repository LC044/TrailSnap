"""全局通知路由。

- `GET /notifications/events`：通用 SSE 通道，承载 task.* live 事件
  （由 TaskManager 桥接进来，不落库）与 notification.* 落库通知。
- `GET /notifications`、`/unread-count`、`POST /{id}/read`、`/read-all`：
  通知收件箱 CRUD，按 user_id 隔离。
- `POST /notifications`：管理员创建通知（可广播给全部用户），落库 + 实时推送。
"""
import asyncio
import json
from datetime import datetime as _dt
from typing import List, Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_current_user, resolve_user_from_token
from app.crud import notification as crud_notification
from app.crud import user as crud_user
from app.db.models.user import User
from app.db.models.notification import NotificationType, NotificationLevel
from app.dependencies import get_db, BaseResponse
from app.service.notification_manager import NotificationManager

router = APIRouter()


class NotificationOut(BaseModel):
    id: str
    user_id: str
    type: str
    level: str
    title: str
    body: Optional[Dict[str, Any]] = None
    ref_type: Optional[str] = None
    ref_id: Optional[str] = None
    read: bool
    created_at: Optional[str] = None
    read_at: Optional[str] = None


class NotificationCreate(BaseModel):
    """管理员创建通知的请求体。"""
    type: str = NotificationType.SYSTEM.value
    level: str = NotificationLevel.INFO.value
    title: str
    body: Optional[Dict[str, Any]] = None
    ref_type: Optional[str] = None
    ref_id: Optional[str] = None
    user_ids: Optional[List[UUID]] = None  # 为空则广播给全部用户
    broadcast: bool = True


def _serialize(n) -> Dict[str, Any]:
    return crud_notification._serialize(n)


# ---------------------------------------------------------------------------
# SSE: 通用通知事件流
# ---------------------------------------------------------------------------
@router.get("/events", summary="通用通知 SSE 事件流")
async def notification_events(
    request: Request,
    token: str = Query(None, description="JWT 或 agent token；用于 EventSource 鉴权"),
    db: Session = Depends(get_db),
):
    """SSE channel for all notifications. Carries:
    - ``task.updated`` / ``task.created`` / ``task.retry`` (bridged from
      TaskManager, in-memory only, not persisted);
    - ``notification.created`` / ``notification.read`` (persisted notifications).
    A keep-alive ``ping`` is sent every 15 seconds.
    """
    if not token:
        raise HTTPException(status_code=401, detail="SSE requires token query parameter")
    user = resolve_user_from_token(token, db)

    manager = NotificationManager.get_instance()
    queue = manager.subscribe(user.id)

    async def event_generator():
        try:
            yield {"event": "hello", "data": json.dumps({"ts": _dt.utcnow().isoformat() + "Z"})}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield {
                        "event": msg.get("event", "notification.created"),
                        "data": json.dumps(msg.get("data") or {}, default=str),
                    }
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": json.dumps({"ts": _dt.utcnow().isoformat() + "Z"})}
        finally:
            manager.unsubscribe(queue)

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# REST: 收件箱
# ---------------------------------------------------------------------------
@router.get("", response_model=BaseResponse[List[NotificationOut]], summary="获取通知列表")
def list_notifications(
    type: Optional[str] = Query(None),
    unread: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    before_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = crud_notification.list_notifications(
        db, current_user.id, type=type, unread=unread, limit=limit, before_id=before_id
    )
    return BaseResponse.success(data=[_serialize(r) for r in rows])


@router.get("/unread-count", response_model=BaseResponse[Dict[str, int]], summary="未读通知数")
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = crud_notification.unread_count(db, current_user.id)
    return BaseResponse.success(data={"count": count})


@router.post("/{notif_id}/read", response_model=BaseResponse[Dict[str, Any]], summary="标记单条已读")
def mark_read(
    notif_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ok = crud_notification.mark_read(db, current_user.id, notif_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Notification not found")
    remaining = crud_notification.unread_count(db, current_user.id)
    return BaseResponse.success(data={"read": True, "unread_count": remaining})


@router.post("/read-all", response_model=BaseResponse[Dict[str, int]], summary="全部标记已读")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    n = crud_notification.mark_all_read(db, current_user.id)
    return BaseResponse.success(data={"marked": n})


# ---------------------------------------------------------------------------
# 管理员创建通知（系统公告 / 更新通知的落点）
# ---------------------------------------------------------------------------
@router.post("", response_model=BaseResponse[Dict[str, Any]], summary="管理员创建通知")
def create_notification(
    payload: NotificationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized")

    if payload.user_ids:
        targets = [uid for uid in payload.user_ids]
    elif payload.broadcast:
        targets = [u.id for u in crud_user.get_all_users(db)]
    else:
        targets = [current_user.id]

    created = []
    manager = NotificationManager.get_instance()
    for uid in targets:
        n = crud_notification.create_notification(
            db,
            user_id=uid,
            type=payload.type,
            title=payload.title,
            body=payload.body,
            level=payload.level,
            ref_type=payload.ref_type,
            ref_id=payload.ref_id,
        )
        manager.publish_to_user(
            uid,
            "notification.created",
            _serialize(n),
        )
        created.append(str(n.id))

    return BaseResponse.success(data={"created": created, "count": len(created)})
