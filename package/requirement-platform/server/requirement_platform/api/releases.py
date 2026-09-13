"""Release planning HTTP endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .responses import ok
from ..db import get_db
from ..delivery import DomainConflict
from ..domain import releases as release_service
from ..domain import requirements as requirement_service
from ..domain.common import audit
from ..models import ReleaseBatch, ReleaseBatchItem, User
from ..presenters import batch_data
from ..schemas import BatchCreate, BatchItemInput, BatchStatusInput, BatchUpdate, DeliveryStatusInput
from ..security import manager, optional_user


router = APIRouter(prefix="/api/versions", tags=["versions"])


@router.get("")
def list_batches(user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    include_private = bool(user and user.role in {"admin", "owner"})
    return ok([batch_data(row, db, include_private=include_private)
               for row in db.query(ReleaseBatch).order_by(ReleaseBatch.created_at.desc()).all()])


@router.post("")
def create_batch(payload: BatchCreate, actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = ReleaseBatch(created_by=actor.id, **payload.model_dump())
    db.add(row)
    try:
        db.flush()
        audit(db, actor.id, "release_batch.created", "release_batch", row.id, version_name=row.version_name)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Version name already exists") from exc
    return ok(batch_data(row, db, include_private=True))


@router.patch("/{batch_id}")
def update_batch(batch_id: str, payload: BatchUpdate, actor: User = Depends(manager), db: Session = Depends(get_db)):
    try:
        batch = release_service.get_batch(db, batch_id)
    except release_service.ReleaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    values = payload.model_dump(exclude_unset=True)
    if "version_name" in values and values["version_name"] != batch.version_name:
        other = db.query(ReleaseBatch.id).filter(
            ReleaseBatch.version_name == values["version_name"], ReleaseBatch.id != batch.id
        ).first()
        if other:
            raise HTTPException(status_code=409, detail="Version name already exists")
    before_version_name = batch.version_name
    for key, value in values.items():
        setattr(batch, key, value)
    audit(db, actor.id, "release_batch.updated", "release_batch", batch.id,
          fields=sorted(values), before_version_name=before_version_name, version_name=batch.version_name)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Version name already exists") from exc
    return ok(batch_data(batch, db, include_private=True))


@router.get("/{batch_id}")
def get_batch(batch_id: str, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    try:
        row = release_service.get_batch(db, batch_id)
    except release_service.ReleaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ok(batch_data(row, db, include_private=bool(user and user.role in {"admin", "owner"})))


@router.post("/{batch_id}/items")
def add_batch_item(batch_id: str, payload: BatchItemInput, actor: User = Depends(manager), db: Session = Depends(get_db)):
    try:
        batch = release_service.get_batch(db, batch_id)
        requirement = requirement_service.get_requirement(db, payload.requirement_id)
        release_service.add_item(db, batch, requirement, actor_id=actor.id,
                                 priority_order=payload.priority_order, source="rest")
        db.flush()
        db.commit()
    except (release_service.ReleaseNotFound, requirement_service.RequirementNotFound) as exc:
        raise HTTPException(status_code=404, detail="Batch or requirement not found") from exc
    except (IntegrityError, DomainConflict) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ok(batch_data(batch, db, include_private=True))


@router.delete("/{batch_id}/items/{item_id}")
def remove_batch_item(batch_id: str, item_id: str, actor: User = Depends(manager), db: Session = Depends(get_db)):
    batch = db.query(ReleaseBatch).filter(ReleaseBatch.id == batch_id).first()
    item = db.query(ReleaseBatchItem).filter(
        ReleaseBatchItem.id == item_id, ReleaseBatchItem.batch_id == batch_id
    ).first()
    if not batch or not item:
        raise HTTPException(status_code=404, detail="Batch item not found")
    release_service.remove_item(db, batch, item, actor_id=actor.id, source="rest")
    db.commit()
    return ok({"removed": True})


@router.post("/{batch_id}/lock")
def lock_batch(batch_id: str, actor: User = Depends(manager), db: Session = Depends(get_db)):
    try:
        batch = release_service.get_batch(db, batch_id)
        release_service.lock_batch(db, batch, actor_id=actor.id, source="release_batch")
    except release_service.ReleaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return ok(batch_data(batch, db, include_private=True))


@router.patch("/{batch_id}/status")
def update_batch_status(batch_id: str, payload: BatchStatusInput, actor: User = Depends(manager), db: Session = Depends(get_db)):
    try:
        batch = release_service.get_batch(db, batch_id)
        release_service.change_status(db, batch, actor_id=actor.id, actor_role=actor.role,
                                      status=payload.status, reason=payload.reason, source="release_batch")
    except release_service.ReleaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    db.commit()
    return ok(batch_data(batch, db, include_private=True))


@router.patch("/{batch_id}/items/{item_id}/status")
def update_delivery_status(batch_id: str, item_id: str, payload: DeliveryStatusInput,
                           actor: User = Depends(manager), db: Session = Depends(get_db)):
    batch = db.query(ReleaseBatch).filter(ReleaseBatch.id == batch_id).first()
    item = db.query(ReleaseBatchItem).filter(
        ReleaseBatchItem.id == item_id, ReleaseBatchItem.batch_id == batch_id
    ).first()
    if not batch or not item:
        raise HTTPException(status_code=404, detail="Batch item not found")
    release_service.change_delivery_status(db, batch, item, actor_id=actor.id,
                                           status=payload.status, source="release_batch")
    db.commit()
    return ok({"id": item.id, "delivery_status": item.delivery_status})
