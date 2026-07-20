import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, Body, Query, Request
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_current_user, resolve_user_from_token
from app.db.models import User
from app.dependencies import get_db, BaseResponse
from app.db.models.task import Task, TaskStatus, TaskType
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
from uuid import UUID
from app.service.task_manager import TaskManager
from app.crud import task as crud_task

router = APIRouter()

class TaskSchema(BaseModel):
    """任务详情返回模型"""
    id: UUID
    type: str
    status: str
    priority: int
    created_at: datetime
    updated_at: Optional[datetime]
    error: Optional[str]
    payload: Optional[Dict[str, Any]]
    total_items: Optional[int]
    processed_items: Optional[int]

    class Config:
        from_attributes = True


class TaskCreate(BaseModel):
    """创建任务请求体"""
    type: str
    payload: Optional[Dict[str, Any]] = {}


@router.get("/types", response_model=BaseResponse[List[Dict[str, str]]], summary="获取支持的任务类型")
def get_task_types():
    """
    返回系统支持的所有任务类型枚举及其描述
    """
    types = [{"type": t.value, "description": str(t.value)} for t in TaskType]
    return BaseResponse.success(data=types)


@router.get("/", response_model=BaseResponse[List[TaskSchema]], summary="获取任务列表")
def list_tasks(
    status: str = None,
    type: str = None,
    limit: int = 50,
    updated_since: str = Query(None, description="ISO 8601 时间戳；只返回 updated_at 晚于该时间的任务，用于断线补偿"),
    db: Session = Depends(get_db)
):
    """
    分页查询任务列表，可按状态和类型过滤。
    默认按创建时间倒序返回前 50 条。
    """
    data = crud_task.list_tasks(db, status=status, type=type, limit=limit, updated_since=updated_since)
    return BaseResponse.success(data=data)


@router.post("/fast-mode", summary="设置快速模式", response_model=BaseResponse[Dict[str, Any]])
def set_fast_mode(enabled: bool = Body(..., embed=True)):
    """
    开启或关闭快速模式。
    快速模式下，系统将尝试同时运行 IO 密集型和 CPU 密集型任务，
    以最大化利用系统资源。
    """
    TaskManager.get_instance().set_fast_mode(enabled)
    return BaseResponse.success(data={"status": "success", "fast_mode": enabled})


@router.get("/status", summary="获取全局任务状态", response_model=BaseResponse[Dict[str, Any]])
def get_status(db: Session = Depends(get_db)):
    """
    获取当前扫描状态和快速模式状态。
    """
    # return "hello world"
    return BaseResponse.success(data=TaskManager.get_instance().get_status())


@router.get("/grouped-status", summary="按状态分组统计任务", response_model=BaseResponse[List[Dict[str, Any]]])
def get_grouped_status(db: Session = Depends(get_db)):
    """
    调用 TaskManager 获取按状态分组的任务统计信息。
    """
    return BaseResponse.success(data=TaskManager.get_instance().get_grouped_status(db))


@router.post("/categories/{category}/pause", summary="暂停指定分类任务", response_model=BaseResponse[Dict[str, Any]])
def pause_category(category: str):
    """
    暂停某一分类（category）下的所有待处理任务。
    """
    TaskManager.get_instance().pause_category(category)
    return BaseResponse.success(data={"status": "success"})


@router.post("/categories/{category}/resume", summary="恢复指定分类任务", response_model=BaseResponse[Dict[str, Any]])
def resume_category(category: str):
    """
    恢复之前被暂停的某一分类（category）下的任务。
    """
    TaskManager.get_instance().resume_category(category)
    return BaseResponse.success(data={"status": "success"})




# ---------------------------------------------------------------------------
# SSE: real-time task status push
# ---------------------------------------------------------------------------
from datetime import datetime as _dt  # noqa: E402


def _serialize_task(task) -> dict:
    return {
        "id": str(task.id),
        "type": task.type,
        "status": task.status,
        "priority": task.priority,
        "total_items": task.total_items or 0,
        "processed_items": task.processed_items or 0,
        "error": task.error,
        "owner_id": str(task.owner_id) if task.owner_id else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        "payload": task.payload or {},
    }


def _resolve_user_from_token(token: str, db: Session) -> User:
    """Backwards-compatible wrapper around `app.api.deps.resolve_user_from_token`."""
    return resolve_user_from_token(token, db)


