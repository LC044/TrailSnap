import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.llm_manager import llm_manager
from app.services.unified_model_manager import ai_model_manager


router = APIRouter()
logger = logging.getLogger(__name__)


class ModelSelectionRequest(BaseModel):
    task: str
    model: str


@router.get("/config", response_model=Dict[str, Any])
async def get_config():
    """Return selections generated from the same catalog used for downloads."""
    return ai_model_manager.list_models()["tasks"]


@router.get("/models", response_model=Dict[str, Any])
async def get_managed_models():
    return ai_model_manager.list_models()


@router.post("/models/{model_id}/download", response_model=Dict[str, Any])
async def download_managed_model(model_id: str):
    try:
        ai_model_manager.trigger_download(model_id)
        return {"status": "downloading", "model": model_id}
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error))


@router.delete("/models/{model_id}", response_model=Dict[str, Any])
async def delete_managed_model(model_id: str):
    try:
        if "llm" in ai_model_manager.get_spec(model_id).get("tasks", []):
            await llm_manager.stop()
        switched = ai_model_manager.delete_model(model_id)
        return {"status": "deleted", "model": model_id, "switched": switched}
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error))


@router.post("/config/model", response_model=Dict[str, Any])
async def set_model(request: ModelSelectionRequest):
    try:
        result = ai_model_manager.select_model(request.task, request.model)
        logger.info("AI model selection task=%s model=%s result=%s", request.task, request.model, result)
        return {**result, "task": request.task, "model": request.model}
    except (ValueError, KeyError) as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        logger.exception("Failed to select AI model")
        raise HTTPException(status_code=500, detail=str(error))
