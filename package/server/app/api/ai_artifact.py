from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.crud import ai_artifact as artifact_crud
from app.db.models.user import User
from app.dependencies import BaseResponse, get_db
from app.schemas.ai_artifact import AIArtifactRead, AIArtifactUpdate

router = APIRouter()


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
