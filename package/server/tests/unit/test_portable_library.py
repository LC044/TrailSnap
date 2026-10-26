"""Portable relocation, ownership, SQL lookup and legacy upgrade regressions."""
import json
import os
import sqlite3
import uuid
from pathlib import Path
from contextlib import closing
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from alembic import command
from alembic.config import Config
from app.utils.portable_library import snapshot_library, restore_library, prepare_portable_library
from app.utils.portable_config import transform_paths
from app.service import storage_paths

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def portable_env(monkeypatch, root):
    monkeypatch.setenv("TS_DESKTOP", "1")
    monkeypatch.setenv("TS_DESKTOP_PORTABLE", "1")
    monkeypatch.setenv("TS_DESKTOP_ROOT", str(root))
    monkeypatch.setattr(storage_paths, "_roots", {})


def test_preview_wrong_data_level_identifies_correct_parent_without_creating_database(tmp_path):
    from app.utils.portable_conversion import preview_conversion
    data = tmp_path / 'old-library/data'
    data.mkdir(parents=True)
    (data / 'trailsnap.sqlite').write_bytes(b'not opened during path validation')
    with pytest.raises(ValueError, match='选中了 data 子文件夹') as error:
        preview_conversion(data)
    assert str(data.parent) in str(error.value)
    assert not (data / 'data').exists()


def test_preview_missing_directory_is_actionable(tmp_path):
    from app.utils.portable_conversion import preview_conversion
    missing = tmp_path / 'missing'
    with pytest.raises(ValueError, match='旧数据目录不存在或无法访问'):
        preview_conversion(missing)
    assert not missing.exists()


def test_preview_instance_root_does_not_silently_choose_userdata(tmp_path):
    from app.utils.portable_conversion import preview_conversion
    data = tmp_path / 'userdata/data'
    data.mkdir(parents=True)
    (data / 'trailsnap.sqlite').write_bytes(b'not opened')
    with pytest.raises(ValueError, match='这里是新版本的实例目录') as error:
        preview_conversion(tmp_path)
    assert str(tmp_path / 'userdata') in str(error.value)


def test_preview_invalid_database_reports_readable_error(tmp_path):
    from app.utils.portable_conversion import preview_conversion
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data/trailsnap.sqlite').write_bytes(b'not a database')
    with pytest.raises(ValueError, match='无法读取旧图库数据库'):
        preview_conversion(tmp_path)


def test_preview_cli_returns_help_instead_of_a_python_traceback(tmp_path):
    import subprocess
    import sys
    data = tmp_path / 'data'
    data.mkdir()
    (data / 'trailsnap.sqlite').write_bytes(b'not opened')
    result = subprocess.run([sys.executable, 'desktop_entry.py', '--preview-portable', str(data)],
                            cwd=Path(__file__).resolve().parents[2], capture_output=True,
                            env={**os.environ, 'PYTHONIOENCODING':'utf-8'}, timeout=30)
    error = result.stderr.decode('utf-8')
    assert result.returncode == 1
    assert '选中了 data 子文件夹' in error
    assert str(tmp_path) in error
    assert 'Traceback' not in error


@pytest.mark.skipif(os.name != 'nt', reason='Windows folder-picker paths')
def test_preview_accepts_windows_extended_folder_picker_paths(tmp_path):
    from app.utils.portable_conversion import validate_library_source
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data/trailsnap.sqlite').write_bytes(b'not opened')
    root = validate_library_source(Path('\\\\?\\' + str(tmp_path.resolve())))
    assert root == tmp_path.resolve()
    assert not root.as_uri().startswith('file://%3F')


