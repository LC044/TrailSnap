from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..ai_settings import (
    AIModelTarget, TASK_TYPES, connection_dict, decrypt_api_key, encrypt_api_key, model_dict,
    settings_dict, test_model_target,
)
from ..db import get_db
from ..domain.common import audit
from ..models import AIConnection, AIModel, AITaskRoute, User
from ..schemas import (
    AIConnectionCreate, AIConnectionTestInput, AIConnectionUpdate, AIModelCreate, AIModelUpdate, AITaskRouteUpdate,
)
from ..security import manager
from .responses import ok

router = APIRouter(prefix="/api/admin", tags=["ai-settings"])


@router.get("/ai-settings")
def get_ai_settings(_actor: User = Depends(manager), db: Session = Depends(get_db)):
    return ok(settings_dict(db))


@router.post("/ai-connections")
def create_ai_connection(payload: AIConnectionCreate, actor: User = Depends(manager), db: Session = Depends(get_db)):
    encrypted, hint = encrypt_api_key(payload.api_key)
    row = AIConnection(name=payload.name.strip(), provider=payload.provider, api_base=payload.api_base.rstrip("/"),
                       api_key_encrypted=encrypted, api_key_hint=hint, enabled=payload.enabled,
                       timeout_seconds=payload.timeout_seconds, priority=payload.priority, created_by=actor.id)
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="AI connection name already exists") from exc
    audit(db, actor.id, "ai_connection.created", "ai_connection", row.id,
          name=row.name, provider=row.provider, api_base=row.api_base)
    db.commit()
    db.refresh(row)
    return ok(connection_dict(db, row))


@router.patch("/ai-connections/{connection_id}")
def update_ai_connection(connection_id: str, payload: AIConnectionUpdate,
                         actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.query(AIConnection).filter(AIConnection.id == connection_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="AI connection not found")
    values = payload.model_dump(exclude_unset=True, exclude={"api_key", "clear_api_key"})
    for key, value in values.items():
        setattr(row, key, value.rstrip("/") if key == "api_base" else value)
    if payload.clear_api_key:
        row.api_key_encrypted, row.api_key_hint = None, None
    elif payload.api_key:
        row.api_key_encrypted, row.api_key_hint = encrypt_api_key(payload.api_key)
    audit(db, actor.id, "ai_connection.updated", "ai_connection", row.id,
          fields=sorted(payload.model_fields_set - {"api_key"}), api_key_changed=bool(payload.api_key or payload.clear_api_key))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="AI connection name already exists") from exc
    db.refresh(row)
    return ok(connection_dict(db, row))


