import asyncio
import logging
import os
import traceback
from concurrent.futures import ThreadPoolExecutor

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


def _select_max_workers() -> int:
    """
    选择并发线程数：
    - 分类已用真 batch 推理（单次 session.run 跑完一批），ONNX intra-op 线程已吃满多核，
      线程池主要价值是「不阻塞 event loop」+ 重叠多请求/解码，而非多核线性加速。
    - GPU 部署显存是瓶颈，限制并发避免 OOM。
    """
    cpu_count = os.cpu_count() or 4
    try:
        import torch
        if torch.cuda.is_available():
            return min(4, cpu_count)
    except Exception:
        pass
    return min(4, cpu_count)


# 模块级线程池，避免每次请求重新创建线程的开销
_cls_executor = ThreadPoolExecutor(
    max_workers=_select_max_workers(),
    thread_name_prefix="cls-batch",
)


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
        # classify_yolo 内部已做批量解码 + 真 batch 推理 + 单图 error 容错；
        # 这里只负责把同步推理移出事件循环，避免阻塞其他请求。
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(
            _cls_executor,
            image_classification_service.classify_yolo,
            request.images,
        )
        return {"results": results}
    except Exception as e:
        logging.error(f"Error in ONNX classification API: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
