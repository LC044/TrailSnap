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
