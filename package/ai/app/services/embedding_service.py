import traceback
import logging
import os
import io
import base64
from typing import List
from PIL import Image

from app.config import settings
from app.services.model_downloader import model_downloader
from app.services.model_manager import model_manager
from app.services.ai_config_manager import ai_config_manager

class ONNXCLIPTextWrapper:
    def __init__(self, model_dir):
        import onnxruntime as ort
        from modelscope import AutoTokenizer
        import os
        
        self.model_dir = model_dir
        logging.info(f"Loading ONNX Text model from {model_dir}")
        
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        
        providers = ['CPUExecutionProvider', 'CUDAExecutionProvider']
        text_model_path = os.path.join(model_dir, "textual.onnx")
        self.text_session = ort.InferenceSession(text_model_path, providers=providers)

    def encode_text(self, texts: List[str]):
        import numpy as np
        inputs = self.tokenizer(text=texts, return_tensors="np", padding=True, truncation=True, max_length=128)
        
        ort_inputs = {
            self.text_session.get_inputs()[0].name: inputs["input_ids"],
            self.text_session.get_inputs()[1].name: inputs["attention_mask"]
        }
        outputs = self.text_session.run(None, ort_inputs)
        embeddings = outputs[0]
        # Normalize
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        normalized = embeddings / np.maximum(norms, 1e-12)
        return normalized

class ONNXCLIPImageWrapper:
    def __init__(self, model_dir):
        import onnxruntime as ort
        from modelscope import AutoImageProcessor
        import os
        
        self.model_dir = model_dir
        logging.info(f"Loading ONNX Image model from {model_dir}")
        
        self.processor = AutoImageProcessor.from_pretrained(model_dir)
        
        providers = ['CPUExecutionProvider', 'CUDAExecutionProvider']
        vision_model_path = os.path.join(model_dir, "visual.onnx")
        self.vision_session = ort.InferenceSession(vision_model_path, providers=providers)

    def encode_image(self, images: List[Image.Image]):
        import numpy as np
        inputs = self.processor(images=images, return_tensors="np")
        ort_inputs = {
            self.vision_session.get_inputs()[0].name: inputs["pixel_values"]
        }
        outputs = self.vision_session.run(None, ort_inputs)
        embeddings = outputs[0]
        # Normalize
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        normalized = embeddings / np.maximum(norms, 1e-12)
        return normalized

class EmbeddingService:
    def __init__(self):
        self._register_models()
        self._register_downloads()

    def _get_model_info(self):
        selected = ai_config_manager.get_model_selection("classification")
        if selected == "clip-ViT-B-32":
            return {
                "text_model_repo": "SiYuan044/clip-ViT-B-32-multilingual-v1-onnx",
                "image_model_repo": "SiYuan044/clip-ViT-B-32-onnx",
                "text_dir_name": "clip-ViT-B-32-multilingual-v1-onnx",
                "image_dir_name": "clip-ViT-B-32-onnx"
            }
        return {
                "text_model_repo": "SiYuan044/clip-ViT-B-32-multilingual-v1-onnx",
                "image_model_repo": "SiYuan044/clip-ViT-B-32-onnx",
                "text_dir_name": "clip-ViT-B-32-multilingual-v1-onnx",
                "image_dir_name": "clip-ViT-B-32-onnx"
        }

    def _register_downloads(self):
        def check_image_model():
            info = self._get_model_info()
            path = os.path.join(settings.MODEL_PATH, info["image_dir_name"])
            return os.path.exists(path) and len(os.listdir(path)) > 0

        def download_image_model():
            info = self._get_model_info()
            path = os.path.join(settings.MODEL_PATH, info["image_dir_name"])
            from modelscope.hub.snapshot_download import snapshot_download
            logging.info(f"Downloading Image model {info['image_model_repo']} to {path}...")
            return snapshot_download(info['image_model_repo'], local_dir=path)

        def check_text_model():
            info = self._get_model_info()
            path = os.path.join(settings.MODEL_PATH, info["text_dir_name"])
            return os.path.exists(path) and len(os.listdir(path)) > 0

        def download_text_model():
            info = self._get_model_info()
            path = os.path.join(settings.MODEL_PATH, info["text_dir_name"])
            from modelscope.hub.snapshot_download import snapshot_download
            logging.info(f"Downloading Text model {info['text_model_repo']} to {path}...")
            return snapshot_download(info['text_model_repo'], local_dir=path)

        model_downloader.register_model("clip_text", check_text_model, download_text_model)
        model_downloader.register_model("clip_image", check_image_model, download_image_model)

    def _load_text_model(self):
        info = self._get_model_info()
        path = os.path.join(settings.MODEL_PATH, info["text_dir_name"])
        model_name = path if os.path.exists(path) else info["text_model_repo"]
        return ONNXCLIPTextWrapper(model_name)

    def _load_image_model(self):
        info = self._get_model_info()
        path = os.path.join(settings.MODEL_PATH, info["image_dir_name"])
        model_name = path if os.path.exists(path) else info["image_model_repo"]
        return ONNXCLIPImageWrapper(model_name)

    def _release_model(self, wrapper):
        """Release resources associated with the model"""
        model_name = getattr(wrapper, 'model_dir', 'unknown')
        logging.info(f"Releasing resources for {model_name}")
        if hasattr(wrapper, 'text_session'):
            del wrapper.text_session
        if hasattr(wrapper, 'vision_session'):
            del wrapper.vision_session
        if hasattr(wrapper, 'tokenizer'):
            del wrapper.tokenizer
        if hasattr(wrapper, 'processor'):
            del wrapper.processor
        import gc
        gc.collect()

    def _register_models(self):
        model_manager.register_model("clip_text", self._load_text_model, self._release_model)
        model_manager.register_model("clip_image", self._load_image_model, self._release_model)

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not model_downloader.is_ready("clip_text"):
             raise Exception("Models are not ready yet. Please try again later.")
        wrapper = model_manager.get_model("clip_text")
        try:
            # Encode texts
            text_embs = wrapper.encode_text(texts)
            return text_embs.tolist()
        except Exception as e:
            logging.error(f"Error in text embedding: {e}\n{traceback.format_exc()}")
            raise e

    async def embed_images(self, images_base64: List[str]) -> List[List[float]]:
        if not model_downloader.is_ready("clip_image"):
             raise Exception("Models are not ready yet. Please try again later.")
        wrapper = model_manager.get_model("clip_image")
        try:
            images = []
            for b64 in images_base64:
                if ',' in b64:
                    b64 = b64.split(',')[1]
                image_data = base64.b64decode(b64)
                image = Image.open(io.BytesIO(image_data)).convert("RGB")
                images.append(image)
                
            # Encode images
            image_embs = wrapper.encode_image(images)
            return image_embs.tolist()
        except Exception as e:
            logging.error(f"Error in image embedding: {e}\n{traceback.format_exc()}")
            raise e

embedding_service = EmbeddingService()
