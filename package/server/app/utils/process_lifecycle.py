"""Process ownership guards, independent of the API and task event loops."""

import logging
import multiprocessing
import os
import sys
import threading


_desktop_job = None


def bind_desktop_process_tree() -> None:
    """Let Windows reap all descendants even when the API is force-killed.

    Only this process owns the non-inheritable job handle. Windows closes it
    on process death, which kills workers and their pools atomically.
    Call before spawning any desktop backend children.
    """
    global _desktop_job
    if sys.platform != "win32" or _desktop_job is not None:
        return

    import ctypes
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimits),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
    ]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL

    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = 0x00002000  # KILL_ON_JOB_CLOSE
    try:
        if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
            raise ctypes.WinError(ctypes.get_last_error())
    except BaseException:
        kernel.CloseHandle(handle)
        raise
    # Intentionally keep the handle open until process death. Do not pass it
    # to children or close it during Python finalization (it owns us too).
    _desktop_job = handle


def _exit_with_parent(parent) -> None:
    # multiprocessing's parent handle identifies the original process even
    # after PID reuse; waiting here also works if the asyncio loop is blocked.
    parent.join()
    try:
        import psutil

        children = psutil.Process().children(recursive=True)
        for child in reversed(children):
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        psutil.wait_procs(children, timeout=2)
    except Exception:
        logging.exception("Failed to reap worker descendants after parent exit")
    finally:
        # Executor threads can block normal Python/asyncio shutdown forever.
        # The owner is gone, so no further task/database writes are allowed.
        os._exit(1)


def watch_worker_parent() -> None:
    parent = multiprocessing.parent_process()
    if parent is not None:
        threading.Thread(
            target=_exit_with_parent, args=(parent,),
            name="WorkerParentWatch", daemon=True,
        ).start()
