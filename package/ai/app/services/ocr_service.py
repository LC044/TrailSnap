import numpy as np
import cv2
import logging
import sys
import os
import threading
from contextlib import contextmanager
from app.config import settings
from app.services.model_downloader import model_downloader
from app.services.model_manager import model_manager
from app.services.ai_config_manager import ai_config_manager

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
        # 引擎优先级：CUDA(TORCH) > OpenVINO > ONNX Runtime(CPU)。
        # OCR 走 RapidOCR 自己的引擎配置口，不经过 onnx_providers.get_onnx_providers()，
        # 因此这里手动探测 OpenVINO extra 是否安装以切换引擎（人脸 / 分类 / 票据 /
        # embedding 走 onnxruntime EP，受 get_onnx_providers() 统一管理）。
        params = {
            "Det.engine_type": EngineType.ONNXRUNTIME,
            "Det.lang_type": LangDet.CH,
            "Det.model_type": ModelType.MOBILE,
            "Det.ocr_version": OCRVersion.PPOCRV5,
            "Rec.engine_type": EngineType.ONNXRUNTIME,
            "Rec.lang_type": LangRec.CH,
            "Rec.model_type": ModelType.MOBILE,
            "Rec.ocr_version": OCRVersion.PPOCRV5,
            "EngineConfig.onnxruntime.use_cuda": True,
        }
        use_torch_gpu = False
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
                use_torch_gpu = True
        except ImportError:
            pass
        _ocr_engine_is_openvino = False
        # 无 GPU 时优先 OpenVINO（openvino extra 安装即启用，CPU/NPU 上通常比
        # ONNX Runtime 更快）。OpenVINO InferRequest 非线程安全，detect_text 中
        # 用 _ocr_infer_lock 串行化推理以支持并发请求。
        if not use_torch_gpu:
            try:
                from openvino import Core  # noqa: F401  仅用于探测 extra 是否安装

                params.update(
                    {
                        "Det.engine_type": EngineType.OPENVINO,
                        "Cls.engine_type": EngineType.OPENVINO,
                        "Rec.engine_type": EngineType.OPENVINO,
                        "EngineConfig.openvino": {
                            "performance_hint": "LATENCY",  # LATENCY低延迟 / THROUGHPUT高吞吐
                            "inference_num_threads": -1,
                            "enable_cpu_pinning": True,
                            # 推理已被 _ocr_infer_lock 串行化，单请求即可；多于 1 无收益
                            "num_infer_requests": 1,
                        },
                    }
                )
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
