import logging
import traceback

from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.face_service import face_service
from typing import List, Dict, Any
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

class RecognitionResponse(BaseModel):
    results: List[SingleImageRecognitionResponse]

class FaceRecognitionRequest(BaseModel):
    images: List[str]

@router.post("/face-recognition", response_model=RecognitionResponse)
async def face_recognition(request: FaceRecognitionRequest):
    """
    Upload multiple base64 encoded images to detect faces and extract features.
    """
    if not request.images:
        raise HTTPException(status_code=400, detail="No images provided")
        
    import base64
    try:
        batch_results = []
        for b64 in request.images:
            if ',' in b64:
                b64 = b64.split(',')[1]
            contents = base64.b64decode(b64)
            results = face_service.process_image(contents)
            batch_results.append({
                "face_count": len(results),
                "faces": results
            })
        return {"results": batch_results}
    except ValueError as ve:
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
