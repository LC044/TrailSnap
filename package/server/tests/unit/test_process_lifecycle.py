"""Real process tests: kill the owner, including while work is blocked."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil
import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


HELPER = '''
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import time

from app.utils.process_lifecycle import bind_desktop_process_tree, watch_worker_parent


def work(ready, watch):
    if watch:
        watch_worker_parent()
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    record = Path(ready)
    temporary = record.with_suffix(".tmp")
    temporary.write_text(json.dumps([os.getpid(), child.pid]))
    temporary.replace(record)
    # Simulate blocked inference/executor threads; no asyncio cooperation.
    time.sleep(120)


if __name__ == "__main__":
    mode, ready, exit_file = sys.argv[1:]
    if mode == "job":
        bind_desktop_process_tree()
        bind_desktop_process_tree()  # Safe to call twice.
        # A second level proves all descendants inherit the job.
        worker = multiprocessing.get_context("spawn").Process(target=work, args=(ready, False))
    else:
        worker = multiprocessing.get_context("spawn").Process(target=work, args=(ready, True))
    worker.start()
    while not Path(exit_file).exists():
        time.sleep(0.05)
    os._exit(0)
'''


def _wait_until(check, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.05)
    pytest.fail("Process lifecycle condition did not complete before timeout")


def _has_exited(process):
    try:
        return not process.is_running() or process.status() == psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        # Windows can reap the process between is_running() and status().
        return True


@pytest.mark.parametrize("mode", ["job", "worker"])
@pytest.mark.parametrize("exit_kind", ["terminate", "exit"])
def test_descendants_exit_with_owner(tmp_path, mode, exit_kind):
    if mode == "job" and sys.platform != "win32":
        pytest.skip("Windows Job Object ownership")
    script = tmp_path / "owner.py"
    script.write_text(HELPER, encoding="utf-8")
    ready = tmp_path / "ready.json"
    exit_file = tmp_path / "exit"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    owner = subprocess.Popen(
        [sys.executable, str(script), mode, str(ready), str(exit_file)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    processes = []
    try:
        _wait_until(lambda: ready.exists() or owner.poll() is not None)
        assert owner.poll() is None, owner.stderr.read().decode(errors="replace")
        owner_process = psutil.Process(owner.pid)
        processes = owner_process.children(recursive=True)
        worker_pid, child_pid = json.loads(ready.read_text())
        worker, child = psutil.Process(worker_pid), psutil.Process(child_pid)
        processes = [worker, child]
        time.sleep(0.25)
        assert owner.poll() is None
        assert worker.is_running() and child.is_running()

        if exit_kind == "terminate":
            owner.kill()
        else:
            exit_file.touch()
        owner.wait(timeout=5)
        _wait_until(lambda: all(_has_exited(p) for p in processes))
    finally:
        for process in reversed(processes):
            try:
                process.kill()
            except psutil.NoSuchProcess:
                pass
        if owner.poll() is None:
            owner.kill()
        owner.wait(timeout=5)
        owner.stderr.close()
