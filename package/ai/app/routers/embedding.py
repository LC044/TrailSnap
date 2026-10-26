import logging
import traceback

from fastapi import APIRouter, HTTPException, Response
from app.services.embedding_service import embedding_service
from app.services.unified_model_manager import ai_model_manager
from app.core.admission import embedding_admission
from pydantic import BaseModel
from typing import List

router = APIRouter()

class TextEmbeddingRequest(BaseModel):
    texts: List[str]
    cache: bool = False

class ImageEmbeddingRequest(BaseModel):
    images: List[str]
    model: str | None = None

@router.post("/text", response_model=List[List[float]])
async def embed_texts(request: TextEmbeddingRequest):
    """
    Generate embeddings for multiple texts using the loaded CLIP model.
    """
    if not request.texts:
        raise HTTPException(status_code=400, detail="No texts provided")
    await embedding_admission.acquire()
    try:
        embeddings = (await embedding_service.embed_texts(request.texts, use_cache=True)
                      if request.cache else await embedding_service.embed_texts(request.texts))
        return embeddings
    except Exception as e:
        logging.error(f"Error in text embedding API: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        embedding_admission.release()

@router.post("/image", response_model=List[List[float]])
async def embed_images(request: ImageEmbeddingRequest, response: Response = None):
    """
    Generate embeddings for multiple images using the loaded CLIP model.
    Input images should be base64 encoded strings.
    """
    if not request.images:
        raise HTTPException(status_code=400, detail="No images provided")
    await embedding_admission.acquire()
    try:
        selected = ai_model_manager.get_selected_spec("embedding")["runtimeName"]
        if request.model and request.model != selected:
            raise HTTPException(status_code=409, detail=f"等待 AI 模型：需要 {request.model}，当前为 {selected}")
        embeddings = await embedding_service.embed_images(request.images)
        if selected != ai_model_manager.get_selected_spec("embedding")["runtimeName"]:
            raise HTTPException(status_code=409, detail="等待 AI 模型：编码期间模型已切换，请重试")
        if response is not None:
            response.headers["X-Embedding-Model"] = selected
        return embeddings
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error in image embedding API: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        embedding_admission.release()
