"""Initialize optional railway reference data without blocking authentication."""

import logging
import os
import threading
from pathlib import Path

from fastapi import HTTPException

logger = logging.getLogger(__name__)
_state = "pending"
_thread = None
_lock = threading.Lock()


def get_initialization_state():
    return _state


def require_ready():
    if _state != "ready":
        message = (
            "铁路数据初始化失败，请检查服务器日志并重启服务重试"
            if _state == "failed" else "铁路数据正在初始化，请稍后重试"
        )
        raise HTTPException(status_code=503, detail=message, headers={"Retry-After": "5"})


def _initialize():
    global _state
    try:
        # Serialize workers sharing a data directory. OS locks are released even
        # when the process exits halfway through an import.
        from app.core.paths import DATA_DIR
        lock_path = Path(DATA_DIR) / "railway-seed.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as lock_file:
            if os.name == "nt":
                import msvcrt
                import time
                lock_file.write(b"\0")
                lock_file.flush()
                while True:
                    lock_file.seek(0)
                    try:
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        time.sleep(1)
            else:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                from railway.start import create_database
                create_database()
                from railway.history_seed import ensure_history_seed
                ensure_history_seed()
            finally:
                if os.name == "nt":
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        _state = "ready"
        logger.info("Railway reference data is ready")
    except Exception:
        _state = "failed"
        logger.exception("Railway initialization failed; authentication remains available")


def start_background_initialization():
    global _thread, _state
    with _lock:
        if _thread is not None and _thread.is_alive():
            return
        if _state == "ready":
            return
        _state = "pending"
        _thread = threading.Thread(target=_initialize, name="railway-initialization", daemon=True)
        _thread.start()


def wait_for_initialization():
    """Finish database writes before the desktop data directory is copied."""
    with _lock:
        thread = _thread
    if thread is not None:
        thread.join()
