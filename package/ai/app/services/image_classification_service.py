import traceback
import logging
import os
import io
import base64
from typing import List, Dict, Optional
from PIL import Image

import json
import numpy as np

from app.config import settings
from app.services.model_downloader import model_downloader
from app.services.model_manager import model_manager

class ONNXModelWrapper:
    def __init__(self, model_path):
        import onnxruntime as ort
        import ast
        self.session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider', 'CUDAExecutionProvider'])
        meta = self.session.get_modelmeta()
        names_str = meta.custom_metadata_map.get('names', '{}')
        try:
            names_dict = ast.literal_eval(names_str)
            self.names = {int(k): v for k, v in names_dict.items()}
        except Exception:
            self.names = {}
        
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name
        self.model_name = os.path.basename(model_path)
        
        input_shape = self.session.get_inputs()[0].shape
        self.input_size = input_shape[2] if len(input_shape) == 4 else 224

    def _preprocess(self, image: Image.Image):
        # Resize shorter side to input_size
        w, h = image.size
        if w < h:
            new_w = self.input_size
            new_h = int(self.input_size * h / w)
        else:
            new_h = self.input_size
            new_w = int(self.input_size * w / h)
        
        img = image.resize((new_w, new_h), Image.Resampling.BILINEAR)
        
        # Center crop
        left = (new_w - self.input_size) / 2
        top = (new_h - self.input_size) / 2
        right = (new_w + self.input_size) / 2
        bottom = (new_h + self.input_size) / 2
        img = img.crop((left, top, right, bottom))
        
        img_array = np.array(img).astype(np.float32) / 255.0
        if len(img_array.shape) == 2:
            img_array = np.stack([img_array]*3, axis=-1)
        elif img_array.shape[2] == 4:
            img_array = img_array[:, :, :3]
            
        img_array = img_array.transpose(2, 0, 1)
        return img_array

    def __call__(self, images):
        is_single = False
        if isinstance(images, Image.Image):
            images = [images]
            is_single = True
            
        results = []
        for img in images:
            input_tensor = self._preprocess(img)
            # Expand dims to create a batch of 1 (1, C, H, W)
            input_tensor = np.expand_dims(input_tensor, axis=0)
            outputs = self.session.run([self.output_name], {self.input_name: input_tensor})[0]
            # outputs shape is usually (1, num_classes), so we take the first element
            results.append(outputs[0])
            
        if is_single:
            return results
        return results

