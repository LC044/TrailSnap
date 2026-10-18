"""Native startup UI against a frozen backend and a synthetic historical library."""
from contextlib import closing
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
import uuid

import pytest

from app.utils.portable_library import file_hash

pytestmark = [pytest.mark.module_automatic_upgrade, pytest.mark.module_startup_experience]


@pytest.mark.skipif(os.name != 'nt', reason='Windows native startup window')
def test_native_progress_three_aliases_pause_and_resume_without_recopying_another_instance():
    template = os.getenv('TS_TEST_DESKTOP_PORTABLE_TEMPLATE')
    installer = os.getenv('TS_TEST_DESKTOP_INSTALLER')
    if not template or not installer:
        pytest.skip('Configure a fresh frozen portable layout and NSIS installer')
    # NSIS parses /R from its raw command line, including a forward-slash
    # executable path containing /release. Use native Windows paths.
    installer = Path(installer).resolve()
    repo = Path(__file__).resolve().parents[4]
    cache = repo / 'tests/.cache/desktop-portable' / ('startup-' + uuid.uuid4().hex[:12])
    root = cache / '行影集'
    shutil.copytree(template, root)
    local = cache / 'local'; local.mkdir()
    env = {**os.environ, 'LOCALAPPDATA': str(local), 'PYTHONIOENCODING': 'utf-8'}
    for key in ('TS_DESKTOP_TEST_HEADLESS', 'TS_DESKTOP_TEST_HIDE_WINDOW', 'TS_DESKTOP_TEST_READONLY', 'TS_DESKTOP_VERIFY', 'TS_DESKTOP_SERVER_BINARY', 'TS_AUTOMATIC_UPGRADE_SESSION'):
        env.pop(key, None)
    read = lambda path: json.loads(path.read_text(encoding='utf-8'))
    build = read(root / 'portable.json')['activeBuild']
    backend = root / 'app' / build / 'server/trailsnap-server.exe'
    # The actual frozen initializer makes a legacy-shaped source before first launch.
    (root / 'data').mkdir()
    init = subprocess.run([str(backend), '--prepare-portable', str(root)], env=env,
                          capture_output=True, timeout=180, creationflags=subprocess.CREATE_NO_WINDOW)
    assert init.returncode == 0, init.stderr.decode('utf-8', errors='replace')[-4000:]
    (root / 'library.json').unlink()
    # A large, ordinary managed file makes source hashing observable without a test delay in production.
    payload = root / 'data/progress-fixture.bin'
    with payload.open('wb') as stream:
        for _ in range(256):
            stream.write(b'P' * (1024 * 1024))
    database = root / 'data/trailsnap.sqlite'
    source_hash = file_hash(database)

    user = ctypes.WinDLL('user32', use_last_error=True)
    user.GetDlgItem.argtypes = [wintypes.HWND, ctypes.c_int]; user.GetDlgItem.restype = wintypes.HWND
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
    user.IsWindowEnabled.argtypes = [wintypes.HWND]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]; user.GetWindow.restype = wintypes.HWND
    user.IsIconic.argtypes = [wintypes.HWND]
    user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t,
                                       wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, ctypes.c_ssize_t)
    user.EnumWindows.argtypes = [callback_type, ctypes.c_ssize_t]

    def text(hwnd):
        value = ctypes.create_unicode_buffer(1000)
        user.GetWindowTextW(hwnd, value, len(value))
        return value.value

    def window(pid, client=False):
        found = []
        @callback_type
        def visit(hwnd, _):
            owner = wintypes.DWORD()
            user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value != pid:
                return True
            expected = (user.IsWindowVisible(hwnd) and not user.GetWindow(hwnd, 4)
                        and text(hwnd) == 'TrailSnap 行影集') if client else user.GetDlgItem(hwnd, 101)
            if owner.value == pid and expected:
                found.append(hwnd)
                return False
            return True
        user.EnumWindows(visit, 0)
        return found[0] if found else None

    process = None
    def wait(predicate, message, timeout=180):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process.poll() is not None:
                error = root / 'maintenance/launcher-error.json'
                pytest.fail(f'launcher {process.pid} exited {process.returncode}: ' +
                            (error.read_text(encoding='utf-8') if error.exists() else 'no launcher-error.json'))
            value = predicate()
            if value:
                return value
            time.sleep(.02)
        pytest.fail(message)

    try:
        installed = subprocess.run([str(installer), '/S', '/NS', f'/D={root}'], env=env,
                                   capture_output=True, timeout=300, creationflags=subprocess.CREATE_NO_WINDOW)
        assert installed.returncode == 0, installed.stderr.decode(errors='replace')[-4000:]
        process = subprocess.Popen([str(root / 'TrailSnap.exe')], env=env, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        hwnd = wait(lambda: window(process.pid), 'native startup window missing', 20)
        progress_path = root / 'maintenance/automatic-upgrade-progress.json'
        def status():
            try:
                return read(progress_path)
            except (OSError, ValueError):
                return {}
        progress = wait(lambda: (s if (s := status()).get('cancellable') and s.get('stage') in {'inventory', 'baseline', 'copying'} else None), 'no cancellable progress')
        session = progress['session']
        response = ctypes.c_size_t()
        assert user.SendMessageTimeoutW(hwnd, 0, 0, 0, 2, 1000, ctypes.byref(response)), 'native UI hung while helper worked'
        for alias in ('TrailSnap.exe', 'trailsnap-desktop.exe', 'portable-launcher.exe'):
            user.ShowWindow(hwnd, 6)
            duplicate = subprocess.run([str(root / alias)], env=env, capture_output=True, timeout=12,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            assert duplicate.returncode == 0, duplicate.stderr.decode(errors='replace')
            wait(lambda: not user.IsIconic(hwnd), 'repeat launch did not restore the existing window', 5)
            assert status()['session'] == session
            assert window(process.pid) == hwnd
        wait(lambda: user.IsWindowEnabled(user.GetDlgItem(hwnd, 101)), 'pause unavailable', 10)
        if os.getenv('TS_DESKTOP_NATIVE_CAPTURE') == '1':
            from PIL import ImageGrab
            user.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
            user.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
            previous = user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
            try:
                rectangle = wintypes.RECT(); user.GetWindowRect(hwnd, ctypes.byref(rectangle))
                ImageGrab.grab(bbox=(rectangle.left, rectangle.top, rectangle.right, rectangle.bottom), all_screens=True).save(cache / 'progress.png')
            finally:
                user.SetThreadDpiAwarenessContext(previous)
        user.PostMessageW(hwnd, 0x111, 101, 0)
        wait(lambda: '已安全暂停' in text(user.GetDlgItem(hwnd, 1)), 'pause did not reach a safe stopped state', 90)
        assert file_hash(database) == source_hash
        assert not (root / 'instance.json').exists()
        assert payload.is_file()
        paused_journal = read(root / 'maintenance/automatic-upgrade.json')
        assert paused_journal['phase'] == 'copying'
        # Retry through the real native button, keeping the same coordinator and operation.
        user.PostMessageW(hwnd, 0x111, 102, 0)
        journal = root / 'maintenance/automatic-upgrade.json'
        wait(lambda: read(journal)['phase'] == 'completed', 'native retry did not finish migration and cleanup', 300)
        final = read(journal)
        assert final['id'] == paused_journal['id']
        assert not database.exists() and not payload.exists()
        assert (root / 'userdata/data/trailsnap.sqlite').is_file()
        assert (root / 'userdata/data/progress-fixture.bin').stat().st_size == 256 * 1024 * 1024
        ready = read(root / 'maintenance/runtime-ready.json')
        assert ready['verified'] is True
        assert read(root / 'maintenance/automatic-upgrade-progress.json')['session'] == session
        assert not user.IsWindowEnabled(user.GetDlgItem(hwnd, 101)) or not status().get('cancellable')
        wait(lambda: not user.IsWindowVisible(hwnd), 'startup window did not hide after readiness', 10)
        client = wait(lambda: window(ready['pid'], client=True), 'normal client window missing', 10)
        user.ShowWindow(client, 6)
        duplicate = subprocess.run([str(root / 'TrailSnap.exe')], env=env, capture_output=True,
                                   timeout=12, creationflags=subprocess.CREATE_NO_WINDOW)
        assert duplicate.returncode == 0
        wait(lambda: not user.IsIconic(client), 'repeat launch did not restore the normal client', 5)
        (cache / 'result.json').write_text(json.dumps({'nativeProgress': True, 'windowResponsive': True,
            'threeAliasesReuseWindow': True, 'pausePreservesSource': True, 'retryCompletesSameOperation': True,
            'oldDataCleanedAfterNormalStartup': True, 'normalWindowReactivated': True}, ensure_ascii=False, indent=2), encoding='utf-8')
    finally:
        import psutil
        children = psutil.Process(process.pid).children(recursive=True) if process and process.poll() is None else []
        if process and process.poll() is None:
            process.terminate(); process.wait(timeout=20)
        _, alive = psutil.wait_procs(children, timeout=30)
        assert not alive, 'native test left sidecars running'
        uninstaller = root / 'uninstall.exe'
        if uninstaller.is_file():
            result = subprocess.run([str(uninstaller), '/S', '/NS'], env=env, capture_output=True,
                                    timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)
            assert result.returncode == 0
        # Keep compact evidence, not the synthetic 256 MiB payload.
        for path in (payload, root / 'userdata/data/progress-fixture.bin'):
            assert path.resolve().is_relative_to(cache.resolve())
            path.unlink(missing_ok=True)
