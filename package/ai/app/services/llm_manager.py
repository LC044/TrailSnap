import asyncio
import time
import logging
import sys
import os
import subprocess
import shutil
from pathlib import Path
import httpx
from app.config import settings
from app.services.desktop_device import record_session
from app.services.onnx_providers import desktop_npu_device
from app.services.unified_model_manager import ai_model_manager

logger = logging.getLogger(__name__)


def _available_cpu_count(cgroup_root: Path = Path("/sys/fs/cgroup")) -> int:
    """Count CPUs available to this container, including a cgroup quota."""
    counts = [max(1, os.cpu_count() or 1)]
    if hasattr(os, "sched_getaffinity"):
        try:
            counts.append(max(1, len(os.sched_getaffinity(0))))
        except OSError:
            pass

    quota_files = (
        (cgroup_root / "cpu.max", None),
        (cgroup_root / "cpu/cpu.cfs_quota_us", cgroup_root / "cpu/cpu.cfs_period_us"),
    )
    for quota_path, period_path in quota_files:
        try:
            if period_path is None:
                quota, period = quota_path.read_text().split()[:2]
            else:
                quota, period = quota_path.read_text().strip(), period_path.read_text().strip()
            if quota != "max" and int(quota) > 0 and int(period) > 0:
                counts.append(max(1, int(quota) // int(period)))
                break
        except (OSError, ValueError, IndexError):
            continue
    return max(1, min(counts))


def _llama_thread_count() -> int:
    """Use at least three threads when available, scaling with larger CPUs."""
    override = os.getenv("LLAMA_ARG_THREADS", "").strip()
    if override:
        threads = int(override)
        if threads < 1:
            raise ValueError("LLAMA_ARG_THREADS must be a positive integer")
        return threads
    available = _available_cpu_count()
    return min(available, max(3, (available + 1) // 2))


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
        self.startup_attempts = 60

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
            threads = _llama_thread_count()
            selected_npu = desktop_npu_device()
            # The V4.6 projector/decoder combination resets the NPU on the
            # current OpenVINO llama.cpp runtime. Keep multimodal GGUF on its
            # existing runtime while allowing the text-only model on NPU.
            if selected_npu and mmproj:
                record_session(resolved_path, [], "当前 llama.cpp OpenVINO NPU 运行时未通过 MiniCPM-V 多模态推理验证")
            npu = selected_npu if not mmproj else None
            if npu:
                env = dict(os.environ, GGML_OPENVINO_DEVICE=npu, GGML_OPENVINO_ENABLE_FALLBACK="0")
                try:
                    executable = self._llama_npu_executable()
                    device = await asyncio.to_thread(self._llama_npu_backend, executable, env)
                except Exception as error:
                    record_session(resolved_path, [], str(error))
                    raise
                accelerator_args = ["--device", device, "--gpu-layers", "all", "--parallel", "1"]
            else:
                executable = self._llama_server_executable()
                env = None
                accelerator_args = []
            command = [executable, "-m", resolved_path, "--threads", str(threads), *accelerator_args]
            logger.info("llama.cpp CPU threads: %s (available: %s)", threads, _available_cpu_count())
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
                stdin=subprocess.DEVNULL,
                stdout=sys.stdout,
                stderr=sys.stderr,
                **({"env": env} if env is not None else {}),
                **({"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}),
            )
            self.active_model_id = selected_model_id
            self.startup_attempts = 240 if npu else 60
            try:
                await self._wait_for_ready()
            except Exception as error:
                if npu:
                    record_session(resolved_path, [], str(error))
                raise
            if npu:
                record_session(resolved_path, ["llama.cpp OpenVINO NPU"])

    @classmethod
    def _llama_npu_executable(cls):
        managed_dir = os.getenv("TS_LLAMA_RUNTIME_DIR")
        if managed_dir:
            folder = Path(managed_dir)
            executable = "llama-server.exe" if sys.platform == "win32" else "llama-server"
            alternate = folder.with_name(f"{folder.name}-openvino-npu")
            for candidate in alternate.rglob(executable):
                if candidate.is_file():
                    return str(candidate)
        return cls._llama_server_executable()

    @staticmethod
    def _llama_npu_backend(executable, env):
        result = subprocess.run(
            [executable, "--list-devices"],
            env=env, capture_output=True, timeout=25, text=True, encoding="utf-8", errors="replace",
            **({"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}),
        )
        if result.returncode == 0:
            selected = f"GGML_OPENVINO_DEVICE={env['GGML_OPENVINO_DEVICE']} (selected)"
            for line in (result.stdout + "\n" + result.stderr).splitlines():
                name, _, description = line.strip().partition(":")
                if name.startswith("OPENVINO") and description.strip().startswith(selected):
                    return name
        raise RuntimeError("llama.cpp 未检测到所选 NPU，请安装支持 OpenVINO NPU 的运行时")

    @staticmethod
    def _llama_server_executable():
        configured = os.getenv("LLAMA_SERVER_PATH")
        if configured and os.path.isfile(configured):
            return configured
        # The desktop may prepare its private runtime after this AI process has
        # started. Resolve it on each inference instead of requiring a restart.
        managed_dir = os.getenv("TS_LLAMA_RUNTIME_DIR")
        desktop_root = os.getenv("TS_DESKTOP_ROOT")
        if managed_dir or desktop_root:
            executable = "llama-server.exe" if sys.platform == "win32" else "llama-server"
            if managed_dir:
                candidates = sorted(Path(managed_dir).rglob(executable))
            else:
                runtime = Path(desktop_root) / "runtime" / "llama.cpp"
                candidates = sorted(runtime.glob(f"*/**/{executable}"), reverse=True)
            for candidate in candidates:
                if candidate.is_file():
                    return str(candidate)
        if not managed_dir:
            discovered = shutil.which("llama-server")
            if discovered:
                return discovered
        raise RuntimeError(
            "本地推理环境尚未准备完成，请重试；独立部署请按照 AI 服务文档安装 llama.cpp。"
        )

    async def _wait_for_ready(self):
        # Wait until the server is responsive
        async with httpx.AsyncClient() as client:
            for _ in range(self.startup_attempts):
                try:
                    resp = await client.get(f"http://127.0.0.1:{self.port}/v1/models")
                    if resp.status_code == 200:
                        logger.info("llama.cpp server is ready and accepting requests.")
                        return
                except httpx.RequestError:
                    pass
                if self.startup_attempts > 60 and self.process is not None and self.process.poll() is not None:
                    exit_code = self.process.returncode
                    await self._stop_unlocked()
                    raise RuntimeError(f"llama.cpp NPU 进程在模型启动时退出，退出码 {exit_code}")
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
