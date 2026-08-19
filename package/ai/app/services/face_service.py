import logging
import os
import sys
import gc
from pathlib import Path
import numpy as np
import cv2

from app.config import settings
from app.services.model_manager import model_manager
from app.services.unified_model_manager import ai_model_manager
from app.services.onnx_providers import get_onnx_providers

def load_insightface_model():
    try:
        import insightface
        from insightface.app import FaceAnalysis

        model_name = ai_model_manager.get_model_selection("face")
        logging.info(f"Initializing InsightFace with model: {model_name}")

        # 推理后端按 CUDA -> OpenVINO -> CPU 自动选择，与安装的 extra (gpu/openvino/cpu) 对齐。
        providers, provider_options = get_onnx_providers()
        model_path = str(Path(settings.MODEL_PATH).expanduser().resolve().parent)
        app = FaceAnalysis(
            name=model_name, root=model_path,
            providers=providers,
            provider_options=provider_options,
        )
        app.prepare(ctx_id=0, det_size=(640, 640))
        logging.info("InsightFace model initialized successfully.")
        return app
    except Exception as e:
        logging.error(f"Failed to initialize InsightFace model: {e}")
        raise e

def release_model(model):
    # Attempt to clear CUDA cache if torch is available (Global fallback)
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


    # 清理InsightFace的CUDA上下文（如果存在）
    try:
        import insightface
        insightface.utils.face_align.clear_cache()
    except:
        pass
    """深度清理InsightFace的FaceAnalysis实例"""
    app = model
    try:
        # 1. 清理FaceAnalysis内部的模型和会话（关键！）
        if hasattr(app, 'models'):
            for model_name, model in app.models.items():
                # 清理模型的ONNX会话
                if hasattr(model, 'session'):
                    del model.session
                # 清理模型权重/缓存
                if hasattr(model, 'model'):
                    del model.model
                # 清理模型输入输出缓存
                if hasattr(model, 'input_names'):
                    del model.input_names
                if hasattr(model, 'output_names'):
                    del model.output_names
            del app.models  # 删除所有模型

        # 2. 清理FaceAnalysis的其他缓存
        if hasattr(app, 'det_model'):
            del app.det_model
        if hasattr(app, 'rec_model'):
            del app.rec_model
        if hasattr(app, 'cls_model'):
            del app.cls_model

        # 4. 强制GC（清理循环引用）
        gc.collect()
        logging.info("InsightFace model internal resources cleaned")
    except Exception as e:
        logging.error(f"Failed to cleanup InsightFace internal resources: {e}", exc_info=True)
    try:
        # Release InsightFace model
        """清理sys.modules中的指定模块，释放导入占用的内存"""
        deleted_modules = []
        cleanup_modules = [
            # InsightFace核心模块
            "insightface",
            "insightface.app",
            "insightface.model_zoo",
            "insightface.utils",
            "insightface.data",
            "insightface.metrics",
        ]
        for module_name in cleanup_modules:
            for key in list(sys.modules.keys()):
                if key == module_name or key.startswith(f"{module_name}."):
                    del sys.modules[key]
                    deleted_modules.append(key)
        if deleted_modules:
            logging.info(f"Deleted modules for InsightFace: {deleted_modules[:10]}...")  # 只打印前10个避免过长
    except Exception as e:
        logging.error(f"Failed to release InsightFace model: {e}")
        raise e

# Register the model
model_manager.register_model("face", load_insightface_model, release_model)

class FaceRecognitionService:
    def process_image(self, image_bytes: bytes):
        """
        Process image bytes and return face analysis results
        """
        if not ai_model_manager.is_ready("face"):
            raise Exception("Face model is not ready yet. Please try again later.")

        # Get model instance from manager (lazy load if needed)
        app = model_manager.get_model("face")

        # Convert bytes to numpy array
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise ValueError("Invalid image data")
        height, width , _ = img.shape
        if width == 0 or height == 0:
            raise ValueError("Image is empty")
        # Perform face analysis
        faces = app.get(img)

        results = []
        for face in faces:
            # Extract relevant data
            # face.bbox is [x1, y1, x2, y2]
            # face.kps is 5 keypoints (eyes, nose, mouth corners)
            # face.embedding is 512-d feature vector
            # face.det_score is detection confidence
            # bbox改成百分比坐标
            bbox = face.bbox / np.array([width, height, width, height])
            face_data = {
                "bbox": bbox.tolist(),
                "kps": face.kps.tolist(),
                "det_score": float(face.det_score),
                "embedding": face.embedding.tolist(), # Convert numpy array to list for JSON serialization
                # "gender": face.sex, # Available in some models
                # "age": face.age,    # Available in some models
            }
            results.append(face_data)
        return results
# Singleton instance
face_service = FaceRecognitionService()
