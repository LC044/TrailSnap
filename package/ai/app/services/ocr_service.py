import numpy as np
import cv2
import logging
import sys
import os
from app.config import settings
from app.services.model_downloader import model_downloader
from app.services.model_manager import model_manager
from app.services.ai_config_manager import ai_config_manager

def load_paddleocr_model():
    try:
        model_root = settings.MODEL_PATH
        from rapidocr import EngineType, LangDet, LangRec, ModelType, OCRVersion, RapidOCR
        params = {
            "Det.engine_type": EngineType.ONNXRUNTIME,
            "Det.lang_type": LangDet.CH,
            "Det.model_type": ModelType.MOBILE,
            "Det.ocr_version": OCRVersion.PPOCRV5,
            "Rec.engine_type": EngineType.ONNXRUNTIME,
            "Rec.lang_type": LangRec.CH,
            "Rec.model_type": ModelType.MOBILE,
            "Rec.ocr_version": OCRVersion.PPOCRV5,
        }
        try:
            import torch
            if torch.cuda.is_available():
                params.update(
                    {
                        "Det.engine_type": EngineType.TORCH,
                        "Cls.engine_type": EngineType.TORCH,
                        "Rec.engine_type": EngineType.TORCH,
                        "EngineConfig.torch.use_cuda": True,  # 使用torch GPU版推理
                        "EngineConfig.torch.gpu_id": 0,  # 指定GPU id
                    }
                )
        except ImportError:
            pass
        ocr = RapidOCR(
            params=params,
        )
        logging.info("PaddleOCR model initialized successfully.")
        return ocr
    except Exception as e:
        logging.error(f"Failed to initialize PaddleOCR model: {e}")
        raise e

def release_paddleocr_model(model):
    try:
        logging.info("PaddleOCR resources released.")
    except Exception as e:
        logging.error(f"Error releasing PaddleOCR resources: {e}")

# Register
model_manager.register_model("ocr", load_paddleocr_model, release_paddleocr_model)

class OCRService:
    def __init__(self):
        self._register_downloads()

    def _register_downloads(self):
        def get_current_model_name():
            return ai_config_manager.get_model_selection("ocr")

        def check_ocr_model():
            model_name = get_current_model_name()
            marker_file = os.path.join(settings.MODEL_PATH, "official_models")
            marker_file = os.path.join(marker_file, f"PP-OCRv5_{model_name}_rec")
            return os.path.exists(marker_file)

        def download_ocr_model():
            model_name = get_current_model_name()
            logging.info(f"Downloading/Verifying PaddleOCR model ({model_name})...")
            # We need to set the env vars as before if they were useful
            model_root = os.path.join(settings.MODEL_PATH, "official_models")
            #模型下载
            from modelscope import snapshot_download
            model_path = os.path.join(model_root, f"PP-OCRv5_{model_name}_rec")
            # Note: This assumes the repo name follows the pattern
            try:
                snapshot_download(f'PaddlePaddle/PP-OCRv5_{model_name}_rec', local_dir=model_path)
            except Exception as e:
                # Fallback to v4 if v5 server is not found? Or just let it fail?
                # For now let's assume v5 exists or user will configure to v4 if needed.
                # But wait, hardcoded PP-OCRv5 in code.
                # If user wants server, and v5 server doesn't exist, we might be in trouble.
                # Let's just try to download what is requested.
                raise e
            
            det_model_path = os.path.join(model_root, f"PP-OCRv5_{model_name}_det")
            snapshot_download(f'PaddlePaddle/PP-OCRv5_{model_name}_det', local_dir=det_model_path)
            return model_path
        
        # model_downloader.register_model("ocr", check_ocr_model, download_ocr_model)


    def detect_text(self, image_bytes: bytes):
        """
        Detect text in image bytes
        """
        # if not model_downloader.is_ready("ocr"):
        #      raise Exception("OCR model is not ready yet. Please try again later.")

        ocr = model_manager.get_model("ocr")

        # nparr = np.frombuffer(image_bytes, np.uint8)
        # img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        #
        # if img is None:
        #     raise ValueError("Invalid image data")

        result = ocr(image_bytes, use_det=True, use_cls=True, use_rec=True)

        parsed_results = []
        parsed_results.append(
            {
                "prunedResult": {
                    "rec_texts": result.txts if result.txts is not None else [],
                    "rec_scores": result.scores if result.scores is not None else [],
                    "rec_polys": result.boxes.tolist() if result.boxes is not None else [],
                },
            }
        )
        return parsed_results

ocr_service = OCRService()
