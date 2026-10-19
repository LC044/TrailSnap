"""Real first-launch conversion, interrupted publication and cleanup authorization."""
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import uuid

import pytest
from alembic import command
from alembic.config import Config

from app.utils import automatic_upgrade as upgrade
from app.utils.portable_library import file_hash, write_json
from app.utils.desktop_verification import photo_paths

pytestmark = [pytest.mark.smoke, pytest.mark.module_system, pytest.mark.module_automatic_upgrade]


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path / '行影集'
    local = tmp_path / 'local'
    root.mkdir(); local.mkdir()
    monkeypatch.setenv('LOCALAPPDATA', str(local))
    write_json(root / 'portable.json', {'schemaVersion': 1, 'activeBuild': 'test-build'})
    return root, local


def library(source, monkeypatch):
    (source / 'data').mkdir(parents=True)
    database = source / 'data/trailsnap.sqlite'
    url = f'sqlite:///{database.as_posix()}'
    monkeypatch.setenv('TS_DB_URL', url)
    config = Config()
    config.set_main_option('script_location', str(Path(__file__).resolve().parents[2] / 'alembic_sqlite'))
    config.set_main_option('sqlalchemy.url', url)
    command.upgrade(config, 'head')
    owner, photo = str(uuid.uuid4()), str(uuid.uuid4())
    image = source / 'data/users' / owner / 'uploads/a.jpg'
    image.parent.mkdir(parents=True); image.write_bytes(b'original full photo' * 5000)
    with closing(sqlite3.connect(database)) as db, db:
        db.execute('INSERT INTO users(id,username,email,hashed_password,settings) VALUES (?,?,?,?,?)',
                   (owner, 'desktop-admin', 'desktop@trailsnap.app', 'hash', '{}'))
        db.execute("INSERT INTO photos(id,owner_id,file_path,file_type,is_deleted) VALUES (?,?,?,'image',0)",
                   (photo, owner, str(image)))
    write_json(source / 'data/system_config.json', {'security': {'secret_key': 'preserve-mobile-session'}})
    return database, image


def invoke(root, action, success=True):
    result = subprocess.run([sys.executable, 'desktop_entry.py', '--automatic-upgrade', str(root), action],
                            cwd=Path(__file__).resolve().parents[2], capture_output=True,
                            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}, timeout=90)
    assert (result.returncode == 0) == success, result.stderr.decode('utf-8')
    return json.loads(result.stdout) if success else result.stderr.decode('utf-8')


def test_clean_install_does_not_create_a_library_during_discovery(setup):
    root, local = setup
    assert invoke(root, 'prepare') == {'phase': 'none'}
    assert not (root / 'instance.json').exists()
    assert not (root / 'userdata').exists()
    assert not (local / 'TrailSnap').exists()


@pytest.mark.parametrize('location', ['overwritten-install', 'default', 'custom'])
def test_automatic_upgrade_stays_in_install_and_cleans_only_after_launch(setup, monkeypatch, location):
    root, local = setup
    source = root if location == 'overwritten-install' else local / ('TrailSnap' if location == 'default' else 'custom-photos')
    database, image = library(source, monkeypatch)
    original_hash = file_hash(database)
    ancillary = source / 'unrelated-before-copy.txt'; ancillary.write_text('keep in original location')
    if location == 'custom':
        write_json(local / 'TrailSnap-desktop.json', {'root': str(source), 'server_port': 18223})
    assert invoke(root, 'prepare') == {'phase': 'published'}
    assert file_hash(database) == original_hash
    assert image.is_file()
    data = root / 'userdata'
    with closing(sqlite3.connect(data / 'data/trailsnap.sqlite')) as db:
        copied = Path(list(photo_paths(db, data))[0][2])
    assert file_hash(copied) == file_hash(image)
    assert json.loads((data / 'data/system_config.json').read_text(encoding='utf-8'))['security']['secret_key'] == 'preserve-mobile-session'
    if location == 'custom':
        assert json.loads((root / 'instance.json').read_text(encoding='utf-8'))['serverPort'] == 18223
    assert '禁止清理' in invoke(root, 'cleanup', success=False)
    assert file_hash(database) == original_hash
    invoke(root, 'validated')
    unknown = source / 'keep-unrelated.txt'; unknown.write_text('not copied; must stay')
    invoke(root, 'cleanup')
    assert not database.exists() and not image.exists()
    assert unknown.read_text(encoding='utf-8') == 'not copied; must stay'
    assert ancillary.read_text(encoding='utf-8') == 'keep in original location'
    assert copied.is_file() and (root / 'portable.json').is_file()
    assert invoke(root, 'cleanup') == {'phase': 'completed'}
    assert invoke(root, 'prepare') == {'phase': 'completed'}