def test_path_references_relocate_for_files_and_sql_queries(tmp_path, monkeypatch):
    import app.db.models
    from app.db.base import Base
    from app.db.models import User, Photo, StorageRoot
    from app.crud.photo_paths import under_directory
    old, new = tmp_path / "old", tmp_path / "新位置"
    old.mkdir()
    new.mkdir()
    portable_env(monkeypatch, old)
    owner, root_id = uuid.uuid4(), uuid.uuid4()
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    relative = f"data/users/{owner}/uploads"
    with Session(engine) as db:
        db.add(User(id=owner, username="portable", email="p@example.com", hashed_password="unused"))
        db.add(StorageRoot(id=root_id, owner_id=owner, name="uploads", kind="managed", location=relative))
        db.commit()
        photo = Photo(id=uuid.uuid4(), owner_id=owner, file_path=str(old / relative / "a.jpg"), file_type="image")
        storage_paths.warm_roots(db)
        storage_paths.apply_photo_reference(photo, db)
        db.add(photo)
        db.commit()
        photo_id = photo.id
        monkeypatch.setenv("TS_DESKTOP_ROOT", str(new))
        db.expire_all()
        expected = str(new / relative / "a.jpg")
        assert db.get(Photo, photo_id).file_path == expected
        assert db.query(Photo.file_path).filter(Photo.file_path == expected).scalar() == expected
        assert db.query(Photo).filter(under_directory(str(new / relative))).count() == 1
        assert db.query(Photo).filter(Photo.file_path.in_([expected])).count() == 1
        with pytest.raises(ValueError, match="another user"):
            storage_paths.resolve_path(uuid.uuid4(), root_id, "a.jpg", db)
        photo = db.get(Photo, photo_id)
        photo.file_path = str(new / relative / "renamed.jpg")
        storage_paths.apply_photo_reference(photo, db)
        db.commit()
        assert photo.storage_relative_path == "renamed.jpg"
    engine.dispose()


@pytest.mark.parametrize("path", ["../escape", "C:\\outside\\a.jpg", "/outside", "a/../../b", "a//b", "a\x00b"])
def test_rejects_nonrelative_storage_paths(path):
    with pytest.raises(ValueError):
        storage_paths.validate_relative(path)


