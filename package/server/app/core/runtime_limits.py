"""Early process-level CPU safeguards for background task workers."""

import logging
import os
import sys


THREAD_ENV_VARS = (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "BLIS_NUM_THREADS",
)


def compute_thread_budget(cpu_count: int | None = None) -> int:
    cores = max(1, cpu_count or os.cpu_count() or 1)
    reserved = max(1, int(os.getenv("TASK_RESERVED_CPU_CORES", "1")))
    default = max(1, min(4, cores - reserved))
    return max(1, int(os.getenv("TASK_COMPUTE_THREADS", str(default))))


def configure_worker_runtime() -> int:
    """Limit native math libraries before task modules import NumPy/OpenCV."""
    budget = compute_thread_budget()
    for name in THREAD_ENV_VARS:
        os.environ[name] = str(budget)
    return budget


def lower_worker_priority() -> None:
    """Keep the API process responsive while the worker is CPU saturated."""
    try:
        if sys.platform == "win32":
            import psutil

            psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        else:
            os.nice(5)
        logging.info("Background task worker process priority lowered")
    except Exception as exc:
        logging.warning("Unable to lower task worker priority: %s", exc)
