"""CPU safeguards applied before inference libraries are imported."""

import logging
import os
import sys

from app.config import settings


THREAD_ENV_VARS = (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "BLIS_NUM_THREADS",
    "ORT_INTRA_OP_THREADS",
)


def configure_inference_runtime() -> int:
    """Apply one authoritative thread budget to common native runtimes."""
    budget = max(1, settings.AI_INFERENCE_THREADS)
    for name in THREAD_ENV_VARS:
        os.environ[name] = str(budget)
    return budget


def lower_ai_process_priority() -> None:
    if not settings.AI_LOW_PROCESS_PRIORITY:
        return
    try:
        if sys.platform == "win32":
            import psutil

            psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        else:
            os.nice(5)
        logging.getLogger("app.main").info("AI process priority lowered")
    except Exception as exc:
        logging.getLogger("app.main").warning(
            "Unable to lower AI process priority: %s", exc
        )
