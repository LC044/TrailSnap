"""Owner-scoped editable zero-shot classification API."""

from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.api.deps import get_current_user
from app.db.models.user import User
from app.db.models.photo import Photo
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.db.models.clip_classification import (
    ClipCategory,
    ClipRuleRevision,
)
from app.dependencies import BaseResponse, get_db
from app.schemas.photo import Photo as PhotoSchema
from app.service import clip_classification as svc
from app.service.clip_catalog import load_catalog

router = APIRouter()


class RuleInput(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    descriptions: list[str] = Field(min_length=1, max_length=5)
    groups: list[str] = Field(
        default_factory=lambda: ["自定义"], min_length=1, max_length=3
    )
    strictness: Literal["relaxed", "standard", "strict"] = "standard"
    thresholds: dict[str, float]
    enabled: bool = False
    revision: int | None = None
    apply_history: bool = False

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError("分类名称不能为空")
        return value.strip()

    @field_validator("descriptions", "groups")
    @classmethod
    def clean_texts(cls, values):
        values = list(dict.fromkeys(v.strip() for v in values))
        if any(not v for v in values) or any(len(v) > 100 for v in values):
            raise ValueError("内容不能为空或超过100字")
        return values

    @field_validator("thresholds")
    @classmethod
    def valid_thresholds(cls, values):
        if not values or any(not -1 <= v <= 1 for v in values.values()):
            raise ValueError("阈值必须在 -1 到 1 之间")
        return values


class PreviewInput(RuleInput):
    sample_size: int = Field(default=1000, ge=1, le=5000)
    photo_ids: list[UUID] | None = Field(default=None, max_length=50)


class RebuildInput(BaseModel):
    category_ids: list[UUID] | None = Field(default=None, max_length=300)


class EnableInput(BaseModel):
    category_ids: list[UUID] = Field(min_length=1, max_length=300)
    enabled: bool


@router.post("/enable", response_model=BaseResponse[dict])
def enable_categories(
    payload: EnableInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        cats = [
            svc.owned_category(db, user.id, cid, lock=True)
            for cid in sorted(set(payload.category_ids))
        ]
        newly_enabled = [cat.id for cat in cats if payload.enabled and not cat.enabled]
        for cat in cats:
            cat.enabled = payload.enabled
        db.commit()
        result = {"updated": len(cats)}
        if newly_enabled:
            result['task_id'] = queue_rebuild(db, user, newly_enabled)
        return BaseResponse.success(result)
    except ValueError as exc:
        db.rollback()
        return BaseResponse.fail(400, str(exc))


def queue_rebuild(db, user, category_ids=None):
    from app.db.models.task import TaskType
    from app.service.task_manager import TaskManager

    manager = TaskManager.get_instance()
    task = manager.add_task(
        db,
        type=TaskType.CLASSIFY_IMAGE_CLIP,
        payload={
            "category_ids": [str(c) for c in category_ids] if category_ids else None
        },
        owner_id=user.id,
    )
    return str(task.id)


@router.get("/categories", response_model=BaseResponse[dict])
def categories(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        if svc.ensure_presets(db, user.id):
            db.commit()
        rows = (
            db.query(ClipCategory, ClipRuleRevision, PhotoTag)
            .join(ClipRuleRevision, (ClipRuleRevision.category_id == ClipCategory.id)
                  & (ClipRuleRevision.revision == ClipCategory.revision))
            .join(PhotoTag, PhotoTag.id == ClipCategory.tag_id)
            .filter(ClipCategory.owner_id == user.id, ClipCategory.is_deleted.is_(False))
            .all()
        )
        cats = [cat for cat, _, _ in rows]
        counts = dict(
            db.query(PhotoTagRelation.tag_id, func.count(PhotoTagRelation.id))
            .join(Photo, Photo.id == PhotoTagRelation.photo_id)
            .filter(
                Photo.owner_id == user.id,
                Photo.is_deleted.is_(False),
                PhotoTagRelation.is_deleted.is_(False),
                PhotoTagRelation.tag_id.in_([cat.tag_id for cat in cats]),
            )
            .group_by(PhotoTagRelation.tag_id)
            .all()
        )
        return BaseResponse.success(
            {
                "groups": list(
                    dict.fromkeys(
                        load_catalog()["groups"]
                        + ["自定义"]
                        + [group for cat in cats for group in cat.groups]
                    )
                ),
                "categories": [
                    dict(svc.serialize_category(db, c, rule=rule, tag=tag), count=counts.get(c.tag_id, 0))
                    for c, rule, tag in rows
                ],
            }
        )
    except ValueError as exc:
        db.rollback()
        return BaseResponse.fail(400, str(exc))


@router.post("/preview", response_model=BaseResponse[dict])
def preview(
    payload: PreviewInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        result = svc.preview(
            db,
            user.id,
            payload.descriptions,
            payload.strictness,
            payload.thresholds,
            payload.sample_size,
            payload.photo_ids,
        )
        for key in ("matches", "boundary"):
            result[key] = [
                dict(
                    row,
                    photo=PhotoSchema.model_validate(row["photo"]).model_dump(
                        mode="json"
                    ),
                )
                for row in result[key]
            ]
        return BaseResponse.success(result)
    except (ValueError, OSError) as exc:
        return BaseResponse.fail(400, str(exc))
    except Exception as exc:
        return BaseResponse.fail(503, f"预览失败：{exc}")


def save_rule(db, user, payload, category_id=None):
    try:
        cat = (
            svc.owned_category(db, user.id, category_id, lock=True)
            if category_id
            else None
        )
        if cat and payload.revision != cat.revision:
            return BaseResponse.fail(409, "分类已更新，请重新打开编辑")
        newly_enabled = payload.enabled and (cat is None or not cat.enabled)
        old_tag = db.get(PhotoTag, cat.tag_id) if cat else None
        existing = (
            db.query(PhotoTag)
            .filter_by(owner_id=user.id, tag_name=payload.name, type="clip", is_deleted=False)
            .first()
        )
        if old_tag and existing and existing.id != old_tag.id:
            return BaseResponse.fail(409, "该名称已有标签，请使用其他名称")
        tag = old_tag if old_tag else svc.get_tag(db, user.id, payload.name)
        other = db.query(ClipCategory).filter_by(
            owner_id=user.id, tag_id=tag.id, is_deleted=False
        )
        if cat:
            other = other.filter(ClipCategory.id != cat.id)
        if other.first():
            return BaseResponse.fail(409, "该名称已有分类")
        tag.tag_name = payload.name
        if cat is None:
            cat = ClipCategory(
                owner_id=user.id,
                tag_id=tag.id,
                groups=payload.groups,
                enabled=payload.enabled,
                revision=1,
            )
            db.add(cat)
            db.flush()
            changed = True
        else:
            old_rule = db.get(ClipRuleRevision, (cat.id, cat.revision))
            changed = (
                old_rule.descriptions != payload.descriptions
                or old_rule.strictness != payload.strictness
                or old_rule.thresholds != payload.thresholds
            )
            if changed:
                cat.revision += 1
            cat.groups, cat.enabled = payload.groups, payload.enabled
        if changed:
            db.add(
                ClipRuleRevision(
                    category_id=cat.id,
                    revision=cat.revision,
                    descriptions=payload.descriptions,
                    strictness=payload.strictness,
                    thresholds=payload.thresholds,
                )
            )
        db.commit()
        result = svc.serialize_category(db, cat)
        if cat.enabled and (payload.apply_history or newly_enabled):
            result["task_id"] = queue_rebuild(db, user, [cat.id])
        return BaseResponse.success(result)
    except ValueError as exc:
        db.rollback()
        return BaseResponse.fail(400, str(exc))


@router.post("/categories", response_model=BaseResponse[dict])
def create_category(
    payload: RuleInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return save_rule(db, user, payload)


@router.put("/categories/{category_id}", response_model=BaseResponse[dict])
def update_category(
    category_id: UUID,
    payload: RuleInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return save_rule(db, user, payload, category_id)


@router.post("/rebuild", response_model=BaseResponse[dict])
def rebuild(
    payload: RebuildInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        if payload.category_ids:
            for cid in payload.category_ids:
                svc.owned_category(db, user.id, cid)
        return BaseResponse.success(
            {"task_id": queue_rebuild(db, user, payload.category_ids)}
        )
    except ValueError as exc:
        return BaseResponse.fail(400, str(exc))


@router.delete("/categories/{category_id}", response_model=BaseResponse[dict])
def delete_category(
    category_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        cat = svc.owned_category(db, user.id, category_id, lock=True)
        cat.is_deleted = True
        cat.enabled = False
        db.query(PhotoTagRelation).filter_by(tag_id=cat.tag_id).delete(synchronize_session=False)
        db.get(PhotoTag, cat.tag_id).is_deleted = True
        db.commit()
        return BaseResponse.success({"deleted": True})
    except ValueError as exc:
        db.rollback()
        return BaseResponse.fail(400, str(exc))
