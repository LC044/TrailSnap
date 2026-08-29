from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.crud import swipe_filter as crud
from app.db.models.user import User
from app.dependencies import BaseResponse, get_db
from app.schemas.swipe_filter import (
    SwipeFilterBatch,
    SwipeFilterDecisionRequest,
    SwipeFilterDecisionResult,
    SwipeFilterResetResult,
    SwipeFilterUndoResult,
)


router = APIRouter()


@router.get("", response_model=BaseResponse[SwipeFilterBatch], summary="获取断舍离待处理照片")
def get_swipe_filter_batch(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    photos, stats = crud.get_batch(db, current_user.id, limit)
    return BaseResponse.success(data={"photos": photos, "stats": stats})


@router.put("/decisions", response_model=BaseResponse[SwipeFilterDecisionResult], summary="保存断舍离结果")
def save_swipe_filter_decisions(
    payload: SwipeFilterDecisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        updated = crud.save_decisions(db, current_user.id, payload.items)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return BaseResponse.success(data={"updated": updated})


@router.delete("/decisions/{photo_id}", response_model=BaseResponse[SwipeFilterUndoResult], summary="撤销断舍离结果")
def undo_swipe_filter_decision(
    photo_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return BaseResponse.success(data={"undone": crud.undo_decision(db, current_user.id, photo_id)})


@router.delete("/decisions", response_model=BaseResponse[SwipeFilterResetResult], summary="重置断舍离处理记录")
def reset_swipe_filter_decisions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return BaseResponse.success(data={"reset": crud.reset_decisions(db, current_user.id)})