class ImageClassificationService:
    _LABEL_TO_CHINESE: Dict[str, str] = {
        "animal": "动物",
        "dog": "狗",
        "cat": "猫",
        "bird": "鸟",
        "person": "人像",
        "children": "儿童",
        "people": "人像",
        "selfie": "自拍",
        "scenery": "风景",
        "architecture": "建筑",
        "sunset": "日出日落",
        "night": "夜景",
        "moon": "月亮",
        "document": "文档",
        "chat_message": "聊天消息",
        "id_card": "卡证",
        "train_ticket": "火车票",
        "train_ticket_screenshot": "火车票截图",
        "flight_ticket_screenshot": "机票截图",
        "movie_ticket": "电影票",
        "movie_ticket_screenshot": "电影票截图",
        "food": "美食",
        "car": "汽车",
        "plant": "植物",
        "electronics": "电子产品",
        "ski": "滑雪"
    }

    def __init__(self):
        self._category_model_map = self._discover_category_models()
        self._register_models()
        self._register_downloads()
        self.version = 'v0.3.10.1'

    def _translate_label(self, label: str) -> str:
        return self._LABEL_TO_CHINESE.get(label, label)

    def _discover_category_models(self) -> Dict[str, str]:
        path = os.path.join(settings.MODEL_PATH, "photo-cls")
        if not os.path.exists(path):
            return {}
        category_map = {}
        for f in os.listdir(path):
            if f.startswith("photo-cls-") and f.endswith(".onnx") and f != "photo-cls-general.onnx":
                category = f.replace("photo-cls-", "").replace(".onnx", "")
                category_map[category] = f
        return category_map

    def _register_downloads(self):

        def check_general_model():
            try:
                path = os.path.join(settings.MODEL_PATH, "photo-cls")
                if not os.path.exists(path):
                    return False
                model_path = os.path.join(path, "photo-cls-general.onnx")
                if not os.path.exists(model_path):
                    return False
                version_file = os.path.join(path, ".mv")
                if not os.path.exists(version_file):
                    return False
                with open(version_file, 'r') as f:
                    version = f.read().strip().split(',')[0].split(':')[1]
                if version != self.version:
                    return False
                return True
            except:
                return False

        def download_general_model():
            path = os.path.join(settings.MODEL_PATH, "photo-cls")
            from modelscope.hub.snapshot_download import snapshot_download
            logging.info(f"Downloading ONNX model SiYuan044/photo-cls to {path}...")
            return snapshot_download('SiYuan044/photo-cls', local_dir=path, revision=self.version)

        model_downloader.register_model("yolo_photo_cls_general", check_general_model, download_general_model)

        for category, model_file in self._category_model_map.items():
            model_key = f"yolo_photo_cls_{category}"

            def make_check(model_file=model_file):
                def check():
                    try:
                        path = os.path.join(settings.MODEL_PATH, "photo-cls")
                        model_path = os.path.join(path, model_file)
                        return os.path.exists(model_path)
                    except:
                        return False
                return check

            def make_download(model_file=model_file):
                def download():
                    return os.path.join(settings.MODEL_PATH, "photo-cls", model_file)
                return download

            model_downloader.register_model(model_key, make_check(), make_download())

    def _load_general_model(self):
        path = os.path.join(settings.MODEL_PATH, "photo-cls")
        model_path = os.path.join(path, "photo-cls-general.onnx")
        if not os.path.exists(model_path):
            pt_files = [f for f in os.listdir(path) if f.endswith('.onnx') and 'general' in f]
            if pt_files:
                model_path = os.path.join(path, pt_files[0])
            else:
                raise FileNotFoundError(f"No general model found in {path}")
        logging.info(f"Loading ONNX general model from {model_path}")
        return ONNXModelWrapper(model_path)

    def _load_category_model(self, category: str):
        model_file = self._category_model_map.get(category)
        if not model_file:
            return None
        path = os.path.join(settings.MODEL_PATH, "photo-cls")
        model_path = os.path.join(path, model_file)
        if not os.path.exists(model_path):
            return None
        logging.info(f"Loading ONNX {category} model from {model_path}")
        return ONNXModelWrapper(model_path)

    def _release_model(self, wrapper):
        model_name = getattr(wrapper, 'model_name', 'unknown')
        logging.info(f"Releasing resources for {model_name}")

        if hasattr(wrapper, 'session'):
            del wrapper.session
        import gc
        gc.collect()

    def _register_models(self):
        model_manager.register_model("yolo_photo_cls_general", self._load_general_model, self._release_model)
        for category in self._category_model_map.keys():
            model_manager.register_model(f"yolo_photo_cls_{category}", lambda c=category: self._load_category_model(c), self._release_model)

    def _get_top_prediction(self, probs, model):
        if probs is not None and len(probs) > 0:
            cls_idx = np.argmax(probs)
            conf = probs[cls_idx]
            return model.names.get(cls_idx, str(cls_idx)), float(conf)
        return None, None

    def _normalize_label(self, label: Optional[str], confidence: float) -> str:
        if label is None or confidence < 0.7:
            return "others"
        return label

    def _classify_single(self, image: Image.Image):
        general_model = model_manager.get_model("yolo_photo_cls_general")
        general_pred = general_model(image)[0]
        big_category, confidence = self._get_top_prediction(general_pred, general_model)
        big_category = self._normalize_label(big_category, confidence)

        if big_category == "others":
            return {"label": "others", "confidence": confidence}

        small_model_key = f"yolo_photo_cls_{big_category}"
        if big_category in self._category_model_map and model_downloader.is_ready(small_model_key):
            small_model = model_manager.get_model(small_model_key)
            small_pred = small_model(image)[0]
            final_label, final_conf = self._get_top_prediction(small_pred, small_model)
            final_label = self._normalize_label(final_label, final_conf)
            return {"label": final_label, "confidence": final_conf}

        return {"label": big_category, "confidence": confidence}

    async def classify_yolo(self, images_base64: List[str]) -> List[dict]:
        if not model_downloader.is_ready("yolo_photo_cls_general"):
            raise Exception("General model is not ready yet. Please try again later.")

        results = []
        valid_images = []
        valid_indices = []

        for idx, b64 in enumerate(images_base64):
            try:
                if ',' in b64:
                    b64 = b64.split(',')[1]
                image_data = base64.b64decode(b64)
                image = Image.open(io.BytesIO(image_data)).convert("RGB")
                valid_images.append(image)
                valid_indices.append(idx)
                results.append({"status": "success", "predictions": []})
            except Exception as e:
                logging.error(f"Image decode error: {e}")
                results.append({"status": "error", "error": str(e)})

        if not valid_images:
            return results

        general_model = model_manager.get_model("yolo_photo_cls_general")
        preds_batch = general_model(valid_images)

        category_groups: Dict[str, List[int]] = {}
        final_results: Dict[int, dict] = {}

        for res_idx, pred in enumerate(preds_batch):
            idx = valid_indices[res_idx]
            big_category, confidence = self._get_top_prediction(pred, general_model)
            normalized_label = self._normalize_label(big_category, confidence)

            if normalized_label == "others":
                final_results[idx] = {"label": "others", "confidence": confidence}
            else:
                if normalized_label not in category_groups:
                    category_groups[normalized_label] = []
                category_groups[normalized_label].append((idx, res_idx))

        for category, indices in category_groups.items():
            small_model_key = f"yolo_photo_cls_{category}"
            if category in self._category_model_map and model_downloader.is_ready(small_model_key):
                small_model = model_manager.get_model(small_model_key)
                group_images = [valid_images[i[1]] for i in indices]
                small_preds = small_model(group_images)

                for i, small_pred in enumerate(small_preds):
                    idx = indices[i][0]
                    final_label, final_conf = self._get_top_prediction(small_pred, small_model)
                    final_label = self._normalize_label(final_label, final_conf)
                    # final_results[idx] = {"label": category + '_' + self._translate_label(final_label), "confidence": final_conf}
                    final_results[idx] = {"label": self._translate_label(final_label), "confidence": final_conf}
            else:
                for i in indices:
                    idx = i[0]
                    final_results[idx] = {"label": self._translate_label(category), "confidence": 0.9}

        for idx, result in final_results.items():
            result["label"] = self._translate_label(result["label"])
            results[idx]["predictions"] = [result]

        return results

image_classification_service = ImageClassificationService()
