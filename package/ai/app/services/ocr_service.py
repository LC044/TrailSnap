import numpy as np
import cv2
import logging
import sys
import threading
from contextlib import contextmanager
from app.services.model_manager import model_manager
from app.services.unified_model_manager import ai_model_manager

# OpenVINO 的 InferRequest.infer() 是同步且非线程安全的：同一 RapidOCR 实例被多个
# 线程并发调用会抛 "Infer Request is busy"（router 里 ThreadPoolExecutor 会并发跑
# 多张图）。ONNX Runtime / Torch 的 session.run 是线程安全的，无需加锁。这里只对
# OpenVINO 后端串行化推理；LATENCY 模式下单次推理已用 intra-op 线程吃满 CPU，串行
# 不损失吞吐，反而避免线程 oversubscription。
_ocr_infer_lock = threading.Lock()
# load_paddleocr_model 中根据实际选中的引擎置位，detect_text / ticket_service 据此
# 决定是否加锁。注意：必须在 model_manager.get_model("ocr") 触发模型加载之后读取，
# 否则标志位尚未被置位。
_ocr_engine_is_openvino = False


@contextmanager
def openvino_infer_lock():
    """
    OpenVINO 后端串行化推理的上下文管理器，供所有共享同一 RapidOCR 实例的调用方使用
    （ocr_service.detect_text、ticket_service.detect）。非 OpenVINO 后端为 no-op，
    不影响 ONNX Runtime / Torch 的并发吞吐。
    """
    if _ocr_engine_is_openvino:
        with _ocr_infer_lock:
            yield
    else:
        yield


def load_paddleocr_model():
    global _ocr_engine_is_openvino
    try:
        from rapidocr import EngineType, LangDet, LangRec, ModelType, OCRVersion, RapidOCR
        spec = ai_model_manager.get_selected_spec("ocr")
        variant = spec["runtimeName"]
        base = ai_model_manager.get_model_dir("ocr", task=True)
        model_type = ModelType.MOBILE if variant == "mobile" else ModelType.SERVER
        det_path = base / f"onnx/PP-OCRv5/det/ch_PP-OCRv5_det_{variant}.onnx"
        rec_path = base / f"onnx/PP-OCRv5/rec/ch_PP-OCRv5_rec_{variant}.onnx"
        cls_name = (
            "ch_PP-LCNet_x0_25_textline_ori_cls_mobile.onnx"
            if variant == "mobile"
            else "ch_PP-LCNet_x1_0_textline_ori_cls_server.onnx"
        )
        params = {
            "Det.engine_type": EngineType.ONNXRUNTIME,
            "Det.lang_type": LangDet.CH,
            "Det.model_type": model_type,
            "Det.ocr_version": OCRVersion.PPOCRV5,
            "Det.model_path": det_path,
            "Cls.engine_type": EngineType.ONNXRUNTIME,
            "Cls.model_type": model_type,
            "Cls.ocr_version": OCRVersion.PPOCRV5,
            "Cls.model_path": base / "onnx/PP-OCRv5/cls" / cls_name,
            "Rec.engine_type": EngineType.ONNXRUNTIME,
            "Rec.lang_type": LangRec.CH,
            "Rec.model_type": model_type,
            "Rec.ocr_version": OCRVersion.PPOCRV5,
            "Rec.model_path": rec_path,
            "EngineConfig.onnxruntime.use_cuda": True,
        }
        _ocr_engine_is_openvino = False
        try:
            from openvino import Core  # noqa: F401

            params.update({
                "Det.engine_type": EngineType.OPENVINO,
                "Cls.engine_type": EngineType.OPENVINO,
                "Rec.engine_type": EngineType.OPENVINO,
                "EngineConfig.openvino": {
                    "performance_hint": "LATENCY",
                    "inference_num_threads": -1,
                    "enable_cpu_pinning": True,
                    "num_infer_requests": 1,
                },
            })
            _ocr_engine_is_openvino = True
        except ImportError:
            pass
        ocr = RapidOCR(
            params=params,
        )
        logging.info(
            "PaddleOCR model initialized successfully. "
            f"openvino_backend={_ocr_engine_is_openvino}"
        )
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
    def detect_text(self, image_bytes: bytes):
        """
        Detect text in image bytes
        """
        if not ai_model_manager.is_ready("ocr"):
            raise Exception("OCR model is not ready yet. Please try again later.")
        ocr = model_manager.get_model("ocr")

        # nparr = np.frombuffer(image_bytes, np.uint8)
        # img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        #
        # if img is None:
        #     raise ValueError("Invalid image data")

        # OpenVINO InferRequest 非线程安全，并发推理会抛 "Infer Request is busy"，
        # 通过 openvino_infer_lock() 串行化；其它引擎（ONNX Runtime / Torch）session
        # 线程安全，锁为 no-op。
        with openvino_infer_lock():
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