def test_multiple_sources_do_not_create_an_empty_library(setup, monkeypatch):
    root, local = setup
    library(root, monkeypatch); library(local / 'TrailSnap', monkeypatch)
    assert '多个' in invoke(root, 'prepare', success=False)
    assert not (root / 'instance.json').exists()
    assert not (root / 'userdata').exists()


def test_nonempty_userdata_is_preserved(setup, monkeypatch):
    root, _ = setup
    library(root, monkeypatch)
    (root / 'userdata').mkdir(); (root / 'userdata/keep').write_text('existing')
    assert '已有数据' in invoke(root, 'prepare', success=False)
    assert (root / 'userdata/keep').read_text(encoding='utf-8') == 'existing'
    assert not (root / 'instance.json').exists()


def test_copy_failure_can_restart_without_deleting_source(setup, monkeypatch):
    root, _ = setup
    database, _ = library(root, monkeypatch)
    original = file_hash(database)
    with monkeypatch.context() as patch:
        def fail(_):
            raise OSError('injected schema failure')
        patch.setattr(upgrade, '_prepare', fail)
        with pytest.raises(OSError, match='injected'):
            upgrade.prepare(root)
    assert not (root / 'instance.json').exists()
    assert file_hash(database) == original
    assert invoke(root, 'prepare') == {'phase': 'published'}


def test_progress_pause_during_streaming_copy_preserves_source_and_can_retry(setup, monkeypatch):
    from app.utils.upgrade_progress import UpgradeProgress
    root, _ = setup
    database, image = library(root, monkeypatch)
    (root / 'data/large-cache.bin').write_bytes(b'large cache' * (256 * 1024))
    original = file_hash(database), file_hash(image)
    monkeypatch.setenv('TS_AUTOMATIC_UPGRADE_SESSION', 'test-pause-session')
    report = UpgradeProgress.report
    seen = []

    def pause_during_copy(self, stage=None, completed=0, total=0, **kwargs):
        report(self, stage, completed, total, **kwargs)
        seen.append((stage, completed, total, kwargs.get('unit')))
        if stage == 'copying' and completed > 0:
            write_json(root / 'maintenance/automatic-upgrade-cancel.json', {'session': self.session})

    with monkeypatch.context() as patch:
        patch.setattr(UpgradeProgress, 'report', pause_during_copy)
        with pytest.raises(ValueError, match='TRAILSNAP_UPGRADE_PAUSED'):
            upgrade.prepare(root)
    assert (file_hash(database), file_hash(image)) == original
    assert not (root / 'instance.json').exists()
    assert not (root / 'userdata').exists()
    assert any(stage == 'copying' and 0 < done <= total and unit == 'bytes' for stage, done, total, unit in seen)
    assert not list(root.parent.glob('.trailsnap-auto-*/.trailsnap-migration-*'))
    (root / 'maintenance/automatic-upgrade-cancel.json').unlink()
    assert invoke(root, 'prepare') == {'phase': 'published'}
    status = json.loads((root / 'maintenance/automatic-upgrade-progress.json').read_text(encoding='utf-8'))
    assert status['session'] == 'test-pause-session' and status['stage'] == 'launching'
    assert status['cancellable'] is False
    assert database.is_file() and image.is_file()


def test_pause_is_session_bound_and_does_not_interrupt_critical_phase(tmp_path, monkeypatch):
    from app.utils.upgrade_progress import UpgradeProgress
    monkeypatch.setenv('TS_AUTOMATIC_UPGRADE_SESSION', 'current')
    progress = UpgradeProgress(tmp_path)
    write_json(tmp_path / 'maintenance/automatic-upgrade-cancel.json', {'session': 'stale'})
    progress.report('copying', 1, 4, unit='bytes')
    progress.report('database', cancellable=False)
    write_json(tmp_path / 'maintenance/automatic-upgrade-cancel.json', {'session': 'current'})
    progress.checkpoint()
    progress.report('verifying', 0, 3, unit='photos')
    with pytest.raises(ValueError, match='TRAILSNAP_UPGRADE_PAUSED'):
        progress.checkpoint()


def test_pause_removes_readonly_scratch_copy_without_changing_source_permissions(tmp_path):
    import stat
    from app.utils.desktop_data_migration import migrate_data_directory
    source = tmp_path / 'source'; source.mkdir()
    original = source / 'readonly.bin'; original.write_bytes(b'original bytes')
    original.chmod(stat.S_IREAD)
    target = tmp_path / 'new-library'
    def pause(done, total):
        raise ValueError('safe pause after copied file')
    try:
        before = original.stat().st_mode
        with pytest.raises(ValueError, match='safe pause'):
            migrate_data_directory(source, target, checkpoint=lambda: None, progress=pause)
        assert original.read_bytes() == b'original bytes'
        assert original.stat().st_mode == before
        assert not target.exists()
        assert not list(tmp_path.glob('.trailsnap-migration-*'))
    finally:
        original.chmod(stat.S_IREAD | stat.S_IWRITE)


