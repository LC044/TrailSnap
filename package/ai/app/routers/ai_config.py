from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, Any, List
from app.services.ai_config_manager import ai_config_manager
from app.services.model_downloader import model_downloader
from app.services.model_manager import model_manager
from app.services.llm_manager import llm_manager
import logging

router = APIRouter()

class ModelSelectionRequest(BaseModel):
    task: str
    model: str

@router.get("/config", response_model=Dict[str, Any])
async def get_config():
    """Get the current AI configuration."""
    return ai_config_manager.get_config()


@router.get("/models", response_model=Dict[str, Any])
async def get_managed_models():
    """List model packs and selections managed by this AI service instance."""
    return {
        "models": model_downloader.list_models(managed_only=True),
        "selections": ai_config_manager.get_config().get("models", {}),
    }


@router.post("/models/{model_id}/download", response_model=Dict[str, Any])
async def download_managed_model(model_id: str):
    try:
        model_downloader.reset_status(model_id)
        model_downloader.trigger_download(model_id)
        return {"status": "downloading", "model": model_id}
    except KeyError:
        raise HTTPException(status_code=404, detail="未知的模型包")


@router.delete("/models/{model_id}", response_model=Dict[str, Any])
async def delete_managed_model(model_id: str):
    try:
        if model_id == "llm_minicpm":
            await llm_manager.stop()
        for wrapper in model_manager.models.values():
            wrapper.release()
        model_downloader.delete_model(model_id)
        return {"status": "deleted", "model": model_id}
    except KeyError:
        raise HTTPException(status_code=404, detail="未知的模型包")
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error))

@router.post("/config/model", response_model=Dict[str, Any])
async def set_model(request: ModelSelectionRequest, background_tasks: BackgroundTasks):
    """
    Set the model for a specific task.
    Triggers model download if necessary.
    """
    try:
        changed = ai_config_manager.set_model_selection(request.task, request.model)
        
        if changed:
            logging.info(f"Model selection changed for {request.task} to {request.model}")
            # Mapping from task name to manager key
            manager_key_map = {
                "ocr": "ocr",
                "face": "face",
                "classification": ["clip_text", "clip_image"],
                "llm": "llm_minicpm",
            }
            
            keys = manager_key_map.get(request.task)
            
            # Release old models
            if keys:
                if isinstance(keys, list):
                    for k in keys:
                         try:
                             if k in model_manager.models:
                                 model_manager.models[k].release()
                         except Exception as e:
                             logging.warning(f"Failed to release model {k}: {e}")
                else:
                    try:
                         if keys in model_manager.models:
                             model_manager.models[keys].release()
                    except Exception as e:
                         logging.warning(f"Failed to release model {keys}: {e}")

            if request.task == "llm":
                await llm_manager.stop()

            # Trigger download/check for new models
            if keys:
                 if isinstance(keys, list):
                     for k in keys:
                         model_downloader.reset_status(k)
                         model_downloader.trigger_download(k)
                 else:
                     model_downloader.reset_status(keys)
                     model_downloader.trigger_download(keys)

        return {"status": "success", "config": ai_config_manager.get_config()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.error(f"Failed to set model: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