def test_json_fields_move_but_prompts_and_docker_paths_do_not(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    portable_env(monkeypatch, root)
    value = {"file_path": str(root / "data/a.jpg"), "prompt": str(root / "data/a.jpg"),
             "scan_roots": [str(root / "data")], "external_directories": [str(tmp_path / "external")]}
    encoded = transform_paths(value, encode=True)
    assert encoded["file_path"] == "ts-instance:/data/a.jpg"
    assert encoded["prompt"] == value["prompt"]
    monkeypatch.setenv("TS_DESKTOP_ROOT", str(tmp_path / "moved"))
    assert transform_paths(encoded, encode=False)["file_path"] == str(tmp_path / "moved/data/a.jpg")
    monkeypatch.delenv("TS_DESKTOP_PORTABLE")
    assert transform_paths(value, encode=True) == value


def test_snapshot_restores_database_and_config_as_a_set(tmp_path):
    root, backup = tmp_path / "library", tmp_path / "backup"
    (root / "data").mkdir(parents=True)
    database = root / "data/trailsnap.sqlite"
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("CREATE TABLE photos(id TEXT)")
        db.execute("INSERT INTO photos VALUES ('original')")
    config = root / "data/system_config.json"
    config.write_text('{"value":1}')
    snapshot_library(root, backup)
    snapshot_library(root, backup)  # Idempotent publication.
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("DELETE FROM photos")
    config.write_text('{"value":2}')
    (root / "library.json").write_text('{}')
    restore_library(root, backup)
    restore_library(root, backup)
    with closing(sqlite3.connect(database)) as db:
        assert db.execute("SELECT id FROM photos").fetchall() == [("original",)]
    assert json.loads(config.read_text()) == {"value": 1}
    assert not (root / "library.json").exists()


def test_snapshot_can_recover_after_portable_folder_moves_but_rejects_other_library(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    (root / "library.json").write_text(json.dumps({"libraryId": str(uuid.uuid4())}))
    backup = root / "backups/upgrade"
    snapshot_library(root, backup)
    moved = tmp_path / "moved"
    root.rename(moved)
    snapshot_library(moved, moved / "backups/upgrade")
    restore_library(moved, moved / "backups/upgrade")
    (moved / "library.json").write_text(json.dumps({"libraryId": str(uuid.uuid4())}))
    with pytest.raises(ValueError, match="another library"):
        restore_library(moved, moved / "backups/upgrade")


@pytest.mark.skipif(os.name != "nt", reason="Win32 CopyFile2 regression")
def test_copying_legacy_tree_supports_long_windows_destination_paths(tmp_path):
    from app.utils.desktop_data_migration import migrate_data_directory
    from app.utils.windows_paths import filesystem_path
    source = tmp_path / "source"
    leaf = source / "models" / ("a" * 100) / ("b" * 70 + ".bin")
    Path(filesystem_path(leaf.parent)).mkdir(parents=True)
    with open(filesystem_path(leaf), "wb") as stream:
        stream.write(b"model")
    target = tmp_path / ("destination-" + "x" * 70)
    migrate_data_directory(source,target)
    copied = target / leaf.relative_to(source)
    assert len(str(copied)) > 260
    with open(filesystem_path(copied),"rb") as stream:
        assert stream.read() == b"model"


@pytest.mark.skipif(os.name != "nt", reason="Win32 directory scanner handle regression")
def test_publish_retries_transient_windows_directory_handle(tmp_path, monkeypatch):
    from app.utils.windows_paths import publish_directory
    source, target = tmp_path / "staging", tmp_path / "published"
    source.mkdir()
    original = Path.rename
    attempts = []
    def rename(path, destination):
        attempts.append(path)
        if len(attempts) == 1: raise PermissionError("Temporary scanner handle")
        return original(path,destination)
    monkeypatch.setattr(Path,"rename",rename)
    publish_directory(source,target)
    assert len(attempts) == 2 and target.is_dir() and not source.exists()


def test_conversion_skips_browser_state_owned_by_the_running_ui(tmp_path):
    from app.utils.desktop_data_migration import migrate_data_directory
    source, target = tmp_path / "source", tmp_path / "copy"
    (source / "webview").mkdir(parents=True)
    (source / "webview/locked-profile").write_bytes(b"browser-state")
    (source / "original.jpg").write_bytes(b"photo")
    migrate_data_directory(source,target,skip_browser_state=True)
    assert (target / "original.jpg").read_bytes() == b"photo"
    assert not (target / "webview").exists()
    assert (source / "webview/locked-profile").read_bytes() == b"browser-state"


def test_additive_upgrade_keeps_legacy_records_then_explicitly_converts(tmp_path, monkeypatch):
    root = tmp_path / "library"
    (root / "data").mkdir(parents=True)
    database = root / "data/trailsnap.sqlite"
    url = f"sqlite:///{database.as_posix()}"
    monkeypatch.setenv("TS_DB_URL", url)
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic_sqlite"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "b0b9b9a3a2c0")
    owner, photo_id = str(uuid.uuid4()), str(uuid.uuid4())
    path = str(root / f"data/users/{owner}/uploads/a.jpg")
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("INSERT INTO users(id,username,email,hashed_password,settings) VALUES (?,?,?,?,?)", (owner,"legacy","l@example.com","hash","{}"))
        db.execute("INSERT INTO photos(id,owner_id,file_path,file_type,is_deleted) VALUES (?,?,?,?,0)", (photo_id,owner,path,"image"))
    command.upgrade(config, "head")
    with closing(sqlite3.connect(database)) as db:
        assert db.execute("SELECT file_path,storage_root_id FROM photos").fetchone() == (path, None)
    portable_env(monkeypatch, root)
    prepare_portable_library(root)
    with closing(sqlite3.connect(database)) as db:
        _, relative = db.execute("SELECT storage_root_id,storage_relative_path FROM photos").fetchone()
        assert relative == "uploads/a.jpg"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert prepare_portable_library(root)["initialized"]


def test_failed_photo_transaction_does_not_leave_a_nonexistent_cached_root(tmp_path, monkeypatch):
    import app.db.models
    from app.db.base import Base
    from app.db.models import User, Photo
    from app.db.session import SessionLocal
    root = tmp_path / "library"
    root.mkdir()
    (root / "library.json").write_text(json.dumps({"libraryId":str(uuid.uuid4())}))
    portable_env(monkeypatch,root)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    owner = uuid.uuid4()
    with SessionLocal(bind=engine) as db:
        db.add(User(id=owner,username="retry",email="retry@example.com",hashed_password="hash"))
        db.commit()
        photo = Photo(id=uuid.uuid4(),owner_id=owner,file_path=str(root / f"data/users/{owner}/uploads/a.jpg"),file_type="image")
        db.add(photo)
        db.flush()
        assert storage_paths._roots
        db.rollback()
        assert storage_paths._roots == {}
        retried = Photo(id=uuid.uuid4(),owner_id=owner,file_path=str(root / f"data/users/{owner}/uploads/a.jpg"),file_type="image")
        db.add(retried)
        db.commit()
        assert retried.storage_root_id is not None
    engine.dispose()


def test_conversion_closes_database_pool_before_publishing_directory(tmp_path, monkeypatch):
    import subprocess
    import sys
    source, program = tmp_path / "legacy", tmp_path / "program"
    (source / "data").mkdir(parents=True)
    (program / "server").mkdir(parents=True)
    database = source / "data/trailsnap.sqlite"
    url = f"sqlite:///{database.as_posix()}"
    monkeypatch.setenv("TS_DB_URL", url)
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic_sqlite"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "b0b9b9a3a2c0")
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("INSERT INTO users(id,username,email,hashed_password,settings) VALUES (?,?,?,?,?)",
                   (str(uuid.uuid4()), "desktop-admin", "desktop@trailsnap.app", "hash", "{}"))
    for path in (program / "trailsnap-desktop.exe", program / "server/trailsnap-server.exe", program / "launcher.exe"):
        path.write_bytes(b"program-fixture")
    (program / "ai").mkdir()
    (program / "ai/trailsnap-ai.exe").write_bytes(b"bundled-ai-fixture")
    # Cover an installer placed over its former data root: the new instance's
    # userdata and programs must not become nested copies inside the old library.
    (source / 'userdata/webview').mkdir(parents=True)
    (source / 'userdata/.instance.lock').write_bytes(b'live lock')
    (source / 'userdata/webview/browser-state').write_bytes(b'live browser')
    (source / 'app/build').mkdir(parents=True)
    (source / 'app/build/program').write_bytes(b'unrelated new build')
    (source / 'instance.json').write_text(json.dumps({'dataRoot':{'kind':'relative','path':'userdata'}}))
    target = tmp_path / "converted"
    result = subprocess.run([sys.executable, "desktop_entry.py", "--convert-portable", str(source), str(target),
                             str(program), str(program / "launcher.exe")],
                            cwd=Path(__file__).resolve().parents[2], capture_output=True, timeout=90)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert (target / "userdata/data/trailsnap.sqlite").is_file()
    assert not (target / 'userdata/userdata').exists()
    assert not (target / 'userdata/app').exists()
    assert not (target / 'userdata/instance.json').exists()
    assert (source / 'userdata/.instance.lock').read_bytes() == b'live lock'
    assert next((target / "app").glob("*/portable-launcher.exe")).read_bytes() == b"program-fixture"
    assert next((target / "app").glob("*/ai/trailsnap-ai.exe")).read_bytes() == b"bundled-ai-fixture"
    assert json.loads(next((target / "app").glob("*/manifest.json")).read_text())['minLauncherVersion'] == 2
    moved = target.with_name("moved")
    target.rename(moved)
    with closing(sqlite3.connect(moved / "userdata/data/trailsnap.sqlite")) as db:
        assert db.execute("PRAGMA quick_check").fetchone() == ("ok",)


def test_preview_decodes_references_against_explicit_source(tmp_path, monkeypatch):
    from app.utils.portable_conversion import preview_conversion
    root = tmp_path / 'library'
    (root / 'data/imported').mkdir(parents=True)
    monkeypatch.setenv('TS_DESKTOP_ROOT', str(tmp_path / 'unrelated-instance'))
    with closing(sqlite3.connect(root / 'data/trailsnap.sqlite')) as db, db:
        db.execute('CREATE TABLE users(id TEXT,settings TEXT)')
        db.execute('CREATE TABLE photos(id TEXT,owner_id TEXT,file_path TEXT)')
        db.execute('CREATE TABLE albums(id TEXT)')
        db.execute('CREATE TABLE tasks(id TEXT)')
        db.execute('INSERT INTO users VALUES (?,?)', ('owner',json.dumps({'storage':{'external_directories':['ts-instance:/data/imported']}})))
    assert preview_conversion(root)['externalRoots'] == []


def test_update_verification_rejects_loss_of_previously_readable_media(tmp_path):
    from app.utils.desktop_verification import media_baseline, verify_media
    root = tmp_path / 'library'
    (root / 'data').mkdir(parents=True)
    photo = root / 'data/a.jpg'
    photo.write_bytes(b'original')
    with closing(sqlite3.connect(root / 'data/trailsnap.sqlite')) as db, db:
        db.execute('CREATE TABLE photos(id TEXT,owner_id TEXT,file_path TEXT)')
        db.execute('INSERT INTO photos VALUES (?,?,?)', ('a','owner',str(photo)))
        db.execute('INSERT INTO photos VALUES (?,?,?)', ('offline','owner',str(root / 'missing.jpg')))
    baseline = media_baseline(root)
    assert len(baseline) == 1
    assert verify_media(root,baseline) == 1
    photo.unlink()
    with pytest.raises(ValueError,match='升级前可读取'):
        verify_media(root,baseline)


def test_existing_library_with_missing_database_never_creates_an_empty_replacement(tmp_path, monkeypatch):
    from desktop_entry import _prepare_desktop_database
    (tmp_path / 'data').mkdir()
    (tmp_path / 'library.json').write_text('{}')
    monkeypatch.setenv('TS_DATA_DIR', str(tmp_path / 'data'))
    with pytest.raises(RuntimeError,match='数据库缺失'):
        _prepare_desktop_database()
    assert not (tmp_path / 'data/trailsnap.sqlite').exists()


def test_installer_and_zip_share_layout_without_overwriting_instance_data(tmp_path):
    from app.utils.desktop_layout import stage_program, finalize_install
    source = tmp_path / 'installer'
    (source / 'server').mkdir(parents=True)
    (source / 'trailsnap-desktop.exe').write_bytes(b'shell__TAURI_BUNDLE_TYPE_VAR_UNK')
    (source / 'server/trailsnap-server.exe').write_bytes(b'server')
    (source / 'ai').mkdir()
    (source / 'ai/trailsnap-ai.exe').write_bytes(b'ai')
    for component in ('server', 'ai'):
        (source / component / 'runtime-version.json').write_text('{"version":"1.0.0"}')
    (source / 'portable-launcher.exe').write_bytes(b'launcher')
    (source / 'ai-extensions.json').write_text('{}')
    (source / 'instance.json').write_bytes(b'keep user config')
    (source / 'userdata').mkdir()
    (source / 'userdata/keep').write_bytes(b'photos')
    import platform
    arch = 'aarch64' if platform.machine().lower() in {'arm64','aarch64'} else 'x86_64'
    zip_root = tmp_path / 'zip'
    expected = stage_program(zip_root,source,source / 'server',source / 'portable-launcher.exe',None,'1.0.0',arch,ai=source / 'ai')
    (source / 'trailsnap-desktop.exe').write_bytes(b'shell__TAURI_BUNDLE_TYPE_VAR_NSS')
    assert finalize_install(source,'1.0.0') == expected
    assert (zip_root / 'app' / expected / 'trailsnap-desktop.exe').read_bytes().endswith(b'_UNK')
    assert (source / 'app' / expected / 'trailsnap-desktop.exe').read_bytes().endswith(b'_NSS')
    assert (source / 'portable.json').read_bytes() == (zip_root / 'portable.json').read_bytes()
    assert (source / 'instance.json').read_bytes() == b'keep user config'
    assert (source / 'userdata/keep').read_bytes() == b'photos'
    assert (source / 'app' / expected / 'server/trailsnap-server.exe').read_bytes() == b'server'
    (source / 'trailsnap_desktop_lib.dll').write_bytes(b'unused Cargo artifact')
    assert finalize_install(source,'1.0.0') == expected
    (source / 'trailsnap-desktop.exe').write_bytes(b'changed shell__TAURI_BUNDLE_TYPE_VAR_NSS')
    assert finalize_install(source,'1.0.0') != expected


@pytest.mark.skipif(os.name != 'nt', reason='Windows installer cleanup')
@pytest.mark.parametrize('data_path', ['userdata', 'app/custom-library'])
def test_uninstaller_preserves_library_and_local_config(tmp_path, data_path):
    import subprocess
    script = Path(__file__).resolve().parents[4] / 'package/desktop/src-tauri/windows/remove-instance-programs.ps1'
    (tmp_path / 'app/build').mkdir(parents=True)
    (tmp_path / 'app/build/program').write_bytes(b'program')
    data = tmp_path / data_path
    data.mkdir(parents=True, exist_ok=True)
    (data / 'photos').write_bytes(b'original media')
    config = json.dumps({'displayName': '行影集安装测试', 'dataRoot': {'kind': 'relative', 'path': data_path}},
                        ensure_ascii=False)
    (tmp_path / 'instance.json').write_text(config, encoding='utf-8')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                             '-File', str(script), '-InstallDirectory', str(tmp_path)], capture_output=True)
    assert (data / 'photos').read_bytes() == b'original media'
    assert (tmp_path / 'instance.json').read_text(encoding='utf-8') == config
    assert (result.returncode == 0) == (data_path == 'userdata')
    assert (tmp_path / 'app').exists() == (data_path != 'userdata')