def test_interruption_after_userdata_rename_recovers_configuration(setup, monkeypatch):
    root, _ = setup
    database, _ = library(root, monkeypatch)
    invoke(root, 'prepare')
    journal = root / 'maintenance/automatic-upgrade.json'
    job = json.loads(journal.read_text(encoding='utf-8')); job['phase'] = 'prepared'; write_json(journal, job)
    (root / 'instance.json').unlink()
    assert invoke(root, 'prepare') == {'phase': 'published'}
    assert json.loads((root / 'instance.json').read_text(encoding='utf-8'))['instanceId'] == job['instance']['instanceId']
    assert database.is_file()


def test_changed_source_or_broken_target_blocks_cleanup(setup, monkeypatch):
    root, _ = setup
    database, image = library(root, monkeypatch)
    invoke(root, 'prepare'); invoke(root, 'validated')
    image.write_bytes(b'new work in old app')
    assert '旧数据已变化' in invoke(root, 'cleanup', success=False)
    assert database.is_file() and image.is_file()


def test_target_damage_past_sample_prefix_prevents_source_cleanup(setup, monkeypatch):
    root, _ = setup
    database, image = library(root, monkeypatch)
    invoke(root, 'prepare'); invoke(root, 'validated')
    data = root / 'userdata'
    with closing(sqlite3.connect(data / 'data/trailsnap.sqlite')) as db:
        copied = Path(list(photo_paths(db, data))[0][2])
    with copied.open('r+b') as stream:
        stream.seek(70000); stream.write(b'BROKEN AFTER PREFIX')
    assert '无法验证' in invoke(root, 'cleanup', success=False)
    assert database.is_file() and image.is_file()


def test_external_original_is_not_in_upgrade_proof_and_old_journal_can_finish(setup, monkeypatch, tmp_path):
    root, _ = setup
    database, image = library(root, monkeypatch)
    external = tmp_path / 'external.jpg'
    external.write_bytes(b'external original')
    with closing(sqlite3.connect(database)) as db, db:
        owner = db.execute('SELECT id FROM users').fetchone()[0]
        db.execute("INSERT INTO photos(id,owner_id,file_path,file_type,is_deleted) VALUES (?,?,?,'image',0)",
                   ('external', owner, str(external)))
    invoke(root, 'prepare')
    journal = root / 'maintenance/automatic-upgrade.json'
    job = json.loads(journal.read_text(encoding='utf-8'))
    assert len(job['media']) == 1
    # A published journal from the original 0.18.0 included external media.
    job['media'].append({'id': 'external', 'sha256': file_hash(external)})
    write_json(journal, job)
    external.write_bytes(b'legitimate edit in another application')
    invoke(root, 'validated')
    invoke(root, 'cleanup')
    assert external.read_bytes() == b'legitimate edit in another application'
    assert not database.exists() and not image.exists()
    assert (root / 'userdata/data/trailsnap.sqlite').is_file()


def test_legacy_copied_record_redirected_outside_target_never_allows_source_cleanup(setup, monkeypatch):
    root, _ = setup
    database, image = library(root, monkeypatch)
    invoke(root, 'prepare')
    journal = root / 'maintenance/automatic-upgrade.json'
    job = json.loads(journal.read_text(encoding='utf-8'))
    for item in job['media']:
        item.pop('copied')
    write_json(journal, job)
    with closing(sqlite3.connect(root / 'userdata/data/trailsnap.sqlite')) as db, db:
        db.execute('UPDATE photos SET file_path=?,storage_root_id=NULL,storage_relative_path=NULL', (str(image),))
    invoke(root, 'validated')
    assert '路径超出新图库' in invoke(root, 'cleanup', success=False)
    assert database.is_file() and image.is_file()


def test_source_lock_prevents_copy_while_legacy_app_is_running(setup, monkeypatch):
    if os.name != 'nt':
        pytest.skip('legacy Windows lock')
    root, _ = setup
    database, _ = library(root, monkeypatch)
    with upgrade._legacy_lock(root):
        assert '仍在使用' in invoke(root, 'prepare', success=False)
    assert database.is_file() and not (root / 'userdata').exists()


def test_old_sqlite_writer_blocks_migration_even_without_pointer_lock(setup, monkeypatch):
    if os.name != 'nt':
        pytest.skip('Windows sharing protection')
    root, _ = setup
    database, _ = library(root, monkeypatch)
    with closing(sqlite3.connect(database)) as writer:
        writer.execute('BEGIN IMMEDIATE')
        assert '仍在使用' in invoke(root, 'prepare', success=False)
        writer.rollback()
    assert database.is_file() and not (root / 'userdata').exists()


