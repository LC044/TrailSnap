import time
import threading
import logging
import gc

logger = logging.getLogger(__name__)

class ModelWrapper:
    def __init__(self, name, load_func, release_func=None):
        self.name = name
        self.load_func = load_func
        self.release_func = release_func
        self.model = None
        self.last_used = 0
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
        self.releasing = False

    def get(self):
        with self.condition:
            while self.releasing:
                self.condition.wait()
            self.last_used = time.time()
            if self.model is None:
                logger.info(f"Loading model: {self.name}")
                self.model = self.load_func()
            return self.model

    def _release_locked(self):
        if self.model is not None:
            logger.info(f"Releasing model: {self.name}")

            # Custom release logic if provided
            if self.release_func:
                try:
                    self.release_func(self.model)
                except Exception as e:
                    logger.error(f"Error in release function for {self.name}: {e}")
            # Attempt to clear CUDA cache if torch is available (Global fallback)
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass
            del self.model
            self.model = None
            gc.collect()

    def release(self):
        with self.condition:
            while self.releasing:
                self.condition.wait()
            self._release_locked()

    def release_async(self):
        """Release in the background while preventing callers from using the old model."""
        with self.condition:
            if self.model is None or self.releasing:
                return False
            self.releasing = True

        def worker():
            with self.condition:
                try:
                    self._release_locked()
                finally:
                    self.releasing = False
                    self.condition.notify_all()

        threading.Thread(target=worker, daemon=True, name=f"release-{self.name}").start()
        return True

class ModelManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ModelManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, idle_timeout=300):
        if self._initialized:
            return
        self.models = {}
        self.idle_timeout = idle_timeout
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        self._initialized = True

    def register_model(self, name, load_func, release_func=None):
        self.models[name] = ModelWrapper(name, load_func, release_func)

    def get_model(self, name):
        if name not in self.models:
            raise ValueError(f"Model {name} not registered")
        return self.models[name].get()

    def _monitor_loop(self):
        while self.running:
            time.sleep(10) # Check every minute
            now = time.time()
            for name, wrapper in self.models.items():
                # print(name, wrapper.last_used, now - wrapper.last_used, wrapper.model)
                # Check without lock first to avoid contention
                if wrapper.model is not None:
                    # Double check inside lock
                    if wrapper.model is not None and (now - wrapper.last_used > self.idle_timeout):
                        wrapper.release()

model_manager = ModelManager()