@router.delete("/ai-connections/{connection_id}")
def delete_ai_connection(connection_id: str, actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.query(AIConnection).filter(AIConnection.id == connection_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="AI connection not found")
    model_ids = [item[0] for item in db.query(AIModel.id).filter(AIModel.connection_id == row.id).all()]
    for route in db.query(AITaskRoute).all():
        filtered = [item for item in (route.model_ids or []) if item not in model_ids]
        if filtered != (route.model_ids or []):
            route.model_ids = filtered
            if not filtered:
                route.enabled = False
    audit(db, actor.id, "ai_connection.deleted", "ai_connection", row.id, name=row.name)
    db.delete(row)
    db.commit()
    return ok({"deleted": True})


@router.post("/ai-connections/{connection_id}/models")
def create_ai_model(connection_id: str, payload: AIModelCreate,
                    actor: User = Depends(manager), db: Session = Depends(get_db)):
    if not db.query(AIConnection.id).filter(AIConnection.id == connection_id).first():
        raise HTTPException(status_code=404, detail="AI connection not found")
    row = AIModel(connection_id=connection_id, **payload.model_dump())
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Model already exists on this connection") from exc
    audit(db, actor.id, "ai_model.created", "ai_model", row.id, connection_id=connection_id, model_name=row.model_name)
    db.commit()
    db.refresh(row)
    return ok(model_dict(row))


@router.patch("/ai-models/{model_id}")
def update_ai_model(model_id: str, payload: AIModelUpdate,
                    actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.query(AIModel).filter(AIModel.id == model_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="AI model not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    audit(db, actor.id, "ai_model.updated", "ai_model", row.id, fields=sorted(payload.model_fields_set))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Model already exists on this connection") from exc
    db.refresh(row)
    return ok(model_dict(row))


@router.delete("/ai-models/{model_id}")
def delete_ai_model(model_id: str, actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.query(AIModel).filter(AIModel.id == model_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="AI model not found")
    for route in db.query(AITaskRoute).all():
        if model_id in (route.model_ids or []):
            route.model_ids = [item for item in route.model_ids if item != model_id]
            if not route.model_ids:
                route.enabled = False
    audit(db, actor.id, "ai_model.deleted", "ai_model", row.id, model_name=row.model_name)
    db.delete(row)
    db.commit()
    return ok({"deleted": True})


@router.put("/ai-task-routes/{task_type}")
def update_ai_task_route(task_type: str, payload: AITaskRouteUpdate,
                         actor: User = Depends(manager), db: Session = Depends(get_db)):
    if task_type not in TASK_TYPES:
        raise HTTPException(status_code=404, detail="Unknown AI task type")
    if payload.enabled and not payload.model_ids:
        raise HTTPException(status_code=422, detail="Enabled AI task routes require at least one model")
    found = {item[0] for item in db.query(AIModel.id).filter(AIModel.id.in_(payload.model_ids)).all()} if payload.model_ids else set()
    if found != set(payload.model_ids):
        raise HTTPException(status_code=422, detail="One or more AI models do not exist")
    selected_models = db.query(AIModel).filter(AIModel.id.in_(payload.model_ids)).all() if payload.model_ids else []
    unsupported = [item.model_name for item in selected_models if payload.reasoning_effort not in (item.reasoning_levels or ["none"])]
    if unsupported:
        raise HTTPException(status_code=422, detail=f"所选思考等级不受模型支持：{', '.join(unsupported)}")
    row = db.query(AITaskRoute).filter(AITaskRoute.task_type == task_type).first()
    if not row:
        row = AITaskRoute(task_type=task_type, updated_by=actor.id)
        db.add(row)
    row.enabled, row.model_ids, row.reasoning_effort, row.updated_by = payload.enabled, payload.model_ids, payload.reasoning_effort, actor.id
    audit(db, actor.id, "ai_task_route.updated", "ai_task_route", task_type,
          enabled=row.enabled, model_ids=row.model_ids, reasoning_effort=row.reasoning_effort)
    db.commit()
    return ok(next(item for item in settings_dict(db)["routes"] if item["task_type"] == task_type))


@router.post("/ai-connections/{connection_id}/test")
def test_ai_connection(connection_id: str, payload: AIConnectionTestInput,
                       _actor: User = Depends(manager), db: Session = Depends(get_db)):
    connection = db.query(AIConnection).filter(AIConnection.id == connection_id).first()
    if not connection:
        raise HTTPException(status_code=404, detail="AI connection not found")
    query = db.query(AIModel).filter(AIModel.connection_id == connection.id, AIModel.enabled.is_(True))
    model = query.filter(AIModel.id == payload.model_id).first() if payload.model_id else query.order_by(AIModel.created_at).first()
    if not model:
        raise HTTPException(status_code=409, detail="Please add and enable a model before testing")
    target = AIModelTarget(connection_id=connection.id, connection_name=connection.name, provider=connection.provider,
                           api_base=connection.api_base.rstrip("/"), api_key=decrypt_api_key(connection.api_key_encrypted),
                           model_id=model.id, model_name=model.model_name, supports_json_mode=model.supports_json_mode,
                           timeout_seconds=connection.timeout_seconds)
    return ok(test_model_target(target))