def test_user_can_resolve_ambiguous_sources_without_creating_a_blank_library(setup, monkeypatch):
    root, local = setup
    library(root, monkeypatch); library(local / 'TrailSnap', monkeypatch)
    write_json(root / 'maintenance/automatic-upgrade-source.json', {'source': str(root)})
    assert invoke(root, 'prepare') == {'phase': 'published'}
    assert (local / 'TrailSnap/data/trailsnap.sqlite').is_file()


@pytest.mark.parametrize('count', [0, 1, 2])
def test_installation_detection_preserves_chinese_path_and_reports_multiple(tmp_path, count):
    if os.name != 'nt':
        pytest.skip('Windows registry')
    import winreg
    product = 'TrailSnap-req165-' + uuid.uuid4().hex
    prefix = 'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\'
    keys = []
    output = tmp_path / 'result.txt'
    script = Path(__file__).resolve().parents[3] / 'desktop/src-tauri/windows/find-installed-directory.ps1'
    try:
        for index in range(count):
            install = tmp_path / f'中文安装-{index}'; install.mkdir()
            (install / 'uninstall.exe').write_bytes(b'fixture')
            (install / 'trailsnap-desktop.exe').write_bytes(b'fixture')
            key = prefix + product + '-' + str(index); keys.append(key)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as handle:
                winreg.SetValueEx(handle, 'InstallLocation', 0, winreg.REG_SZ, str(install))
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-File', str(script),
                                 '-ProductName', product, '-OutputFile', str(output)], capture_output=True, timeout=30)
        assert result.returncode == (2 if count == 2 else 0), result.stderr.decode(errors='replace')
        found = output.read_text(encoding='utf-16-le').splitlines()
        assert found == [str(tmp_path / f'中文安装-{index}') for index in range(count)]
    finally:
        for key in keys:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)


def test_progress_sharing_violation_does_not_abort_migration_or_disable_pause(tmp_path, monkeypatch):
    from app.utils import upgrade_progress
    monkeypatch.setenv('TS_AUTOMATIC_UPGRADE_SESSION', 'active-session')
    progress = upgrade_progress.UpgradeProgress(tmp_path)
    original = upgrade_progress.write_json
    def busy(*args, **kwargs):
        raise PermissionError('progress reader temporarily denies replacement')
    monkeypatch.setattr(upgrade_progress, 'write_json', busy)
    progress.report('copying', 1, 10)
    monkeypatch.setattr(upgrade_progress, 'write_json', original)
    progress.report('copying', 10, 10)
    path = tmp_path / 'maintenance/automatic-upgrade-progress.json'
    assert json.loads(path.read_text(encoding='utf-8'))['completed'] == 10
    original(tmp_path / 'maintenance/automatic-upgrade-cancel.json', {'session': 'active-session'})
    with pytest.raises(ValueError, match='TRAILSNAP_UPGRADE_PAUSED'):
        progress.checkpoint()


def test_same_version_reinstallation_repairs_program_without_replacing_data(tmp_path):
    from app.utils.desktop_layout import stage_program
    program, server, root = (tmp_path / name for name in ('program', 'server', 'installed'))
    program.mkdir(); server.mkdir()
    (program / 'trailsnap-desktop.exe').write_bytes(b'GOOD SHELL')
    (server / 'trailsnap-server.exe').write_bytes(b'GOOD BACKEND')
    launcher = tmp_path / 'launcher.exe'; launcher.write_bytes(b'LAUNCHER')
    catalog = tmp_path / 'catalog.json'; catalog.write_text('{}')
    build = stage_program(root, program, server, launcher, catalog, '0.17.4', 'x86_64')
    write_json(root / 'instance.json', {'identity': 'unchanged'})
    (root / 'userdata').mkdir(); (root / 'userdata/keep').write_bytes(b'USER DATA')
    (root / 'app' / build / 'trailsnap-desktop.exe').write_bytes(b'BROKEN')
    (root / 'app' / build / 'server/trailsnap-server.exe').unlink()
    assert stage_program(root, program, server, launcher, catalog, '0.17.4', 'x86_64') == build
    assert (root / 'app' / build / 'trailsnap-desktop.exe').read_bytes() == b'GOOD SHELL'
    assert (root / 'app' / build / 'server/trailsnap-server.exe').read_bytes() == b'GOOD BACKEND'
    assert (root / 'userdata/keep').read_bytes() == b'USER DATA'
    assert json.loads((root / 'instance.json').read_text(encoding='utf-8')) == {'identity': 'unchanged'}
