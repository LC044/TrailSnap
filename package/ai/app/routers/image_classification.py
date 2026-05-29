import logging
import traceback

from fastapi import APIRouter, HTTPException
from app.services.image_classification_service import image_classification_service
from pydantic import BaseModel, Field
from typing import List, Dict, Any

router = APIRouter()

class ImageClassificationRequest(BaseModel):
    images: List[str] = Field(..., description="List of base64 encoded image strings to be classified.")

class PredictionResult(BaseModel):
    label: str = Field(..., description="The predicted class label (translated to Chinese).")
    confidence: float = Field(..., description="The confidence score of the prediction (0.0 to 1.0).")

class ImageClassificationResponseItem(BaseModel):
    status: str = Field(..., description="Status of the classification for this image ('success' or 'error').")
    predictions: List[PredictionResult] = Field(default=[], description="List of predictions for the image.")
    error: str | None = Field(default=None, description="Error message if the classification failed.")

class ImageClassificationResponse(BaseModel):
    results: List[ImageClassificationResponseItem] = Field(..., description="List of classification results corresponding to the input images.")

@router.post("/", response_model=ImageClassificationResponse, summary="Image Classification")
async def classify_images(request: ImageClassificationRequest):
    """
    Classify one or multiple images using ONNX image classification models.
    
    - **images**: List of base64 encoded image strings.
    
    Returns:
        ImageClassificationResponse: The classification results.
        - **results**: List of classification results for each input image.
            - **status**: 'success' or 'error'.
            - **predictions**: Contains the predicted label and confidence.
                - **label**: The predicted category (e.g., '猫', '狗', '风景').
                - **confidence**: The confidence score of the prediction.
    """
    if not request.images:
        raise HTTPException(status_code=400, detail="No images provided")
    try:
        results = await image_classification_service.classify_yolo(request.images)
        return {"results": results}
    except Exception as e:
        logging.error(f"Error in ONNX classification API: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))