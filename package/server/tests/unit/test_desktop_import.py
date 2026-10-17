"""User-facing upgrade discovery, safe retry and complete custom-storage copies."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import uuid

import pytest
from alembic import command
from alembic.config import Config
from app.utils.desktop_import import discover_libraries, cleanup_staging, conversion_space
from app.utils.portable_config import transform_paths
from app.utils.desktop_verification import photo_paths

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def test_native_helper_outputs_utf8_even_when_interpreter_starts_with_gbk(tmp_path):
    old, current = tmp_path / '旧版目录', tmp_path / 'current'
    small_library(old, 1)
    small_library(current, 0)
    code = "import sys; sys.stdout.reconfigure(encoding='gbk'); sys.stderr.reconfigure(encoding='gbk'); import desktop_entry; sys.argv=['desktop_entry.py','--discover-old-data',*sys.argv[1:]]; desktop_entry.main()"
    result = subprocess.run([sys.executable, '-c', code, str(old), str(current)], capture_output=True,
                            env={**os.environ, 'LOCALAPPDATA': str(tmp_path / 'empty-local')}, timeout=30)
    assert result.returncode == 0, result.stderr.decode('utf-8')
    discovery = json.loads(result.stdout.decode('utf-8'))
    assert discovery['candidates'][0]['path'] == str(old.resolve())


def test_legacy_photo_without_upload_time_can_be_listed():
    from app.schemas.photo import Photo
    from app.db.models.photo import FileType
    photo_id = uuid.uuid4()
    photo = Photo(id=photo_id, file_type=FileType.image, size=1,
                  file_path='C:/legacy/a.jpg', upload_time=None)
    result = photo.model_dump(mode='json')
    assert result['id'] == str(photo_id)
    assert 'upload_time' not in result


@pytest.mark.parametrize('layout', ['managed-organize', 'legacy-internal', 'zero-photos'])
def test_copy_final_paths_and_retained_entry_survive_move(tmp_path, monkeypatch, layout):
    source, program, target = [tmp_path / name for name in ('source', 'program', 'copy')]
    (source / 'data/organized').mkdir(parents=True)
    (program / 'server').mkdir(parents=True)
    owner, photo, ref = [str(uuid.uuid4()) for _ in range(3)]
    database = source / 'data/trailsnap.sqlite'
    url = f'sqlite:///{database.as_posix()}'
    monkeypatch.setenv('TS_DB_URL', url)
    config = Config()
    config.set_main_option('script_location', str(Path(__file__).resolve().parents[2] / 'alembic_sqlite'))
    config.set_main_option('sqlalchemy.url', url)
    command.upgrade(config, 'head')
    original = source / 'data/organized/a.jpg'
    original.write_bytes(b'photo in a custom internal folder')
    with closing(sqlite3.connect(database)) as db, db:
        db.execute('INSERT INTO users(id,username,email,hashed_password,settings) VALUES (?,?,?,?,?)',
                   (owner, 'desktop-admin', 'desktop@trailsnap.app', 'hash', '{}'))
        if layout != 'zero-photos':
            db.execute("INSERT INTO photos(id,owner_id,file_path,file_type,is_deleted) VALUES (?,?,?,'image',0)",
                       (photo, owner, str(original)))
        if layout == 'managed-organize':
            db.execute('INSERT INTO storage_roots(id,owner_id,name,kind,location) VALUES (?,?,?,?,?)',
                       (ref, owner, '整理目录', 'managed', 'data/organized'))
            db.execute('UPDATE photos SET storage_root_id=?,storage_relative_path=?', (ref, 'a.jpg'))
    (source / 'library.json').write_text(json.dumps({'schemaVersion': 1, 'pathFormat': 1,
        'libraryId': str(uuid.uuid4()), 'lastRoot': str(source), 'initialized': True}), encoding='utf-8')
    for relative in ('trailsnap-desktop.exe', 'server/trailsnap-server.exe', 'launcher.exe'):
        (program / relative).write_bytes(b'program fixture')
    environment = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'TS_IMPORT_PREVIOUS_DATA': str(source),
                   'TS_IMPORT_ORIGIN': str(program), 'TS_IMPORT_ORIGIN_ID': 'original-instance'}
    result = subprocess.run([sys.executable, 'desktop_entry.py', '--convert-portable', str(source), str(target),
                             str(program), str(program / 'launcher.exe'), '--copy-external'],
                            capture_output=True, env=environment, timeout=90)
    assert result.returncode == 0, result.stderr.decode('utf-8')
    proof = json.loads((target / 'conversion.json').read_text(encoding='utf-8'))
    assert proof['previousEntry'] == str(program)  # Also preserve accounts/settings without photos.
    assert proof['verified'] is True
    from app.utils.desktop_verification import verify_media
    verify_media(target / 'userdata', proof['media'])
    moved = tmp_path / '搬迁后的图库'
    target.rename(moved)
    result = subprocess.run([sys.executable, 'desktop_entry.py', '--prepare-portable', str(moved / 'userdata')],
                            capture_output=True, env=environment, timeout=90)
    assert result.returncode == 0, result.stderr.decode('utf-8')
    verify_media(moved / 'userdata', proof['media'])
    if layout != 'zero-photos':
        with closing(sqlite3.connect(moved / 'userdata/data/trailsnap.sqlite')) as db:
            copied = Path(list(photo_paths(db, moved / 'userdata'))[0][2])
        assert copied.read_bytes() == original.read_bytes()
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session
        from app.db.models import Photo
        monkeypatch.setenv('TS_DESKTOP', '1')
        monkeypatch.setenv('TS_DESKTOP_PORTABLE', '1')
        monkeypatch.setenv('TS_DESKTOP_ROOT', str(moved / 'userdata'))
        engine = create_engine(f'sqlite:///{(moved / "userdata/data/trailsnap.sqlite").as_posix()}')
        try:
            with Session(engine) as session:
                assert session.scalar(select(Photo.id).where(Photo.file_path == str(copied))) == uuid.UUID(photo)
        finally:
            engine.dispose()
        copied.unlink()
        with pytest.raises(ValueError, match='升级前可读取'):
            verify_media(moved / 'userdata', proof['media'])


@pytest.mark.skipif(os.name != 'nt', reason='Windows installer process protection')
def test_installer_refuses_running_sidecar_without_terminating_it(tmp_path):
    import shutil
    executable = tmp_path / 'trailsnap-server.exe'
    shutil.copy2(Path(os.environ['SystemRoot']) / 'System32/cmd.exe', executable)
    child = subprocess.Popen([str(executable), '/d', '/c', 'set /p waiting='], stdin=subprocess.PIPE,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=subprocess.CREATE_NO_WINDOW)
    script = Path(__file__).resolve().parents[3] / 'desktop/src-tauri/windows/stop-installed-processes.ps1'
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                                 '-File', str(script), '-InstallDirectory', str(tmp_path)], capture_output=True, timeout=30)
        assert result.returncode != 0
        assert b'TrailSnap is still running' in result.stderr
        assert child.poll() is None
    finally:
        child.communicate(b'finished\r\n', timeout=10)


@pytest.mark.skipif(os.name != 'nt', reason='Windows resource staging')
@pytest.mark.parametrize('layout', ['program-only', 'configured-library', 'unconfigured-library'])
def test_installer_cleans_only_obsolete_program_resources(tmp_path, layout):
    server = tmp_path / 'server'
    server.mkdir()
    (server / 'obsolete.dll').write_bytes(b'old runtime')
    (tmp_path / 'userdata').mkdir()
    (tmp_path / 'userdata/keep').write_bytes(b'user data')
    (tmp_path / 'instance.json').write_text(json.dumps({'dataRoot': {
        'kind': 'relative', 'path': 'server/library' if layout == 'configured-library' else 'userdata'}}))
    if layout == 'unconfigured-library':
        (server / 'trailsnap.sqlite').write_bytes(b'preserve historical data')
    script = Path(__file__).resolve().parents[3] / 'desktop/src-tauri/windows/stop-installed-processes.ps1'
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                             '-File', str(script), '-InstallDirectory', str(tmp_path), '-PrepareInstall'],
                            capture_output=True, timeout=30)
    if layout == 'program-only':
        assert result.returncode == 0, result.stderr.decode(errors='replace')
        assert not server.exists()
    else:
        assert result.returncode != 0
        assert (server / 'obsolete.dll').is_file()
    assert (tmp_path / 'userdata/keep').read_bytes() == b'user data'


@pytest.mark.skipif(os.name != 'nt', reason='Windows uninstall registry migration')
@pytest.mark.parametrize('same_installation', [True, False])
def test_installer_migrates_only_its_own_legacy_uninstall_entry(tmp_path, same_installation):
    import winreg
    product = 'TrailSnap-fixture-' + uuid.uuid4().hex
    prefix = 'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\'
    old_key, new_key = prefix + product, prefix + product + '-new-instance'
    script = Path(__file__).resolve().parents[3] / 'desktop/src-tauri/windows/migrate-installed-identity.ps1'
    try:
        for name, location in ((old_key, tmp_path if same_installation else tmp_path / 'another-installation'), (new_key, tmp_path)):
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, name) as key:
                winreg.SetValueEx(key, 'InstallLocation', 0, winreg.REG_SZ, f'"{location}"')
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                                 '-File', str(script), '-InstallDirectory', str(tmp_path), '-InstanceTag', 'new-instance',
                                 '-ProductName', product], capture_output=True, timeout=30)
        assert result.returncode == 0, result.stderr.decode(errors='replace')
        if same_installation:
            with pytest.raises(FileNotFoundError):
                winreg.OpenKey(winreg.HKEY_CURRENT_USER, old_key)
        else:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, old_key):
                pass
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, new_key):
            pass
    finally:
        for name in (old_key, new_key):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, name)
            except FileNotFoundError:
                pass


def small_library(path, count=1):
    (path / 'data').mkdir(parents=True)
    with closing(sqlite3.connect(path / 'data/trailsnap.sqlite')) as db, db:
        db.execute('CREATE TABLE photos(id TEXT)')
        db.executemany('INSERT INTO photos VALUES (?)', [(str(n),) for n in range(count)])


def test_discovery_is_read_only_distinguishes_clean_install_and_custom_old_location(tmp_path):
    installation, current, local = tmp_path / 'program', tmp_path / 'program/userdata', tmp_path / 'local'
    current.mkdir(parents=True)
    local.mkdir()
    assert discover_libraries(installation, current, local)['candidates'] == []
    # A stale/missing default directory must not be created during discovery.
    assert not (local / 'TrailSnap').exists()
    old = tmp_path / 'my-photos'
    small_library(old, 7)
    pointer = local / 'TrailSnap-desktop.json'
    pointer.write_text(json.dumps({'root': str(old)}), encoding='utf-8')
    before = (old / 'data/trailsnap.sqlite').read_bytes()
    result = discover_libraries(installation, current, local)
    assert result['candidates'] == [{'path': str(old.resolve()), 'photos': 7, 'error': None}]
    assert (old / 'data/trailsnap.sqlite').read_bytes() == before
    assert not (old / 'library.json').exists()
    assert not (old / '.instance.lock').exists()
    old.rename(tmp_path / 'offline')
    result = discover_libraries(installation, current, local)
    assert result['candidates'] == []
    assert '原磁盘' in result['notices'][0]


def test_overwritten_install_and_corrupt_pointer_report_sources_without_switching(tmp_path):
    current = tmp_path / 'program/userdata'
    small_library(tmp_path / 'program', 2)
    small_library(current, 3)
    local = tmp_path / 'local'
    local.mkdir()
    (local / 'TrailSnap-desktop.json').write_text('broken')
    result = discover_libraries(current.parent, current, local)
    assert result['currentPhotos'] == 3
    assert len(result['candidates']) == 1
    assert result['notices']
    (current.parent / 'conversion.json').write_text('{}')
    assert discover_libraries(current.parent, current, local)['completed']


def test_cleanup_only_removes_owned_unpublished_sibling_and_preserves_saved_library(tmp_path):
    target = tmp_path / 'saved'
    target.mkdir()
    (target / 'keep.jpg').write_bytes(b'photo')
    operation = str(uuid.uuid4())
    stage = tmp_path / ('.trailsnap-portable-' + operation)
    stage.mkdir()
    (stage / 'import-operation.json').write_text(json.dumps({'operationId': operation, 'target': str(target.resolve())}))
    (stage / 'partial').write_bytes(b'incomplete')
    cleanup_staging(target, operation)
    assert not stage.exists()
    assert (target / 'keep.jpg').read_bytes() == b'photo'
    stage.mkdir()
    (stage / 'import-operation.json').write_text(json.dumps({'operationId': operation, 'target': 'another'}))
    with pytest.raises(ValueError, match='不属于'):
        cleanup_staging(target, operation)
    assert stage.is_dir()
    with pytest.raises(ValueError):
        cleanup_staging(target, '../saved')


def test_custom_storage_copy_keeps_originals_thumbnails_and_chunks_after_original_disk_disappears(tmp_path, monkeypatch):
    source, external, program, target = [tmp_path / name for name in ('old', 'external', 'program', 'copy')]
    (source / 'data').mkdir(parents=True)
    (program / 'server').mkdir(parents=True)
    owner, photo, operation = (str(uuid.uuid4()) for _ in range(3))
    user = external / 'users' / owner
    compact = photo.replace('-', '')
    thumb = Path('thumbnails') / compact[:2] / compact[2:4] / (compact + '-thumb.jpg')
    for relative, content in [('uploads/a.jpg', b'photo'), (thumb, b'thumbnail'), ('chunks/upload-id/0', b'chunk')]:
        path = user / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (user / 'config').mkdir()
    mirror = user / 'config/settings.json'
    mirror.write_text(json.dumps({'storage': {'photo_storage_path': str(external)}}))
    database = source / 'data/trailsnap.sqlite'
    url = f'sqlite:///{database.as_posix()}'
    monkeypatch.setenv('TS_DB_URL', url)
    config = Config()
    config.set_main_option('script_location', str(Path(__file__).resolve().parents[2] / 'alembic_sqlite'))
    config.set_main_option('sqlalchemy.url', url)
    command.upgrade(config, 'b0b9b9a3a2c0')
    with closing(sqlite3.connect(database)) as db, db:
        db.execute('INSERT INTO users(id,username,email,hashed_password,settings) VALUES (?,?,?,?,?)',
                   (owner, 'desktop-admin', 'desktop@trailsnap.app', 'hash', json.dumps({'storage': {'photo_storage_path': str(external)}})))
        db.execute("INSERT INTO photos(id,owner_id,file_path,file_type,is_deleted) VALUES (?,?,?,'image',0)", (photo, owner, str(user / 'uploads/a.jpg')))
    for path in (program / 'trailsnap-desktop.exe', program / 'server/trailsnap-server.exe', program / 'launcher.exe'):
        path.write_bytes(b'program-fixture')
    # Full external sizes and database snapshots must be included before stopping services.
    # Do not stop services or start copying into a folder being copied/scanned.
    for copy_external in (False, True):
        with pytest.raises(ValueError, match='外部照片文件夹'):
            conversion_space(source, user / 'backup', program, copy_external)
    space = conversion_space(source, target, program, True)
    assert space['externalBytes'] == len(b'photo') + len(b'thumbnail') + len(b'chunk') + mirror.stat().st_size
    assert space['requiredBytes'] > space['externalBytes'] + database.stat().st_size
    result = subprocess.run([sys.executable, 'desktop_entry.py', '--convert-portable', str(source), str(target), str(program), str(program / 'launcher.exe'), '--copy-external'],
                            cwd=Path(__file__).resolve().parents[2], env={**os.environ, 'TS_IMPORT_OPERATION': operation, 'TS_IMPORT_PREVIOUS_DATA': str(source), 'TS_IMPORT_ORIGIN': str(program), 'TS_IMPORT_ORIGIN_ID': 'before-import', 'PYTHONIOENCODING': 'utf-8'}, capture_output=True, timeout=90)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    assert 'importProgress' in result.stderr.decode('utf-8')
    proof = json.loads((target / 'conversion.json').read_text())
    assert proof['operationId'] == operation
    assert proof['previousEntry'] == str(program)
    assert proof['previousInstanceId'] == 'before-import'
    assert proof['externalReferencesRetained'] is False
    external.rename(tmp_path / 'offline')
    # Candidate startup must also rebase copied user configuration and snapshot it.
    prepared = subprocess.run([sys.executable, 'desktop_entry.py', '--prepare-portable', str(target / 'userdata')],
                              cwd=Path(__file__).resolve().parents[2], env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}, capture_output=True, timeout=60)
    assert prepared.returncode == 0, prepared.stderr.decode(errors='replace')
    with closing(sqlite3.connect(target / 'userdata/data/trailsnap.sqlite')) as db:
        settings = transform_paths(json.loads(db.execute('SELECT settings FROM users WHERE id=?', (owner,)).fetchone()[0]), encode=False, root=target / 'userdata')
        assert Path(list(photo_paths(db, target / 'userdata'))[0][2]).read_bytes() == b'photo'
    base = Path(settings['storage']['photo_storage_path']) / 'users' / owner
    assert (base / thumb).read_bytes() == b'thumbnail'
    assert (base / 'chunks/upload-id/0').read_bytes() == b'chunk'
    from app.utils.portable_library import configuration_files
    assert base / 'config/settings.json' in configuration_files(target / 'userdata')
    assert Path(json.loads((base / 'config/settings.json').read_text())['storage']['photo_storage_path']) == base.parent.parent
    assert (source / 'data/trailsnap.sqlite').is_file()
