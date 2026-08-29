import asyncio
import base64
import logging
import os
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import List, Any, Dict

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from app.services.ocr_service import ocr_service
from app.core.admission import ocr_admission
from app.config import settings

router = APIRouter()

class OCRRequest(BaseModel):
    images: List[str]

class OCRResult(BaseModel):
    prunedResult: Dict[str, Any] = {}
    ocrImage: str|None = ""
    docPreprocessingImage: str|None = ""
    inputImage: str|None = ""

class OCRResponse(BaseModel):
    results: List[Dict[str, Any]]


def _select_max_workers() -> int:
    """
    选择并发线程数：
    - RapidOCR 底层 ONNX Runtime 单图推理已用 intra-op 线程吃满多核，
      因此 OCR 的并发收益主要来自「解码/IO 与推理重叠」+ 不阻塞 event loop，
      而非多核线性加速。CPU 下并发度取保守值避免线程 oversubscription。
    - GPU 部署显存是瓶颈，限制并发避免 OOM。
    """
    cpu_count = os.cpu_count() or 4
    try:
        import torch
        if torch.cuda.is_available():
            # GPU：推理在显卡上串行，少量线程足以让解码与推理重叠
            return min(max(1, settings.AI_INFERENCE_THREADS), cpu_count)
    except Exception:
        pass
    # CPU：RapidOCR 单图已占满 intra-op 线程，2~4 足以重叠 IO，过多反而抢核
    return min(max(1, settings.AI_INFERENCE_THREADS), cpu_count)


# 模块级线程池，避免每次请求重新创建线程的开销
_ocr_executor = ThreadPoolExecutor(
    max_workers=_select_max_workers(),
    thread_name_prefix="ocr-batch",
)


def _process_one(b64: str) -> dict:
    """处理单张 base64 图片，供线程池并发调用。"""
    if ',' in b64:
        b64 = b64.split(',')[1]
    contents = base64.b64decode(b64)
    results = ocr_service.detect_text(contents)
    return {
        "ocrResults": results,
        "dataInfo": []
    }


@router.post("/predict", response_model=OCRResponse, summary="OCR Prediction")
async def ocr_predict(request: OCRRequest):
    """
    Perform OCR prediction on multiple base64 encoded images.
    - **images**: List of base64 encoded image strings.
    Returns:
        OCRResponse: The OCR results and images.
        - **dataInfo**: Additional information about the OCR process.
        - **ocrResults**: The OCR results, including pruned results and images.
            - **prunedResult**: The pruned OCR result, containing the detected text and other relevant information.
                - **rec_texts**: (List[str]) 文本识别结果列表，仅包含置信度超过text_rec_score_thresh的文本
                - **rec_scores**: (List[float]) 文本识别的置信度列表，已按text_rec_score_thresh过滤
                - **rec_polys**: (List[List[int]]) 经过置信度过滤的文本检测框列表，文本检测的多边形框列表。每个检测框由4个顶点坐标构成的int数组表示，数组shape为(4, 2)，数据类型为int16
                - **rec_boxes**: (List[List[int]]) 检测框的矩形边界框列表，每个元素为一个4个整数的列表，分别表示矩形框的[x_min, y_min, x_max, y_max]坐标，其中(x_min, y_min)为左上角坐标，(x_max, y_max)为右下角坐标
            - **ocrImage**: The image of the OCR result.
            - **docPreprocessingImage**: The image of the document preprocessing step.
            - **inputImage**: The original input image.
    """
    if not request.images:
        raise HTTPException(status_code=400, detail="No images provided")

    loop = asyncio.get_running_loop()
    await ocr_admission.acquire()
    try:
        # 每张图各自提交到线程池并发处理，同时把同步推理移出事件循环。
        # return_exceptions=True：单张图片失败（如损坏、解码失败）不影响整批，
        # 失败项以 error 字段返回，其余正常出结果。
        tasks = [
            loop.run_in_executor(_ocr_executor, _process_one, b64)
            for b64 in request.images
        ]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        batch_results = []
        for res in raw_results:
            if isinstance(res, Exception):
                logging.error(f"ocr single image failed: {res}")
                batch_results.append({
                    "ocrResults": [],
                    "dataInfo": [],
                    "error": str(res),
                })
            else:
                batch_results.append(res)
        return OCRResponse(results=batch_results)
    except Exception as e:
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        ocr_admission.release()
