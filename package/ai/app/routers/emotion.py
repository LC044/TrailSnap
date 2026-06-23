"""情绪色彩提取路由 - 从图片中提取主色调、亮度、饱和度及情绪暗示"""

import logging
import traceback

from fastapi import APIRouter, HTTPException
from app.services.emotion_service import emotion_service
from pydantic import BaseModel, Field
from typing import List, Optional

router = APIRouter()

logger = logging.getLogger("app.routers.emotion")


class EmotionRequest(BaseModel):
    images: List[str] = Field(..., description="List of base64 encoded image strings")


class ColorInfo(BaseModel):
    hex: str = Field(..., description="Hex color code, e.g. #E8A87C")
    ratio: float = Field(..., description="Proportion of this color in the image (0-1)")


class EmotionResponseItem(BaseModel):
    status: str = Field(..., description="'success' or 'error'")
    dominant_colors: List[ColorInfo] = Field(default=[], description="Top dominant colors sorted by ratio")
    brightness: Optional[float] = Field(default=None, description="Average brightness (0-1)")
    saturation: Optional[float] = Field(default=None, description="Average saturation (0-1)")
    emotion_hint: Optional[str] = Field(default=None, description="Emotion hint: warm/cool/neutral/vibrant/muted")
    top_categories: List[str] = Field(default=[], description="Inferred scene categories from color signals")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class EmotionResponse(BaseModel):
    results: List[EmotionResponseItem] = Field(..., description="Emotion analysis results for each image")


@router.post("/", response_model=EmotionResponse, summary="Emotion Color Extraction")
async def extract_emotion(request: EmotionRequest):
    """
    Extract dominant colors, brightness, saturation, and emotion hints from images.

    - **images**: List of base64 encoded image strings.

    Returns:
        EmotionResponse with dominant colors, brightness, saturation, and emotion hint for each image.
    """
    if not request.images:
        raise HTTPException(status_code=400, detail="No images provided")
    try:
        results = await emotion_service.analyze(request.images)
        return {"results": results}
    except Exception as e:
        logger.error(f"Error in emotion extraction API: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
