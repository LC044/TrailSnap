from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models.user import User
from app.dependencies import BaseResponse, get_db
from app.schemas.agent_action import AgentActionPlanRead
from app.service.agent.actions import (
    execute_plan,
    expire_stale_plans,
    get_owned_plan,
    list_owned_plans,
    mark_plan_failed,
    undo_plan,
)


router = APIRouter()


def _serialize(row):
    return AgentActionPlanRead.model_validate(row).model_dump(mode="json")


@router.get("", summary="获取 Agent 操作计划")
def list_action_plans(
    session_id: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return BaseResponse.success(data=[_serialize(row) for row in list_owned_plans(db, current_user.id, session_id, status, limit)])


@router.get("/{plan_id}", summary="获取 Agent 操作计划详情")
def get_action_plan(plan_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    expire_stale_plans(db, current_user.id)
    row = get_owned_plan(db, current_user.id, plan_id)
    if not row:
        raise HTTPException(status_code=404, detail="Action plan not found")
    return BaseResponse.success(data=_serialize(row))


@router.post("/{plan_id}/execute", summary="确认并执行 Agent 操作计划")
def confirm_action_plan(plan_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        row = execute_plan(db, current_user.id, plan_id)
    except ValueError as exc:
        db.rollback()
        mark_plan_failed(db, current_user.id, plan_id, str(exc))
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        mark_plan_failed(db, current_user.id, plan_id, "执行过程中发生内部错误")
        raise HTTPException(status_code=500, detail="Action plan execution failed") from exc
    return BaseResponse.success(data=_serialize(row))


@router.post("/{plan_id}/undo", summary="撤销 Agent 操作计划")
def undo_action_plan(plan_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        row = undo_plan(db, current_user.id, plan_id)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return BaseResponse.success(data=_serialize(row))
