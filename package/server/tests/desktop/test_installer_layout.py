"""Opt-in installation acceptance; every destination is a fresh workspace cache."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

import pytest

pytestmark = [pytest.mark.module_portable_upgrade]


def test_installer_instances_match_zip_and_uninstall_preserves_data():
    installer = os.getenv('TS_TEST_DESKTOP_INSTALLER')
    template = os.getenv('TS_TEST_DESKTOP_PORTABLE_TEMPLATE')
    if os.name != 'nt' or not installer or not template:
        pytest.skip('Set final NSIS installer and ZIP layout for acceptance')
    # NSIS scans its full command line for /R; normalize Windows paths so
    # a forward-slash /release directory cannot accidentally request launch.
    installer = str(Path(installer).resolve())
    import winreg
    repo = Path(__file__).resolve().parents[4]
    cache = repo / 'tests/.cache/desktop-portable' / ('installer-' + uuid.uuid4().hex[:10])
    roots = [cache / '家庭安装', cache / '工作安装']
    expected = json.loads((Path(template) / 'portable.json').read_text())['activeBuild']
    env = {**os.environ, 'TS_INSTANCE_ROOT': str(cache / 'wrong-instance')}
    def install(root):
        result = subprocess.run([installer, '/S', f'/D={root}'], env=env,
                                timeout=240, creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode == 0
        assert json.loads((root / 'portable.json').read_text())['activeBuild'] == expected
        assert (root / 'app' / expected / 'server/trailsnap-server.exe').is_file()
        assert (root / 'TrailSnap.exe').read_bytes() == (root / 'trailsnap-desktop.exe').read_bytes()
    def registry_key(root):
        tag = hashlib.sha256((str(root).rstrip('\\') + '\\').lower().encode('utf-8')).hexdigest()
        return 'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\TrailSnap-' + tag
    def uninstall(root):
        uninstaller = root / 'uninstall.exe'
        if not uninstaller.exists():
            return
        subprocess.run([str(uninstaller), '/S', f'_?={root}'], timeout=180,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 60
        while (root / 'app').exists() and time.monotonic() < deadline:
            time.sleep(.2)
        assert not (root / 'app').exists()
    try:
        for root in roots:
            install(root)
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry_key(root)) as key:
                assert str(root) in winreg.QueryValueEx(key, 'DisplayName')[0]
            (root / 'userdata').mkdir(exist_ok=True)
            (root / 'userdata/sentinel').write_bytes(b'user photos must survive')
            (root / 'instance.json').write_text(json.dumps({'dataRoot': {'kind':'relative','path':'userdata'}}))
        original = (roots[0] / 'instance.json').read_bytes()
        install(roots[0])
        assert (roots[0] / 'instance.json').read_bytes() == original
        uninstall(roots[0])
        assert (roots[0] / 'userdata/sentinel').read_bytes() == b'user photos must survive'
        assert (roots[0] / 'instance.json').read_bytes() == original
        assert (roots[1] / 'TrailSnap.exe').is_file()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry_key(roots[1])):
            pass
        assert not (cache / 'wrong-instance').exists()
    finally:
        for root in roots:
            uninstall(root)
