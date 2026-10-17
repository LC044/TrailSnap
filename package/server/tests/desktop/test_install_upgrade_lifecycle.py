"""Current NSIS package against scratch installations and a historical SQLite library."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
import uuid

import pytest

pytestmark = [pytest.mark.module_portable_upgrade]


def test_installer_preparation_error_returns_without_a_native_modal(tmp_path):
    template = os.getenv('TS_TEST_DESKTOP_PORTABLE_TEMPLATE')
    if os.name != 'nt' or not template:
        pytest.skip('Set the current launcher template')
    shutil.copy2(Path(template) / 'TrailSnap.exe', tmp_path / 'TrailSnap.exe')
    (tmp_path / 'instance.json').write_text('{}')
    environment = dict(os.environ)
    environment.pop('TS_DESKTOP_TEST_HEADLESS', None)
    result = subprocess.run([str(tmp_path / 'TrailSnap.exe'), '--prepare-reinstall'], env=environment,
                            capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode != 0
    assert not (tmp_path / 'userdata').exists()


def test_reinstall_new_build_after_uninstall_preserves_library():
    packages = [os.getenv('TS_TEST_DESKTOP_PREVIOUS_INSTALLER'), os.getenv('TS_TEST_DESKTOP_INSTALLER')]
    if os.name != 'nt' or not all(packages):
        pytest.skip('Set current and previous per-directory NSIS packages')
    root = Path(__file__).resolve().parents[4] / 'tests/.cache/desktop-portable' / ('reinstall-' + uuid.uuid4().hex[:10])
    environment = {**os.environ, 'TS_DESKTOP_TEST_HEADLESS': '1', 'TS_DESKTOP_TEST_READONLY': '1'}

    def invoke(executable, *args):
        return subprocess.run([str(executable), *map(str, args)], env=environment, capture_output=True,
                              timeout=240, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        assert invoke(Path(packages[0]).resolve(), '/S', '/NS', f'/D={root}').returncode == 0
        prepared = invoke(root / 'TrailSnap.exe', '--validate-only')
        assert prepared.returncode == 0, prepared.stderr.decode(errors='replace')
        original = json.loads((root / 'instance.json').read_text(encoding='utf-8'))
        assert invoke(root / 'uninstall.exe', '/S', f'_?={root}').returncode == 0
        assert not (root / 'app').exists()
        assert invoke(Path(packages[1]).resolve(), '/S', '/NS', f'/D={root}').returncode == 0
        offered = json.loads((root / 'portable.json').read_text(encoding='utf-8'))['activeBuild']
        executable = root / 'app' / offered / 'trailsnap-desktop.exe'
        saved_program = executable.read_bytes()
        executable.write_bytes(b'broken reinstallation candidate')
        rejected = invoke(root / 'TrailSnap.exe', '--validate-only')
        assert rejected.returncode != 0
        assert json.loads((root / 'instance.json').read_text(encoding='utf-8'))['activeBuild'] == original['activeBuild']
        assert (root / 'userdata/data/trailsnap.sqlite').is_file()
        executable.write_bytes(saved_program)
        prepared = invoke(root / 'TrailSnap.exe', '--validate-only')
        assert prepared.returncode == 0, prepared.stderr.decode(errors='replace')
        current = json.loads((root / 'instance.json').read_text(encoding='utf-8'))
        assert current['instanceId'] == original['instanceId']
        assert current['activeBuild'] != original['activeBuild']
        assert (root / 'userdata/data/trailsnap.sqlite').is_file()
        # Simulate loss of power after the reinstallation snapshot, before commit.
        backend = root / 'app' / current['activeBuild'] / 'server/trailsnap-server.exe'
        data = root / 'userdata'
        snapshot = data / 'backups/reinstall-interruption'
        assert invoke(backend, '--snapshot-data', data, snapshot).returncode == 0
        original_settings = (data / 'data/system_config.json').read_bytes()
        (data / 'data/system_config.json').write_text('{"security":{"secret_key":"interrupted"}}')
        (root / 'maintenance/reinstall.json').write_text(json.dumps({'originalConfig': current, 'newBuild': current['activeBuild']}))
        (root / 'maintenance/update.json').write_text(json.dumps({'schemaVersion': 1, 'id': 'reinstall-interruption',
            'phase': 'validating', 'oldBuild': current['activeBuild'], 'newBuild': current['activeBuild'],
            'version': '0.17.4', 'nonce': 'interruption', 'error': None}))
        prepared = invoke(root / 'TrailSnap.exe', '--validate-only')
        assert prepared.returncode == 0, prepared.stderr.decode(errors='replace')
        assert (data / 'data/system_config.json').read_bytes() == original_settings
        assert not (root / 'maintenance/reinstall.json').exists()
    finally:
        if (root / 'uninstall.exe').exists():
            assert invoke(root / 'uninstall.exe', '/S', f'_?={root}').returncode == 0


def test_install_upgrade_import_move_and_failed_candidate(monkeypatch):
    installer_raw = os.getenv('TS_TEST_DESKTOP_INSTALLER')
    previous_raw = os.getenv('TS_TEST_DESKTOP_PREVIOUS_INSTALLER')
    if os.name != 'nt' or not installer_raw or not previous_raw:
        pytest.skip('Set current and previous per-directory NSIS packages')
    import psutil
    from alembic import command
    from alembic.config import Config
    from app.utils.desktop_verification import photo_paths, verify_media
    from app.utils.windows_paths import filesystem_path

    repo = Path(__file__).resolve().parents[4]
    cache = repo / 'tests/.cache/desktop-portable' / ('lifecycle-' + uuid.uuid4().hex[:10])
    (cache / 'local-appdata').mkdir(parents=True)
    fresh, legacy, imported, upgrading = [cache / name for name in ('全新安装', '旧版安装', '导入后的图库', '已有图库更新')]
    installer, previous = [str(Path(p).resolve()) for p in (installer_raw, previous_raw)]
    template = os.getenv('TS_TEST_DESKTOP_PORTABLE_TEMPLATE')
    expected_build = json.loads((Path(template) / 'portable.json').read_text(encoding='utf-8'))['activeBuild'] if template else None
    environment = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'TS_DESKTOP_TEST_HEADLESS': '1', 'TS_DESKTOP_TEST_READONLY': '1',
                   'LOCALAPPDATA': str(cache / 'local-appdata')}
    processes = []
    installed = []
    report = {}

    def invoke(executable, *args, env=None, timeout=240):
        return subprocess.run([str(executable), *map(str, args)], env=env or environment,
                              capture_output=True, timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)

    def install(package, root):
        result = invoke(package, '/S', '/NS', f'/D={root}')
        assert result.returncode == 0, result.stderr.decode(errors='replace')
        if root not in installed:
            installed.append(root)
        assert (root / 'TrailSnap.exe').is_file()
        if package == installer and expected_build:
            assert json.loads((root / 'portable.json').read_text(encoding='utf-8'))['activeBuild'] == expected_build

    def stop(process):
        if process.poll() is None:
            children = psutil.Process(process.pid).children(recursive=True)
            process.terminate()
            process.wait(timeout=20)
            _, alive = psutil.wait_procs(children, timeout=20)
            assert not alive, 'Test runtime did not release its sidecars'

    def launch(root):
        marker = root / 'maintenance/validated.json'
        marker.unlink(missing_ok=True)
        (root / 'maintenance/launcher-error.json').unlink(missing_ok=True)
        process = subprocess.Popen([str(root / 'TrailSnap.exe')], env=environment,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        processes.append(process)
        deadline = time.monotonic() + 180
        while True:
            # The candidate verifier writes this same marker before the
            # launcher commits the update and starts the normal runtime.
            journal = root / 'maintenance/update.json'
            transaction = json.loads(journal.read_text(encoding='utf-8')) if journal.exists() else {}
            proof = json.loads(marker.read_text(encoding='utf-8')) if marker.exists() else {}
            if (proof.get('verified') and
                    transaction.get('phase') in (None, 'committed', 'rolled_back') and
                    proof.get('nonce') != transaction.get('nonce')):
                break
            error = root / 'maintenance/launcher-error.json'
            assert not error.exists(), error.read_text(encoding='utf-8') if error.exists() else ''
            assert process.poll() is None, 'Installed launcher exited before becoming ready'
            assert time.monotonic() < deadline, f'Installed startup timed out: {root}'
            time.sleep(.2)
        assert json.loads(marker.read_text(encoding='utf-8'))['verified']
        return process

    try:
        install(installer, fresh)
        first = launch(fresh)
        identity = json.loads((fresh / 'instance.json').read_text(encoding='utf-8'))['instanceId']
        descriptor = (fresh / 'portable.json').read_bytes()
        rejected = invoke(installer, '/S', '/NS', f'/D={fresh}')
        assert rejected.returncode != 0, 'Running installation was accepted'
        assert first.poll() is None, 'Installer terminated the active runtime'
        assert (fresh / 'portable.json').read_bytes() == descriptor
        report['freshInstallAndRunningOverwriteProtection'] = True
        stop(first)
        install(installer, fresh)
        assert json.loads((fresh / 'instance.json').read_text(encoding='utf-8'))['instanceId'] == identity
        report['stoppedOverwritePreservesIdentity'] = True

        install(previous, upgrading)
        old_process = launch(upgrading)
        old_config = json.loads((upgrading / 'instance.json').read_text(encoding='utf-8'))
        stop(old_process)
        (upgrading / 'userdata/keep.txt').write_bytes(b'preserve existing library files')
        install(installer, upgrading)
        updated = launch(upgrading)
        updated_config = json.loads((upgrading / 'instance.json').read_text(encoding='utf-8'))
        assert updated_config['instanceId'] == old_config['instanceId']
        assert updated_config['activeBuild'] != old_config['activeBuild']
        assert json.loads((upgrading / 'maintenance/update.json').read_text(encoding='utf-8'))['phase'] == 'committed'
        assert (upgrading / 'userdata/keep.txt').read_bytes() == b'preserve existing library files'
        stop(updated)
        report['previousBuildUpgradeBackedUpValidatedAndCommitted'] = True

        install(previous, legacy)
        database = legacy / 'data/trailsnap.sqlite'
        database.parent.mkdir(exist_ok=True)
        config = Config()
        config.set_main_option('script_location', str(repo / 'package/server/alembic_sqlite'))
        config.set_main_option('sqlalchemy.url', f'sqlite:///{database.as_posix()}')
        monkeypatch.setenv('TS_DB_URL', f'sqlite:///{database.as_posix()}')
        command.upgrade(config, 'b0b9b9a3a2c0')
        owner, photo = str(uuid.uuid4()), str(uuid.uuid4())
        original = legacy / 'data/organized/original.jpg'
        original.parent.mkdir()
        original.write_bytes(b'old-library-original')
        with closing(sqlite3.connect(database)) as db, db:
            db.execute('INSERT INTO users(id,username,email,hashed_password,settings) VALUES (?,?,?,?,?)',
                       (owner, 'desktop-admin', 'desktop@trailsnap.app', 'hash', '{}'))
            db.execute("INSERT INTO photos(id,owner_id,file_path,file_type,is_deleted) VALUES (?,?,?,'image',0)",
                       (photo, owner, str(original)))
        before = hashlib.sha256(database.read_bytes()).hexdigest()
        install(installer, legacy)
        assert hashlib.sha256(database.read_bytes()).hexdigest() == before
        old_runtime = launch(legacy)
        stop(old_runtime)
        build = json.loads((legacy / 'instance.json').read_text(encoding='utf-8'))['activeBuild']
        program = legacy / 'app' / build
        backend = program / 'server/trailsnap-server.exe'
        discovery = invoke(backend, '--discover-old-data', legacy, legacy / 'userdata')
        assert discovery.returncode == 0, discovery.stderr.decode(errors='replace')
        found = json.loads(discovery.stdout.splitlines()[-1])
        assert any(Path(candidate['path']) == legacy for candidate in found['candidates'])
        report['historicalLibraryFoundAfterOverwrite'] = True
        conversion_env = {**environment, 'TS_IMPORT_OPERATION': str(uuid.uuid4()),
                          'TS_IMPORT_PREVIOUS_DATA': str(legacy / 'userdata'),
                          'TS_IMPORT_ORIGIN': str(legacy), 'TS_IMPORT_ORIGIN_ID': json.loads((legacy / 'instance.json').read_text(encoding='utf-8'))['instanceId']}
        result = invoke(backend, '--convert-portable', legacy, imported, program, legacy / 'TrailSnap.exe',
                        '--copy-external', env=conversion_env)
        assert result.returncode == 0, result.stderr.decode(errors='replace')
        proof = json.loads((imported / 'conversion.json').read_text(encoding='utf-8'))
        assert proof['previousEntry'] == str(legacy)
        verify_media(imported / 'userdata', proof['media'])
        result = invoke(imported / 'TrailSnap.exe', '--validate-only')
        assert result.returncode == 0, result.stderr.decode(errors='replace')
        assert hashlib.sha256(database.read_bytes()).hexdigest() == before
        report['FrozenLegacyImportFinalPathsAndZeroPhotoReturnEntry'] = True
        with closing(sqlite3.connect(imported / 'userdata/data/trailsnap.sqlite')) as db:
            copied = Path(list(photo_paths(db, imported / 'userdata'))[0][2])
        saved = copied.read_bytes()
        copied.unlink()
        result = invoke(imported / 'TrailSnap.exe', '--validate-only')
        assert result.returncode != 0, 'Missing copied original passed candidate validation'
        copied.write_bytes(saved)
        report['missingOriginalFailsNativeVerification'] = True

        target_config = json.loads((imported / 'instance.json').read_text(encoding='utf-8'))
        (legacy / 'maintenance/library-link.json').write_text(json.dumps({'target': str(imported),
            'instanceId': target_config['instanceId']}), encoding='utf-8')
        install(installer, legacy)
        result = invoke(backend, '--discover-old-data', imported, imported / 'userdata')
        assert json.loads(result.stdout.splitlines()[-1])['completed'] is True
        report['repeatInstallRetainsLinkAndCompletedImport'] = True
        moved = imported.with_name('搬迁后的图库')
        imported.rename(moved)
        moved_runtime = launch(moved)
        stop(moved_runtime)
        verify_media(moved / 'userdata', proof['media'])
        rejected = invoke(legacy / 'TrailSnap.exe', '--validate-only')
        assert rejected.returncode != 0
        assert not (imported / 'userdata').exists()
        report['movedLibraryBootsAndOldLinkDoesNotCreateEmptyLibrary'] = True

        # A real installed runtime must recover when the candidate cannot start.
        current = json.loads((fresh / 'instance.json').read_text(encoding='utf-8'))
        broken = fresh / 'app/broken-candidate'
        shutil.copytree(filesystem_path(fresh / 'app' / current['activeBuild']), filesystem_path(broken))
        manifest = json.loads((broken / 'manifest.json').read_text(encoding='utf-8'))
        manifest.update(buildId='broken-candidate', version='99.0.0')
        (broken / 'manifest.json').write_text(json.dumps(manifest))
        (broken / 'trailsnap-desktop.exe').write_bytes(b'invalid candidate executable')
        (fresh / 'portable.json').write_text(json.dumps({'schemaVersion': 1, 'activeBuild': 'broken-candidate'}))
        recovered = launch(fresh)
        journal = json.loads((fresh / 'maintenance/update.json').read_text(encoding='utf-8'))
        assert journal['phase'] == 'rolled_back'
        assert json.loads((fresh / 'instance.json').read_text(encoding='utf-8'))['activeBuild'] == current['activeBuild']
        stop(recovered)
        report['failedRealCandidateRollsBack'] = True
    finally:
        for process in processes:
            stop(process)
        for root in installed:
            if (root / 'uninstall.exe').exists():
                result = invoke(root / 'uninstall.exe', '/S', f'_?={root}')
                assert result.returncode == 0
                deadline = time.monotonic() + 60
                while (root / 'app').exists() and time.monotonic() < deadline:
                    time.sleep(.2)
                assert not (root / 'app').exists()
                assert (root / 'userdata/data/trailsnap.sqlite').is_file()
        if installed:
            report['uninstallRetainsDatabases'] = True
        cache.mkdir(parents=True, exist_ok=True)
        (cache / 'install-lifecycle-result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
