import logging
import traceback

from fastapi import APIRouter, HTTPException
from app.services.embedding_service import embedding_service
from app.core.admission import embedding_admission
from pydantic import BaseModel
from typing import List

router = APIRouter()

class TextEmbeddingRequest(BaseModel):
    texts: List[str]

class ImageEmbeddingRequest(BaseModel):
    images: List[str]

@router.post("/text", response_model=List[List[float]])
async def embed_texts(request: TextEmbeddingRequest):
    """
    Generate embeddings for multiple texts using the loaded CLIP model.
    """
    if not request.texts:
        raise HTTPException(status_code=400, detail="No texts provided")
    await embedding_admission.acquire()
    try:
        embeddings = await embedding_service.embed_texts(request.texts)
        return embeddings
    except Exception as e:
        logging.error(f"Error in text embedding API: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        embedding_admission.release()

@router.post("/image", response_model=List[List[float]])
async def embed_images(request: ImageEmbeddingRequest):
    """
    Generate embeddings for multiple images using the loaded CLIP model.
    Input images should be base64 encoded strings.
    """
    if not request.images:
        raise HTTPException(status_code=400, detail="No images provided")
    await embedding_admission.acquire()
    try:
        embeddings = await embedding_service.embed_images(request.images)
        return embeddings
    except Exception as e:
        logging.error(f"Error in image embedding API: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        embedding_admission.release()
