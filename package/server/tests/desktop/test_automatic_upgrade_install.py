"""Actual NSIS, frozen sidecar and writable WebView startup in scratch directories."""
from contextlib import closing
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import time
import urllib.request
import uuid

import pytest

pytestmark = [pytest.mark.module_automatic_upgrade, pytest.mark.module_portable_upgrade]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


@pytest.mark.parametrize('broken_candidate', [False, True])
def test_real_install_auto_migrates_repairs_and_cleans_after_normal_start(broken_candidate, monkeypatch):
    installer = os.getenv('TS_TEST_DESKTOP_INSTALLER')
    template = os.getenv('TS_TEST_DESKTOP_PORTABLE_TEMPLATE')
    if os.name != 'nt' or not installer or not template:
        pytest.skip('Set built installer and portable layout for native acceptance')
    repo = Path(__file__).resolve().parents[4]
    cache = repo / 'tests/.cache/desktop-portable' / ('automatic-' + uuid.uuid4().hex[:12])
    root = cache / '中文安装'
    root.mkdir(parents=True)
    local = cache / 'local'; local.mkdir()
    environment = {**os.environ, 'LOCALAPPDATA': str(local), 'TS_DESKTOP_TEST_HEADLESS': '1',
                   'PYTHONIOENCODING': 'utf-8'}
    environment.pop('TS_DESKTOP_TEST_READONLY', None)
    environment.pop('TS_DESKTOP_VERIFY', None)
    environment.pop('TS_DESKTOP_SERVER_BINARY', None)
    build = read(Path(template) / 'portable.json')['activeBuild']
    backend = Path(template) / 'app' / build / 'server/trailsnap-server.exe'

    def invoke(executable, *args, timeout=240, check=True):
        result = subprocess.run([str(executable), *map(str, args)], env=environment, capture_output=True,
                                timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
        if check:
            assert result.returncode == 0, result.stderr.decode('utf-8', errors='replace')[-6000:]
        return result

    process = None
    def stop():
        nonlocal process
        if process and process.poll() is None:
            import psutil
            children = psutil.Process(process.pid).children(recursive=True)
            process.terminate(); process.wait(timeout=20)
            _, alive = psutil.wait_procs(children, timeout=20)
            assert not alive, 'test launcher job left sidecars running'

    def launch():
        nonlocal process
        (root / 'maintenance/runtime-ready.json').unlink(missing_ok=True)
        process = subprocess.Popen([str(root / 'TrailSnap.exe')], env=environment,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            journal = root / 'maintenance/automatic-upgrade.json'
            ready = root / 'maintenance/runtime-ready.json'
            if journal.exists() and read(journal)['phase'] == 'completed' and ready.exists():
                return
            error = root / 'maintenance/launcher-error.json'
            if process.poll() is not None:
                pytest.fail(error.read_text(encoding='utf-8') if error.exists() else 'launcher exited')
            time.sleep(.2)
        logs = list((root / 'userdata/logs').glob('*err*'))
        pytest.fail('automatic migration timed out: ' + '\n'.join(p.read_text(encoding='utf-8', errors='replace')[-4000:] for p in logs))

    # Use the real sidecar to create a legacy-shaped SQLite library, then add an
    # original. Everything, including the writable normal server, stays in cache.
    (root / 'data').mkdir()
    invoke(backend, '--prepare-portable', root)
    (root / 'library.json').unlink()
    database = root / 'data/trailsnap.sqlite'
    # Exercise the schema shipped before portable storage references, rather
    # than just moving a database already at the new client's schema head.
    from alembic import command
    from alembic.config import Config
    config = Config()
    config.set_main_option('script_location', str(repo / 'package/server/alembic_sqlite'))
    config.set_main_option('sqlalchemy.url', f'sqlite:///{database.as_posix()}')
    with monkeypatch.context() as patch:
        patch.setenv('TS_DB_URL', f'sqlite:///{database.as_posix()}')
        command.downgrade(config, 'b0b9b9a3a2c0')
    with closing(sqlite3.connect(database)) as db, db:
        owner = db.execute("SELECT id FROM users WHERE username='desktop-admin'").fetchone()[0]
        photo = str(uuid.uuid4())
        image = root / 'data/users' / owner / 'uploads/original.png'
        image.parent.mkdir(parents=True, exist_ok=True)
        from PIL import Image
        Image.new('RGB', (16, 16), 'green').save(image)
        db.execute("INSERT INTO photos(id,owner_id,file_path,file_type,size,is_deleted) VALUES (?,?,?,'image',?,0)",
                   (photo, owner, str(image), image.stat().st_size))
    expected = hashlib.sha256(image.read_bytes()).hexdigest()
    old_hash = hashlib.sha256(database.read_bytes()).hexdigest()
    original_settings = read(root / 'data/system_config.json')
    try:
        invoke(Path(installer).resolve(), '/S', '/NS', f'/D={root}')
        assert read(root / 'portable.json')['activeBuild'] == build
        for name in ('TrailSnap.exe', 'trailsnap-desktop.exe', 'portable-launcher.exe'):
            assert ctypes.windll.shell32.ExtractIconExW(str(root / name), -1, None, None, 0) > 0, name
        shell = root / 'app' / build / 'trailsnap-desktop.exe'
        shell_hash = hashlib.sha256(shell.read_bytes()).hexdigest()
        if broken_candidate:
            shell.write_bytes(b'broken migration candidate')
            rejected = invoke(root / 'TrailSnap.exe', '--validate-only', check=False)
            assert rejected.returncode != 0
            assert hashlib.sha256(database.read_bytes()).hexdigest() == old_hash
            assert image.is_file()
            assert read(root / 'maintenance/automatic-upgrade.json')['phase'] == 'published'
            invoke(Path(installer).resolve(), '/S', '/NS', f'/D={root}')
            assert hashlib.sha256(shell.read_bytes()).hexdigest() == shell_hash
        launch()
        assert not database.exists() and not image.exists()
        instance = read(root / 'instance.json')
        data = root / 'userdata'
        assert instance['dataRoot'] == {'kind': 'relative', 'path': 'userdata'}
        assert read(data / 'data/system_config.json')['security']['secret_key'] == original_settings['security']['secret_key']
        port = instance['serverPort']
        response = urllib.request.urlopen(f'http://127.0.0.1:{port}/api/medias/{photo}/file?original=1', timeout=30)
        assert response.status == 200
        assert hashlib.sha256(response.read()).hexdigest() == expected
        from jose import jwt
        token = jwt.encode({'sub': owner, 'exp': int(time.time()) + 3600},
                           original_settings['security']['secret_key'],
                           algorithm=original_settings['security'].get('algorithm', 'HS256'))
        request = urllib.request.Request(f'http://127.0.0.1:{port}/api/photos',
                                         headers={'Authorization': 'Bearer ' + token})
        with urllib.request.urlopen(request, timeout=30) as response:
            photos = json.load(response)
        assert any(str(item['id']) == photo for item in photos)
        before_id = instance['instanceId']
        stop()
        # Same-version repair must replace both a corrupt shell and missing backend.
        data_hash = hashlib.sha256((data / 'data/trailsnap.sqlite').read_bytes()).hexdigest()
        shell.write_bytes(b'broken after successful upgrade')
        (root / 'app' / build / 'server/trailsnap-server.exe').unlink()
        invoke(Path(installer).resolve(), '/S', '/NS', f'/D={root}')
        assert hashlib.sha256(shell.read_bytes()).hexdigest() == shell_hash
        assert hashlib.sha256((data / 'data/trailsnap.sqlite').read_bytes()).hexdigest() == data_hash
        assert read(root / 'instance.json')['instanceId'] == before_id
        launch()
        assert read(root / 'instance.json')['instanceId'] == before_id
        assert not (root / 'data/trailsnap.sqlite').exists()
        (cache / 'result.json').write_text(json.dumps({'automaticMigration': True, 'httpOriginalSha256': expected,
            'oldDataCleaned': True, 'sameVersionRepair': True, 'icons': True,
            'oldSessionTokenWorks': True, 'candidateFailureTested': broken_candidate}, indent=2), encoding='utf-8')
    finally:
        stop()
        if (root / 'uninstall.exe').exists():
            invoke(root / 'uninstall.exe', '/S', f'_?={root}')


def test_nsis_default_upgrade_selects_existing_chinese_installation():
    """Compile the same generated script under a private product/registry name.

    Its fallback directory is also in cache. No branch can select a real install.
    """
    if os.name != 'nt' or not os.getenv('TS_TEST_DESKTOP_INSTALLER'):
        pytest.skip('Set built Windows installer')
    import winreg
    repo = Path(__file__).resolve().parents[4]
    generated = repo / 'package/desktop/src-tauri/target/release/nsis/x64/installer.nsi'
    compiler = Path(os.environ['LOCALAPPDATA']) / 'tauri/NSIS/makensis.exe'
    assert generated.is_file() and compiler.is_file()
    product = 'TrailSnap-REQ165-' + uuid.uuid4().hex[:10]
    cache = repo / 'tests/.cache/desktop-portable' / product
    installed = cache / '已有中文安装'; installed.mkdir(parents=True)
    fallback = cache / 'fallback'
    fixture_installer = cache / 'directory-setup.exe'
    source = generated.read_text(encoding='utf-8')
    source, changed = re.subn(r'(?m)^!define PRODUCTNAME ".*"$', lambda _: f'!define PRODUCTNAME "{product}"', source)
    assert changed == 1
    source, changed = re.subn(r'(?m)^!define OUTFILE ".*"$', lambda _: f'!define OUTFILE "{fixture_installer}"', source)
    assert changed == 1
    original = 'StrCpy $INSTDIR "$LOCALAPPDATA\\${PRODUCTNAME}"'
    assert source.count(original) == 1
    source = source.replace(original, f'StrCpy $INSTDIR "{fallback}"')
    fixture_script = cache / 'directory.nsi'
    fixture_script.write_text(source, encoding='utf-8')
    compiled = subprocess.run([str(compiler), '/V2', '/NOCD', '/INPUTCHARSET', 'UTF8', str(fixture_script)],
                              cwd=generated.parent, capture_output=True, timeout=240)
    assert compiled.returncode == 0, compiled.stdout.decode(errors='replace') + compiled.stderr.decode(errors='replace')
    (installed / 'uninstall.exe').write_bytes(b'old fixture')
    (installed / 'trailsnap-desktop.exe').write_bytes(b'old fixture')
    key = 'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\' + product + '-previous'
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as handle:
            winreg.SetValueEx(handle, 'InstallLocation', 0, winreg.REG_SZ, str(installed))
        result = subprocess.run([str(fixture_installer), '/S', '/NS'], capture_output=True, timeout=240,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode == 0
        assert (installed / 'TrailSnap.exe').is_file()
        assert (installed / 'portable.json').is_file()
        assert not fallback.exists()
        (cache / 'result.json').write_text(json.dumps({'existingChinesePathSelected': True,
                                                     'fallbackUnused': True}), encoding='utf-8')
    finally:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
        if (installed / 'portable.json').exists():
            result = subprocess.run([str(installed / 'uninstall.exe'), '/S', f'_?={installed}'],
                                    capture_output=True, timeout=240, creationflags=subprocess.CREATE_NO_WINDOW)
            assert result.returncode == 0