def test_clone_of_moved_portable_library_carries_external_photos(tmp_path, monkeypatch):
    import subprocess
    import sys
    from app.utils.portable_conversion import preview_conversion
    from app.utils.desktop_verification import photo_paths
    source, program, external = tmp_path / 'legacy', tmp_path / 'program', tmp_path / 'external'
    (source / 'data').mkdir(parents=True)
    (program / 'server').mkdir(parents=True)
    external.mkdir()
    (external / 'outside.jpg').write_bytes(b'external photo')
    (external / 'outside.mov').write_bytes(b'live photo companion')
    owner, photo = str(uuid.uuid4()), str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    url = f"sqlite:///{(source / 'data/trailsnap.sqlite').as_posix()}"
    monkeypatch.setenv('TS_DB_URL', url)
    config = Config()
    config.set_main_option('script_location',str(Path(__file__).resolve().parents[2] / 'alembic_sqlite'))
    config.set_main_option('sqlalchemy.url',url)
    command.upgrade(config,'b0b9b9a3a2c0')
    with closing(sqlite3.connect(source / 'data/trailsnap.sqlite')) as db, db:
        db.execute('INSERT INTO users(id,username,email,hashed_password,settings) VALUES (?,?,?,?,?)',
                   (owner,'desktop-admin','desktop@trailsnap.app','hash',json.dumps({'storage':{'external_directories':[str(external)]}})))
        db.execute("INSERT INTO photos(id,owner_id,file_path,file_type,is_deleted) VALUES (?,?,?,'image',0)",
                   (photo,owner,str(external / 'outside.jpg')))
        # Pending work must follow the copy even if it predates task.owner_id.
        db.execute("INSERT INTO tasks(id,type,status,payload) VALUES (?,'PROCESS_BASIC','pending',?)",
                   (task_id,json.dumps({'user_id':owner,'file_path':str(external / 'outside.jpg'),
                                        'live_photo_video_path':str(external / 'outside.mov'),
                                        'target_root_path':str(external), 'scan_roots':[str(external)],
                                        'prompt':str(external / 'outside.jpg')})))
    for path in (program / 'trailsnap-desktop.exe',program / 'server/trailsnap-server.exe',program / 'launcher.exe'):
        path.write_bytes(b'fixture')
    def convert(original, target, copy_external=False):
        args = [sys.executable,'desktop_entry.py','--convert-portable',str(original),str(target),str(program),str(program / 'launcher.exe')]
        if copy_external: args.append('--copy-external')
        result = subprocess.run(args,cwd=Path(__file__).resolve().parents[2],capture_output=True,timeout=90)
        assert result.returncode == 0, result.stderr.decode(errors='replace')
    first = tmp_path / 'first'
    convert(source,first)
    assert json.loads((first / 'conversion.json').read_text())['externalReferencesRetained'] is True
    moved = tmp_path / 'moved'
    first.rename(moved)
    second = tmp_path / 'second'
    convert(moved / 'userdata',second,True)
    assert json.loads((second / 'conversion.json').read_text())['externalReferencesRetained'] is False
    external.rename(tmp_path / 'disconnected')
    with closing(sqlite3.connect(second / 'userdata/data/trailsnap.sqlite')) as db:
        paths = list(photo_paths(db,second / 'userdata'))
        assert len(paths) == 1
        copied = Path(paths[0][2])
        assert copied.is_relative_to(second / 'userdata')
        assert copied.read_bytes() == b'external photo'
        payload = transform_paths(json.loads(db.execute('SELECT payload FROM tasks WHERE id=?', (task_id,)).fetchone()[0]),
                                  encode=False, root=second / 'userdata')
        assert Path(payload['file_path']) == copied
        assert Path(payload['live_photo_video_path']).read_bytes() == b'live photo companion'
        assert Path(payload['target_root_path']) == copied.parent
        assert Path(payload['scan_roots'][0]) == copied.parent
        assert payload['prompt'] == str(external / 'outside.jpg')
    assert preview_conversion(second / 'userdata')['externalRoots'] == []