@router.get("/events", summary="任务状态 SSE 事件流")
async def task_events(
    request: Request,
    token: str = Query(None, description="JWT 或 agent token；用于 EventSource 鉴权（EventSource 无法自定义 header）"),
    db: Session = Depends(get_db),
):
    """SSE channel for real-time task status updates.

    The client opens this with ``EventSource('/api/tasks/events?token=...')``
    and listens for ``task.updated`` / ``task.created`` / ``task.retry`` events.
    A keep-alive comment is sent every 15 seconds so reverse proxies do not
    close the connection.
    """
    if not token:
        raise HTTPException(status_code=401, detail="SSE requires token query parameter")
    # Validate the token so the request 401s immediately on bad creds
    # instead of silently streaming an empty channel.
    _resolve_user_from_token(token, db)

    manager = TaskManager.get_instance()
    queue = manager.subscribe()

    async def event_generator():
        try:
            yield {"event": "hello", "data": json.dumps({"ts": _dt.utcnow().isoformat() + "Z"})}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield {
                        "event": msg.get("event", "task.updated"),
                        "data": json.dumps(msg.get("data") or {}, default=str),
                    }
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": json.dumps({"ts": _dt.utcnow().isoformat() + "Z"})}
        finally:
            manager.unsubscribe(queue)

    return EventSourceResponse(event_generator())


@router.get("/recent", summary="获取最近完成 / 失败任务（用于 SSE 断线补偿）", response_model=BaseResponse[List[Dict[str, Any]]])
def list_recent_tasks(
    since: str = Query(..., description="ISO 8601 时间戳"),
    limit: int = 100,
    token: str = Query(None, description="JWT 或 agent token"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return tasks updated after the given timestamp. The frontend uses
    this to catch up on missed events after a reconnect."""
    tasks = crud_task.list_tasks(db, status=None, type=None, limit=limit, updated_since=since)
    return BaseResponse.success(data=[_serialize_task(t) for t in tasks])


@router.get("/{task_id}", response_model=BaseResponse[TaskSchema], summary="根据 ID 获取任务详情")
def get_task(task_id: UUID, db: Session = Depends(get_db)):
    """
    根据任务 UUID 返回任务详情；若任务不存在则返回空任务。
    """
    task = crud_task.get_task(db, task_id)
    if not task:
        # 任务不存在，返回空任务
        task = Task(
            id=task_id, status=TaskStatus.COMPLETED,
            priority = 0,
            type=TaskType.PROCESS_BASIC,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
    return BaseResponse.success(data=task)


@router.post("/", response_model=BaseResponse[TaskSchema], summary="创建新任务")
def create_task(task_in: TaskCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    创建一个新任务。
    - type：任务类型，需为系统支持的 TaskType 枚举值。
    - payload：可选，任务附加数据。
    若 type 非法则返回 400。
    """
    # Validate type
    task_in.payload['user_id'] = str(current_user.id)  # Ensure user_id is included in payload
    try:
        task_type = TaskType(task_in.type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid task type: {task_in.type}")

    task = TaskManager.get_instance().add_task(db, task_in.type, task_in.payload, owner_id=current_user.id)
    return BaseResponse.success(data=task)


@router.post("/{task_id}/cancel", response_model=BaseResponse[TaskSchema], summary="取消任务")
def cancel_task(task_id: UUID, db: Session = Depends(get_db)):
    """
    将指定任务状态置为 CANCELLED。
    仅允许取消处于待处理或运行中的任务；已完成、已失败或已取消的任务将返回 400。
    """
    task = crud_task.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
        raise HTTPException(status_code=400, detail="Task is already finished")

    return BaseResponse.success(data=crud_task.cancel_task(db, task))


@router.post("/{task_id}/retry", response_model=BaseResponse[TaskSchema], summary="重试任务")
def retry_task(task_id: UUID, db: Session = Depends(get_db)):
    """
    重试失败的任务。
    """
    task = crud_task.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status != TaskStatus.FAILED:
         raise HTTPException(status_code=400, detail="Only failed tasks can be retried")
    
    task = TaskManager.get_instance().retry_task(db, task)
    return BaseResponse.success(data=task)


@router.post("/retry-all-failed", summary="重试所有失败任务", response_model=BaseResponse[Dict[str, Any]])
def retry_all_failed_tasks(
    types: Optional[List[str]] = Query(None),
    db: Session = Depends(get_db)
):
    """
    重试所有失败的任务。可选指定任务类型。
    """
    result = TaskManager.get_instance().retry_all_failed_tasks(db, types)
    return BaseResponse.success(data=result)


@router.delete("/failed", summary="删除失败任务", response_model=BaseResponse[Dict[str, Any]])
def delete_failed_tasks(
    types: Optional[List[str]] = Query(None),
    db: Session = Depends(get_db)
):
    """
    删除所有失败的任务。可选指定任务类型。
    """
    count = crud_task.delete_failed_tasks(db, types)
    return BaseResponse.success(data={"message": f"Deleted {count} failed tasks", "count": count})

