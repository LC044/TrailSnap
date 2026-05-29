import os
import json
import logging
from typing import Dict, List, Any
from app.config import settings

class AIConfigManager:
    _instance = None
    _config: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AIConfigManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        # Path relative to app root (app/data)
        # app/services/ai_config_manager.py -> app/services -> app
        self.config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ai_config.json")
        self._load_config()
        self._initialized = True

    def _get_default_config(self):
        return {
            "models": {
                "ocr": {
                    "selected": "mobile",
                    "available": ["mobile", "server"],
                    "description": "Optical Character Recognition models. 'mobile' is faster, 'server' is more accurate."
                },
                "face": {
                    "selected": "buffalo_l",
                    "available": ["buffalo_l"],
                    "description": "Face detection and recognition models."
                },
                "classification": {
                    "selected": "clip-ViT-B-32",
                    "available": ["clip-ViT-B-32"],
                    "description": "Image classification and embedding models."
                }
            }
        }

    def _load_config(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self._config = json.load(f)
                logging.info(f"Loaded AI config from {self.config_path}")
                
                # Merge with defaults to ensure all keys exist
                defaults = self._get_default_config()
                for key, value in defaults["models"].items():
                    if key not in self._config.get("models", {}):
                        if "models" not in self._config:
                            self._config["models"] = {}
                        self._config["models"][key] = value
            else:
                logging.info("AI config file not found, creating default.")
                self._config = self._get_default_config()
                self._save_config()
        except Exception as e:
            logging.error(f"Failed to load AI config: {e}")
            self._config = self._get_default_config()

    def _save_config(self):
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=4, ensure_ascii=False)
            logging.info(f"Saved AI config to {self.config_path}")
        except Exception as e:
            logging.error(f"Failed to save AI config: {e}")

    def get_config(self):
        return self._config

    def get_model_selection(self, task_name: str) -> str:
        """Get the currently selected model for a task."""
        return self._config.get("models", {}).get(task_name, {}).get("selected")

    def set_model_selection(self, task_name: str, model_name: str):
        """Set the selected model for a task. Raises ValueError if invalid."""
        task_config = self._config.get("models", {}).get(task_name)
        if not task_config:
            raise ValueError(f"Unknown task: {task_name}")
        
        if model_name not in task_config.get("available", []):
            raise ValueError(f"Invalid model '{model_name}' for task '{task_name}'. Available: {task_config.get('available')}")

        if task_config["selected"] != model_name:
            task_config["selected"] = model_name
            self._save_config()
            return True # Changed
        return False # Not changed

ai_config_manager = AIConfigManager()
