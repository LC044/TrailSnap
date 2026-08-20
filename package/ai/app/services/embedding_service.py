import traceback
import logging
import io
import base64
from typing import List
from PIL import Image

from app.services.model_manager import model_manager
from app.services.unified_model_manager import ai_model_manager
from app.services.onnx_providers import create_inference_session

class ONNXCLIPTextWrapper:
    def __init__(self, model_dir):
        from modelscope import AutoTokenizer
        import os

        self.model_dir = model_dir
        logging.info(f"Loading ONNX Text model from {model_dir}")

        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)

        text_model_path = os.path.join(model_dir, "textual.onnx")
        self.text_session = create_inference_session(text_model_path)

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
        from modelscope import AutoImageProcessor
        import os

        self.model_dir = model_dir
        logging.info(f"Loading ONNX Image model from {model_dir}")

        self.processor = AutoImageProcessor.from_pretrained(model_dir)

        vision_model_path = os.path.join(model_dir, "visual.onnx")
        self.vision_session = create_inference_session(vision_model_path)

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

    def _get_model_info(self):
        base = ai_model_manager.get_model_dir("embedding", task=True)
        return {
            "text_path": str(base / "text"),
            "image_path": str(base / "image"),
        }

    def _load_text_model(self):
        info = self._get_model_info()
        return ONNXCLIPTextWrapper(info["text_path"])

    def _load_image_model(self):
        info = self._get_model_info()
        return ONNXCLIPImageWrapper(info["image_path"])

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
        if not ai_model_manager.is_ready("clip_text"):
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
        if not ai_model_manager.is_ready("clip_image"):
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
