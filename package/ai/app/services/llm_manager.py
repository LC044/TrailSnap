import asyncio
import time
import logging
import sys
import os
import httpx
from app.config import settings
from app.services.model_downloader import model_downloader

logger = logging.getLogger(__name__)

class LLMProcessManager:
    def __init__(self):
        self.process = None
        self.last_access_time = time.time()
        self.port = settings.LLM_SERVER_PORT
        self.lock = asyncio.Lock()
        # self.repo_id = "SiYuan044/MiniCPM5-1B-Q4_K_M"
        # self.model_dir_name = "MiniCPM5-1B-Q4_K_M"
        self.repo_id = "SiYuan044/MiniCPM-V-4_6-Q4_K_M"
        self.model_dir_name = "MiniCPM-V-4_6-Q4_K_M"
        self.model_name = "MiniCPM-V-4_6-Q4_K_M.gguf"
        self._register_download()

    def _register_download(self):
        def check_model():
            if settings.LLM_MODEL_PATH and os.path.exists(settings.LLM_MODEL_PATH):
                return True
            path = os.path.join(settings.MODEL_PATH, self.model_dir_name)
            # Check if directory exists and contains a .gguf file
            if os.path.exists(path):
                for file in os.listdir(path):
                    if file.endswith(".gguf"):
                        return True
            return False

        def download_model():
            path = os.path.join(settings.MODEL_PATH, self.model_dir_name)
            from modelscope.hub.snapshot_download import snapshot_download
            logger.info(f"Downloading LLM model {self.repo_id} to {path}...")
            # We only need the gguf file, ignore other large files if possible, or just download the whole repo
            return snapshot_download(self.repo_id, local_dir=path, allow_patterns=["*.gguf", "*.json"])

        model_downloader.register_model("llm_minicpm", check_model, download_model)

    def _get_resolved_model_path(self) -> str:
        # If user explicitly set LLM_MODEL_PATH in env, use it directly
        if settings.LLM_MODEL_PATH and os.path.exists(settings.LLM_MODEL_PATH):
            return settings.LLM_MODEL_PATH, ""
            
        path = os.path.join(settings.MODEL_PATH, self.model_dir_name, self.model_name)
        mmproj = os.path.join(settings.MODEL_PATH, self.model_dir_name, "mmproj-model-f16.gguf")

        return path, mmproj

    async def ensure_running(self):
        self.last_access_time = time.time()
        
        # Ensure model is downloaded and ready
        if not model_downloader.is_ready("llm_minicpm"):
            raise ValueError("LLM model is still downloading or not ready. Please try again later.")
            
        resolved_path, mmproj = self._get_resolved_model_path()
        if not resolved_path:
            raise ValueError("LLM model file (.gguf) not found in the downloaded directory.")
            
        async with self.lock:
            # Check if process is already running
            if self.process is not None and self.process.returncode is None:
                return
            
            logger.info(f"Starting llama.cpp server subprocess on port {self.port} with model {resolved_path}...")
            # Use native llama-server binary compiled in Docker
            self.process = await asyncio.create_subprocess_exec(
                "llama-server",
                "-m", resolved_path,
                "--mmproj", mmproj,
                "--host", "127.0.0.1",
                "--port", str(self.port),
                "--image-min-tokens", "1024",
                "--image-max-tokens", "2048",
                "-c","8192",
                "-n","1024",
                "--no-webui",
                stdout=sys.stdout,
                stderr=sys.stderr
            )
            await self._wait_for_ready()

    async def _wait_for_ready(self):
        # Wait until the server is responsive
        async with httpx.AsyncClient() as client:
            for i in range(60): # Wait up to 60 seconds for the model to load into memory
                try:
                    resp = await client.get(f"http://127.0.0.1:{self.port}/v1/models")
                    if resp.status_code == 200:
                        logger.info("llama.cpp server is ready and accepting requests.")
                        return
                except httpx.RequestError:
                    pass
                await asyncio.sleep(1)
                
        logger.error("Timeout waiting for llama.cpp server to start.")
        await self.stop()
        raise RuntimeError("LLM server failed to start or load model within timeout.")

    async def stop(self):
        async with self.lock:
            if self.process and self.process.returncode is None:
                logger.info("Stopping llama.cpp server to free memory...")
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning("Force killing llama.cpp server...")
                    self.process.kill()
                    await self.process.wait()
                self.process = None
                logger.info("llama.cpp server stopped successfully.")

    async def idle_checker(self):
        """Background task to monitor idle time and shut down the server."""
        while True:
            await asyncio.sleep(10)
            if self.process and self.process.returncode is None:
                idle_duration = time.time() - self.last_access_time
                if idle_duration > settings.LLM_IDLE_TIMEOUT:
                    logger.info(f"LLM server idle for {idle_duration:.0f}s (limit: {settings.LLM_IDLE_TIMEOUT}s). Shutting down.")
                    await self.stop()

llm_manager = LLMProcessManager()
