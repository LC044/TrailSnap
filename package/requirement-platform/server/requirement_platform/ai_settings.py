"""Database-backed AI provider configuration and per-task model routing."""
from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from .config import settings
from .models import AIConnection, AIModel, AITaskRoute


TASK_TYPES = {
    "preflight_triage": ("提交前分析", "匿名用户提交前的同步分析与追问"),
    "requirement_triage": ("需求分诊", "需求提交或变更后的后台结构化分诊"),
    "spec_drafting": ("规格草拟", "预留：辅助生成规格草稿"),
    "coding": ("编码任务", "预留：为编码 Agent 推荐模型"),
    "testing": ("测试任务", "预留：为测试 Agent 推荐模型"),
    "review": ("审查任务", "预留：为审查 Agent 推荐模型"),
}


@dataclass(frozen=True)
class AIModelTarget:
    connection_id: str
    connection_name: str
    provider: str
    api_base: str
    api_key: str
    model_id: str
    model_name: str
    supports_json_mode: bool
    timeout_seconds: int
    reasoning_effort: str = "none"


def _fernet() -> Fernet:
    material = hashlib.sha256(f"trailsnap-requirement-ai:{settings.jwt_secret}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(material))


def encrypt_api_key(value: str) -> tuple[str | None, str | None]:
    value = value.strip()
    if not value:
        return None, None
    return _fernet().encrypt(value.encode()).decode(), f"••••{value[-4:]}"


def decrypt_api_key(value: str | None) -> str:
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError("AI API Key 无法解密，请管理员重新保存该连接的密钥") from exc


def model_dict(row: AIModel) -> dict[str, Any]:
    return {
        "id": row.id, "connection_id": row.connection_id, "model_name": row.model_name,
        "display_name": row.display_name, "enabled": row.enabled,
        "supports_json_mode": row.supports_json_mode, "context_window": row.context_window,
        "reasoning_levels": list(row.reasoning_levels or ["none"]),
        "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
    }


def connection_dict(db: Session, row: AIConnection) -> dict[str, Any]:
    models = db.query(AIModel).filter(AIModel.connection_id == row.id).order_by(AIModel.created_at).all()
    return {
        "id": row.id, "name": row.name, "provider": row.provider, "api_base": row.api_base,
        "has_api_key": bool(row.api_key_encrypted), "api_key_hint": row.api_key_hint,
        "enabled": row.enabled, "timeout_seconds": row.timeout_seconds, "priority": row.priority,
        "models": [model_dict(item) for item in models],
        "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
    }


def settings_dict(db: Session) -> dict[str, Any]:
    connections = db.query(AIConnection).order_by(AIConnection.priority, AIConnection.created_at).all()
    route_rows = {row.task_type: row for row in db.query(AITaskRoute).all()}
    legacy_enabled = bool(settings.ai_api_url and settings.ai_model)
    routes = []
    for task_type, (label, description) in TASK_TYPES.items():
        row = route_rows.get(task_type)
        routes.append({
            "task_type": task_type, "label": label, "description": description,
            "enabled": row.enabled if row else (legacy_enabled and task_type in {"preflight_triage", "requirement_triage"}),
            "model_ids": list(row.model_ids) if row else [],
            "reasoning_effort": row.reasoning_effort if row else "none",
            "source": "managed" if row else ("environment" if legacy_enabled and task_type in {"preflight_triage", "requirement_triage"} else "none"),
            "updated_at": row.updated_at.isoformat() if row else None,
        })
    return {"connections": [connection_dict(db, row) for row in connections], "routes": routes,
            "legacy_environment_configured": legacy_enabled}


def resolve_model_targets(db: Session, task_type: str) -> list[AIModelTarget]:
    route = db.query(AITaskRoute).filter(AITaskRoute.task_type == task_type).first()
    if route:
        if not route.enabled:
            return []
        models = {row.id: row for row in db.query(AIModel).filter(AIModel.id.in_(route.model_ids or [])).all()}
        connection_ids = {row.connection_id for row in models.values()}
        connections = {row.id: row for row in db.query(AIConnection).filter(AIConnection.id.in_(connection_ids)).all()}
        targets = []
        for model_id in route.model_ids or []:
            model = models.get(model_id)
            connection = connections.get(model.connection_id) if model else None
            if not model or not connection or not model.enabled or not connection.enabled:
                continue
            targets.append(AIModelTarget(
                connection_id=connection.id, connection_name=connection.name, provider=connection.provider,
                api_base=connection.api_base.rstrip("/"), api_key=decrypt_api_key(connection.api_key_encrypted),
                model_id=model.id, model_name=model.model_name, supports_json_mode=model.supports_json_mode,
                timeout_seconds=connection.timeout_seconds, reasoning_effort=route.reasoning_effort,
            ))
        return targets
    if task_type in {"preflight_triage", "requirement_triage"} and settings.ai_api_url and settings.ai_model:
        return [AIModelTarget(
            connection_id="environment", connection_name="环境变量兼容配置", provider="openai_compatible",
            api_base=settings.ai_api_url, api_key=settings.ai_api_key, model_id="environment",
            model_name=settings.ai_model, supports_json_mode=True, timeout_seconds=45,
        )]
    return []


def request_chat_completion(target: AIModelTarget, messages: list[dict[str, str]], *, json_mode: bool) -> str:
    body: dict[str, Any] = {"model": target.model_name, "temperature": 0.1, "messages": messages}
    if target.reasoning_effort != "none":
        body["reasoning_effort"] = target.reasoning_effort
    if json_mode and target.supports_json_mode:
        body["response_format"] = {"type": "json_object"}
    with httpx.Client(timeout=target.timeout_seconds) as client:
        response = client.post(
            f"{target.api_base}/chat/completions",
            headers={"Authorization": f"Bearer {target.api_key}"} if target.api_key else {},
            json=body,
        )
        response.raise_for_status()
        return str(response.json()["choices"][0]["message"]["content"]).strip()


def test_model_target(target: AIModelTarget) -> dict[str, Any]:
    try:
        content = request_chat_completion(
            target,
            [{"role": "user", "content": "Reply with exactly: OK"}],
            json_mode=False,
        )
        return {"available": True, "model": target.model_name, "response": content[:200]}
    except (httpx.HTTPError, KeyError, TypeError, ValueError, RuntimeError) as exc:
        return {"available": False, "model": target.model_name, "error": type(exc).__name__}
