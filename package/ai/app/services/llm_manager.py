import asyncio
import time
import logging
import sys
import os
import subprocess
import shutil
import httpx
from app.config import settings
from app.services.unified_model_manager import ai_model_manager

logger = logging.getLogger(__name__)


class LLMModelNotReadyError(ValueError):
    def __init__(self, status: str, error: str | None = None):
        self.status = status
        self.download_error = error
        if status == "failed":
            message = f"LLM model download failed; model_status=failed; error={error or 'unknown error'}"
        else:
            message = f"LLM model is downloading; model_status=downloading; please try again later"
        super().__init__(message)


class LLMProcessManager:
    def __init__(self):
        self.process = None
        self.last_access_time = time.time()
        self.port = settings.LLM_SERVER_PORT
        self.lock = asyncio.Lock()
        self.active_model_id = None

    def _get_resolved_model_path(self) -> tuple[str, str]:
        # If user explicitly set LLM_MODEL_PATH in env, use it directly
        if settings.LLM_MODEL_PATH and os.path.exists(settings.LLM_MODEL_PATH):
            return settings.LLM_MODEL_PATH, ""
            
        spec = ai_model_manager.get_selected_spec("llm")
        base = ai_model_manager.get_model_dir("llm", task=True)
        gguf_files = [base / item for item in spec.get("requiredFiles", []) if item.endswith(".gguf")]
        model_path = next((item for item in gguf_files if "mmproj" not in item.name.lower()), None)
        mmproj = next((item for item in gguf_files if "mmproj" in item.name.lower()), None)
        return str(model_path) if model_path else "", str(mmproj) if mmproj else ""

    async def ensure_running(self):
        self.last_access_time = time.time()
        
        # Ensure model is downloaded and ready
        if not settings.LLM_MODEL_PATH and not ai_model_manager.is_ready("llm"):
            state = ai_model_manager.get_download_state("llm", task=True)
            if state["status"] == "pending":
                ai_model_manager.trigger_download(state["model_id"])
                state = {**state, "status": "downloading"}
            raise LLMModelNotReadyError(state["status"], state["error"])
            
        resolved_path, mmproj = self._get_resolved_model_path()
        if not resolved_path:
            raise ValueError("LLM model file (.gguf) not found in the downloaded directory.")
            
        async with self.lock:
            selected_model_id = "external" if settings.LLM_MODEL_PATH else ai_model_manager.get_selected_id("llm")
            # Check if process is already running
            if self.process is not None and self.process.poll() is None:
                if self.active_model_id == selected_model_id:
                    return
                logger.info(
                    "Selected LLM changed from %s to %s; restarting subprocess",
                    self.active_model_id,
                    selected_model_id,
                )
                await self._stop_unlocked()
            
            logger.info(f"Starting llama.cpp server subprocess on port {self.port} with model {resolved_path}...")
            # Docker resolves llama-server from PATH; desktop passes the path
            # detected or installed by the Tauri shell.
            command = [self._llama_server_executable(), "-m", resolved_path]
            if mmproj:
                command.extend(["--mmproj", mmproj])
            command.extend([
                "--host", "127.0.0.1",
                "--port", str(self.port),
                "--image-min-tokens", "1024",
                "--image-max-tokens", "2048",
                "-c", "8192",
                "-n", "1024",
                "--no-webui",
            ])
            self.process = subprocess.Popen(
                command,
                stdout=sys.stdout,
                stderr=sys.stderr
            )
            self.active_model_id = selected_model_id
            await self._wait_for_ready()

    @staticmethod
    def _llama_server_executable():
        configured = os.getenv("LLAMA_SERVER_PATH")
        if configured and os.path.isfile(configured):
            return configured
        discovered = shutil.which("llama-server")
        if discovered:
            return discovered
        raise RuntimeError(
            "llama-server 未安装。请在桌面端 AI 扩展设置中安装 llama.cpp，"
            "或按照 package/ai/README.md 完成安装。"
        )

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
        await self._stop_unlocked()
        raise RuntimeError("LLM server failed to start or load model within timeout.")

    async def stop(self):
        async with self.lock:
            await self._stop_unlocked()

    async def _stop_unlocked(self):
        if self.process and self.process.poll() is None:
            logger.info("Stopping llama.cpp server to free memory...")
            self.process.terminate()

            # Wait up to 5 seconds
            start_time = time.time()
            while time.time() - start_time < 5.0:
                if self.process.poll() is not None:
                    break
                await asyncio.sleep(0.1)

            if self.process.poll() is None:
                logger.warning("Force killing llama.cpp server...")
                self.process.kill()
                self.process.wait()
        self.process = None
        self.active_model_id = None
        logger.info("llama.cpp server stopped successfully.")

    async def idle_checker(self):
        """Background task to monitor idle time and shut down the server."""
        while True:
            await asyncio.sleep(10)
            if self.process and self.process.poll() is None:
                idle_duration = time.time() - self.last_access_time
                if idle_duration > settings.LLM_IDLE_TIMEOUT:
                    logger.info(f"LLM server idle for {idle_duration:.0f}s (limit: {settings.LLM_IDLE_TIMEOUT}s). Shutting down.")
                    await self.stop()

llm_manager = LLMProcessManager()
