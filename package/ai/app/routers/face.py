import asyncio
import base64
import logging
import os
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.face_service import face_service
from pydantic import BaseModel

router = APIRouter()

# 人脸检测结果的子模型（对应FaceResult）
class FaceResult(BaseModel):
    bbox: List[float]          # 人脸检测框 [x1, y1, x2, y2]
    kps: List[List[float]]     # 人脸关键点 [[x1,y1], [x2,y2], ...]
    det_score: float           # 检测置信度 0~1
    embedding: List[float]     # 人脸特征向量

# 接口响应模型
class SingleImageRecognitionResponse(BaseModel):
    face_count: int            # 检测到的人脸数量
    faces: List[FaceResult]    # 每个人脸的详细结果
    error: Optional[str] = None  # 单张图片处理失败时的错误信息（成功时为 None）

class RecognitionResponse(BaseModel):
    results: List[SingleImageRecognitionResponse]

class FaceRecognitionRequest(BaseModel):
    images: List[str]


def _select_max_workers() -> int:
    """
    选择并发线程数：
    - ONNX Runtime 推理、cv2.imdecode、base64.b64decode 都会释放 GIL，
      因此线程池能真正并行（CPU 部署收益最大，GPU 部署可让解码与推理重叠）。
    - GPU 部署时显存是瓶颈，限制并发避免 OOM。
    """
    cpu_count = os.cpu_count() or 4
    try:
        import torch
        if torch.cuda.is_available():
            # GPU：推理本身在显卡上串行，少量线程足以让解码与推理重叠
            return min(4, cpu_count)
    except Exception:
        pass
    # CPU：用核心数填满多核并行，参考 ThreadPoolExecutor 默认上限封顶
    return min(8, cpu_count)


# 模块级线程池，避免每次请求重新创建线程的开销
_face_executor = ThreadPoolExecutor(
    max_workers=_select_max_workers(),
    thread_name_prefix="face-batch",
)


def _process_one(b64: str) -> dict:
    """处理单张 base64 图片，供线程池并发调用。"""
    if ',' in b64:
        b64 = b64.split(',')[1]
    contents = base64.b64decode(b64)
    results = face_service.process_image(contents)
    return {
        "face_count": len(results),
        "faces": results,
    }


@router.post("/face-recognition", response_model=RecognitionResponse)
async def face_recognition(request: FaceRecognitionRequest):
    """
    Upload multiple base64 encoded images to detect faces and extract features.
    """
    if not request.images:
        raise HTTPException(status_code=400, detail="No images provided")

    loop = asyncio.get_running_loop()
    try:
        # 每张图各自提交到线程池并发处理，同时把同步推理移出事件循环。
        # return_exceptions=True：单张图片失败（如损坏、空图）不影响整批，
        # 失败项以 error 字段返回，其余正常出结果。
        tasks = [
            loop.run_in_executor(_face_executor, _process_one, b64)
            for b64 in request.images
        ]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        batch_results = []
        for res in raw_results:
            if isinstance(res, Exception):
                logging.error(f"face-recognition single image failed: {res}")
                batch_results.append({
                    "face_count": 0,
                    "faces": [],
                    "error": str(res),
                })
            else:
                batch_results.append(res)
        return {"results": batch_results}
    except Exception as e:
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
