"""Real complete Windows installation, isolated from installed user libraries."""
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import time
import urllib.request
import uuid

import pytest

pytestmark = [pytest.mark.module_bundled_ai]


def test_complete_installer_runs_ai_and_preserves_data_on_reinstall():
    raw = os.getenv('TS_TEST_DESKTOP_INSTALLER')
    if os.name != 'nt' or not raw:
        pytest.skip('Set the complete Windows installer for native acceptance')
    repo = Path(__file__).resolve().parents[4]
    cache = repo/'tests/.cache/desktop-portable'/('bundled-ai-'+uuid.uuid4().hex[:10])
    root = cache/'行影集安装测试'
    local = cache/'local-appdata'
    local.mkdir(parents=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        cdp = sock.getsockname()[1]
    env = {**os.environ, 'LOCALAPPDATA': str(local), 'APPDATA': str(cache/'appdata'),
           'TS_DESKTOP_TEST_HEADLESS': '1', 'TS_AI_SKIP_AUTO_DOWNLOAD': '1',
           'WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS': f'--remote-debugging-port={cdp}'}
    for key in ['TS_DESKTOP_VERIFY','TS_DESKTOP_TEST_READONLY','TS_DESKTOP_SERVER_BINARY']:
        env.pop(key,None)
    installer = str(Path(raw).resolve())
    def install():
        return subprocess.run([installer,'/S',f'/D={root}'],env=env,capture_output=True,
                              timeout=600,creationflags=subprocess.CREATE_NO_WINDOW)
    assert install().returncode == 0
    descriptor=json.loads((root/'portable.json').read_text(encoding='utf-8'))
    build=descriptor['activeBuild']
    program=root/'app'/build
    version=json.loads((repo/'package/desktop/src-tauri/tauri.conf.json').read_text(encoding='utf-8'))['version']
    assert json.loads((program/'manifest.json').read_text(encoding='utf-8'))['bundledAI'] is True
    assert not (root/'server').exists() and not (root/'ai').exists()
    for component in ['server','ai']:
        assert (program/component/f'trailsnap-{component}.exe').is_file()
        assert json.loads((program/component/'runtime-version.json').read_text(encoding='utf-8'))['version']==version
    process=subprocess.Popen([str(root/'TrailSnap.exe')],env=env,cwd=root,
                             creationflags=subprocess.CREATE_NO_WINDOW)
    report={'root':str(root),'installer':installer,'buildId':build,'cdpPort':cdp}
    output=repo/'data/bundled-ai-work'
    output.mkdir(parents=True,exist_ok=True)
    try:
        deadline=time.monotonic()+180
        while not (root/'maintenance/runtime-ready.json').exists():
            error=root/'maintenance/launcher-error.json'
            assert not error.exists(), error.read_text(encoding='utf-8') if error.exists() else ''
            assert process.poll() is None,'Launcher exited before readiness'
            assert time.monotonic()<deadline,'Installed application startup timed out'
            time.sleep(.25)
        instance=json.loads((root/'instance.json').read_text(encoding='utf-8'))
        base=f'http://127.0.0.1:{instance["serverPort"]}'
        report['apiUrl']=base
        security=json.loads((root/'userdata/data/system_config.json').read_text(encoding='utf-8'))['security']
        with sqlite3.connect(root/'userdata/data/trailsnap.sqlite') as db:
            owner=db.execute('SELECT id FROM users LIMIT 1').fetchone()[0]
        from jose import jwt
        token=jwt.encode({'sub':str(uuid.UUID(owner)),'exp':int(time.time())+900},
                         security['secret_key'],algorithm=security.get('algorithm','HS256'))
        def get(path):
            request=urllib.request.Request(base+path,headers={'Authorization':'Bearer '+token})
            with urllib.request.urlopen(request,timeout=120) as response:
                return json.load(response)
        assert get('/health-check')['status']=='ok'
        assert get('/api/settings/')['runtime']['managedAI'] is True
        models=get('/api/settings/ai-models')
        assert models['code']==0 and models['data']['models']
        import psutil
        children=psutil.Process(process.pid).children(recursive=True)
        ai=[child for child in children if child.name()=='trailsnap-ai.exe']
        assert len(ai)==1
        assert Path(ai[0].exe()).resolve().is_relative_to((program/'ai').resolve())
        old_pid=ai[0].pid
        ai[0].terminate()
        ai[0].wait(timeout=30)
        assert get('/health-check')['status']=='ok'
        assert get('/api/settings/ai-models')['code']==0
        recovered=[child for child in psutil.Process(process.pid).children(recursive=True)
                   if child.name()=='trailsnap-ai.exe']
        assert len(recovered)==1 and recovered[0].pid!=old_pid
        assert install().returncode != 0,'Running installation must refuse overwrite'
        assert process.poll() is None,'Installer stopped a running application'
        sentinel=root/'userdata/models/preserve.sentinel'
        sentinel.parent.mkdir(parents=True,exist_ok=True)
        sentinel.write_bytes(b'existing models survive')
        report.update(installedAI=True,managedSettings=True,runningOverwriteRefused=True,automaticAIRecovery=True)
        review=root/'maintenance/ui-review.json'
        if os.getenv('TS_TEST_DESKTOP_UI_REVIEW')=='1':
            report['phase']='awaiting_ui_review'
            (output/'install-review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            deadline=time.monotonic()+600
            while not review.exists():
                assert time.monotonic()<deadline,'Timed out waiting for automated UI review'
                time.sleep(.5)
            evidence=json.loads(review.read_text(encoding='utf-8'))
            assert evidence['safeExit'] is True and evidence['settings'] is True
            process.wait(timeout=60)
            assert process.returncode==0
            report.update(ui=evidence,safeExit=True)
        else:
            process.terminate()
            process.wait(timeout=30)
            psutil.wait_procs(children,timeout=30)
        assert install().returncode==0
        assert sentinel.read_bytes()==b'existing models survive'
        assert json.loads((root/'instance.json').read_text(encoding='utf-8'))['instanceId']==instance['instanceId']
        assert not (root/'server').exists() and not (root/'ai').exists()
        report.update(phase='passed',reinstallPreservesData=True,installerBytes=Path(installer).stat().st_size)
        (output/'installed-test-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=30)