def test_relocated_library_keeps_rendered_films_and_posters_accessible(tmp_path, monkeypatch):
    from app.db.base import Base
    from app.db.models import User, DailyFrameWork
    from app.api.daily_frame import work_file, poster
    from app.service import daily_frame_render

    old = tmp_path / 'old'
    (old / 'data').mkdir(parents=True)
    owner, work_id = uuid.uuid4(), uuid.uuid4()
    movie = old / f'data/users/{owner}/daily-frame/film.mp4'
    movie.parent.mkdir(parents=True)
    movie.write_bytes(b'rendered film')
    movie.with_suffix('.jpg').write_bytes(b'film poster')
    engine = create_engine(f"sqlite:///{(old / 'data/trailsnap.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(User(id=owner, username='film', email='film@example.com', hashed_password='unused'))
        db.add(DailyFrameWork(id=work_id, owner_id=owner, fingerprint='film', status='ready',
                             output_path=str(movie), snapshot={'settings': {'title':'Film','start_date':'2024-05-07'}, 'frames':[{}]}))
        db.commit()
    engine.dispose()
    write_metadata = {'schemaVersion':1,'pathFormat':1,'libraryId':str(uuid.uuid4()),
                      'lastRoot':str(old),'initialized':True}
    (old / 'library.json').write_text(json.dumps(write_metadata))
    moved = tmp_path / 'moved'
    old.rename(moved)
    portable_env(monkeypatch, moved)
    prepare_portable_library(moved)
    # A second startup must be idempotent as well.
    prepare_portable_library(moved)
    monkeypatch.setattr(daily_frame_render, 'DATA_DIR', str(moved / 'data'))
    engine = create_engine(f"sqlite:///{(moved / 'data/trailsnap.sqlite').as_posix()}")
    with Session(engine) as db:
        user = db.get(User, owner)
        response = work_file(work_id, download=False, user=user, db=db)
        assert Path(response.path).read_bytes() == b'rendered film'
        assert Path(poster(work_id, user=user, db=db).path).read_bytes() == b'film poster'
    engine.dispose()
