"""Build a complete portable instance from a stopped legacy library."""
from __future__ import annotations
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import uuid
import sys
import time


_last_progress = 0.0
def report_progress(stage, completed=0, total=0):
    global _last_progress
    if not os.getenv("TS_IMPORT_OPERATION"):
        return
    now = time.monotonic()
    if completed and completed != total and now - _last_progress < .2:
        return
    _last_progress = now
    print(json.dumps({"importProgress": True, "stage": stage, "completed": completed, "total": total}, ensure_ascii=False), file=sys.stderr, flush=True)
from app.utils.portable_library import file_hash, write_json
from app.utils.windows_paths import filesystem_path, publish_directory
from app.utils.portable_config import transform_paths, remap_path_fields
from app.utils.desktop_verification import photo_paths, media_baseline, verify_media


def validate_library_source(source: Path) -> Path:
    """Validate the explicitly selected library root without choosing another library."""
    # Folder pickers may return a Win32 extended path; its file:// URI has an
    # invalid authority for SQLite. Keep ordinary drive/UNC semantics here.
    raw = str(source)
    if os.name == 'nt':
        if raw.startswith('\\\\?\\UNC\\'):
            raw = '\\\\' + raw[8:]
        elif raw.startswith('\\\\?\\'):
            raw = raw[4:]
    source = Path(raw)
    if not source.is_absolute():
        raise ValueError('请输入旧数据目录的完整路径，或使用“选择旧数据目录”。')
    try:
        source = source.resolve(strict=True)
    except OSError as error:
        raise ValueError(f'旧数据目录不存在或无法访问：{source}。请检查路径和磁盘连接。') from error
    if not source.is_dir():
        raise ValueError(f'请选择文件夹，不要选择数据库文件：{source}。应选择包含 data 文件夹的旧数据目录。')
    database = source / 'data/trailsnap.sqlite'
    if not database.is_file():
        if (source / 'trailsnap.sqlite').is_file() and source.name.lower() == 'data':
            raise ValueError(f'选中了 data 子文件夹，请改选它的上一级目录：{source.parent}。系统会自动读取 data/trailsnap.sqlite。')
        if (source / 'userdata/data/trailsnap.sqlite').is_file():
            raise ValueError(f'这里是新版本的实例目录。要复制其中的图库，请选择：{source / "userdata"}；要导入旧版本，请选择包含 data 文件夹的旧数据目录。')
        raise ValueError(f'所选目录中未找到旧图库数据库：{database}。请选择包含 data 文件夹的旧数据目录，不要选择 data 子文件夹。')
    return source


def conversion_exclusions(source: Path) -> frozenset[str]:
    """An overwritten legacy installation can also contain the NEW live library."""
    excluded = {'server', 'trailsnap-desktop.exe', 'uninstall.exe'}
    descriptor = source / 'instance.json'
    if descriptor.is_file():
        config = json.loads(descriptor.read_text(encoding='utf-8'))
        data_root = config.get('dataRoot') or {}
        if data_root.get('kind') == 'relative':
            from app.service.storage_paths import validate_relative
            nested = source / validate_relative(data_root.get('path'))
        elif data_root.get('kind') == 'absolute':
            nested = Path(data_root.get('path', ''))
        else:
            raise ValueError('所选目录中的 instance.json 数据位置无效，请保留原目录并检查该配置。')
        nested = nested.resolve()
        database = source / 'data/trailsnap.sqlite'
        if nested != source and nested.is_relative_to(source) and not database.is_relative_to(nested):
            excluded.add(nested.relative_to(source).as_posix())
        excluded.update({'app', 'maintenance', 'TrailSnap.exe', 'portable-launcher.exe', 'instance.json', 'portable.json'})
    return frozenset(excluded)


def preview_conversion(source: Path) -> dict:
    source = validate_library_source(source)
    try:
        return _preview_conversion(source)
    except sqlite3.Error as error:
        raise ValueError(f'无法读取旧图库数据库：{source / "data/trailsnap.sqlite"}。请确认磁盘在线、具有读取权限，并完全退出旧版本后重试。数据库格式不正确或损坏时，请保留原目录并从备份恢复。') from error


def _preview_conversion(source: Path) -> dict:
    with closing(sqlite3.connect((source / "data/trailsnap.sqlite").as_uri() + "?mode=ro", uri=True)) as db:
        users = db.execute("SELECT id,settings FROM users").fetchall()
        registered = {}
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='storage_roots'").fetchone():
            for owner, location in db.execute("SELECT owner_id,location FROM storage_roots WHERE kind='external'"):
                registered.setdefault(owner, []).append(location)
        external = []
        for owner, raw in users:
            settings = transform_paths(json.loads(raw or "{}"), encode=False, root=source)
            storage = settings.get("storage") or {}
            roots = list(storage.get("external_directories", []))
            roots.extend(registered.get(owner, []))
            base = storage.get("photo_storage_path")
            if base and Path(base).is_absolute() and not Path(base).resolve().is_relative_to(source):
                roots.append(str(Path(base) / "users" / owner))
            for path in sorted(set(roots)):
                root = Path(path).resolve()
                if root.is_relative_to(source):
                    continue
                external.append({"ownerId": owner, "path": str(root), "available": root.is_dir()})
        counts = {name: db.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0] for name in ("users", "photos", "albums", "tasks")}
        from app.utils.portable_library import _matches
        unregistered = 0
        for _, owner, path in photo_paths(db, source):
            if _matches(path,source) is None and not any(item["ownerId"]==owner and (_matches(path,Path(item["path"])) is not None) for item in external):
                unregistered += 1
    excluded = conversion_exclusions(source)
    size = 0
    def walk_error(error):
        raise error
    for current, dirs, names in os.walk(source, onerror=walk_error):
        current = Path(current)
        dirs[:] = [name for name in dirs if (current / name).relative_to(source).as_posix() not in excluded
                   and not (current == source and (name == 'webview' or name.startswith('webview-backup-')))]
        for name in names:
            path = current / name
            if path.relative_to(source).as_posix() not in excluded and path.is_file() and not path.is_symlink():
                size += path.stat().st_size
    return {"source": str(source), "bytes": size, "counts": counts, "externalRoots": external, "unregisteredPhotos":unregistered}


def validate_external_target(preview: dict, target: Path) -> None:
    """Keep the new instance outside every scanned/copied original folder."""
    target = target.resolve()
    for item in preview['externalRoots']:
        external = Path(item['path']).resolve()
        if target == external or target.is_relative_to(external) or external.is_relative_to(target):
            raise ValueError(f'新位置不能与外部照片文件夹相同或互相包含：{external}。请在磁盘上选择另外的空文件夹，例如它的同级文件夹。')


def convert_to_portable(source: Path, target: Path, program: Path, launcher: Path, *, copy_external: bool = False) -> dict:
    source, target, program, launcher = validate_library_source(source), target.resolve(), program.resolve(strict=True), launcher.resolve(strict=True)
    if target == source or target.is_relative_to(source) or source.is_relative_to(target):
        raise ValueError("新旧目录不能相同或互相包含")
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ValueError("便携实例目标必须是空文件夹")
    if not launcher.is_file() or not (program / "trailsnap-desktop.exe").is_file() or not (program / "server/trailsnap-server.exe").is_file():
        raise ValueError("转换需要完整的新桌面程序、后端与启动器")
    preview = preview_conversion(source)
    validate_external_target(preview, target)
    baseline = media_baseline(source)
    if copy_external and any(not item["available"] for item in preview["externalRoots"]):
        raise ValueError("外部图库磁盘不可用，不能创建完整便携副本")
    if copy_external and preview["unregisteredPhotos"]:
        raise ValueError("存在未登记存储根的照片，请先补充外部图库目录后再创建完整便携副本")
    report_progress("checking")
    target.parent.mkdir(parents=True, exist_ok=True)
    from app.utils.desktop_import import conversion_space, cleanup_staging
    space = conversion_space(source, target, program, copy_external)
    if not space['enough']:
        raise ValueError("目标磁盘空间不足，需要图库、程序、数据库快照与额外余量")
    operation = os.getenv('TS_IMPORT_OPERATION')
    if operation:
        cleanup_staging(target, operation)
        stage = target.parent / ('.trailsnap-portable-' + operation)
        stage.mkdir()
        write_json(stage / 'import-operation.json', {'operationId': operation, 'target': str(target)})
    else:
        stage = Path(tempfile.mkdtemp(prefix=".trailsnap-portable-", dir=target.parent))
    try:
        from app.utils.desktop_data_migration import migrate_data_directory, rebase_value
        data = stage / "userdata"
        migrate_data_directory(source, data, skip_browser_state=True, excluded_entries=conversion_exclusions(source), progress=lambda done, total: report_progress("copying", done, total))
        # Resolve the authoritative references against the SOURCE before cloning.
        # Rebuild references in the target even for an already-portable library.
        with closing(sqlite3.connect((source / 'data/trailsnap.sqlite').as_uri() + '?mode=ro', uri=True)) as original:
            with closing(sqlite3.connect(data / 'data/trailsnap.sqlite')) as db, db:
                has_refs = 'storage_root_id' in {row[1] for row in db.execute('PRAGMA table_info(photos)')}
                for photo, _, path in photo_paths(original, source):
                    db.execute('UPDATE photos SET file_path=? WHERE id=?', (rebase_value(path, source, data), photo))
                if has_refs:
                    db.execute('UPDATE photos SET storage_root_id=NULL, storage_relative_path=NULL')
                    db.execute('DELETE FROM storage_roots')
                for owner, raw in db.execute('SELECT id,settings FROM users').fetchall():
                    settings = transform_paths(json.loads(raw or '{}'), encode=False, root=data)
                    # Explicit organize roots may exist only in storage_roots.
                    # Preserve them when rebuilding references in the copy.
                    external = settings.setdefault('storage', {}).setdefault('external_directories', [])
                    for item in preview['externalRoots']:
                        if item['ownerId'] == owner and item['path'] not in external:
                            external.append(item['path'])
                    db.execute('UPDATE users SET settings=? WHERE id=?', (json.dumps(settings,ensure_ascii=False),owner))
        # A deliberate copy is a new independent library. Moving an existing
        # folder keeps its IDs; this explicit operation rotates identity/session.
        library = data / "library.json"
        if library.exists():
            metadata = json.loads(library.read_text(encoding="utf-8"))
            metadata["libraryId"] = str(uuid.uuid4())
            metadata["initialized"] = False
            write_json(library,metadata)
        config = data / "data/system_config.json"
        if config.exists():
            import secrets
            settings = json.loads(config.read_text(encoding="utf-8"))
            settings.setdefault("security",{})["secret_key"] = secrets.token_hex(32)
            write_json(config,settings)
        # Source installations may historically live alongside their data. Remove
        # only copied, known program files; the original installation is untouched.
        for name in ("server", "trailsnap-desktop.exe", "uninstall.exe"):
            copied = data / name
            if copied.is_dir(): shutil.rmtree(filesystem_path(copied))
            elif copied.is_file(): copied.unlink()
        if copy_external:
            with closing(sqlite3.connect(data / "data/trailsnap.sqlite")) as db, db:
                mappings = {}
                for item in preview["externalRoots"]:
                    old = Path(item["path"])
                    owner = item['ownerId']
                    raw_settings = db.execute('SELECT settings FROM users WHERE id=?', (owner,)).fetchone()[0]
                    original_base = (transform_paths(json.loads(raw_settings or '{}'), encode=False, root=data).get('storage') or {}).get('photo_storage_path')
                    custom_storage = bool(original_base and old == (Path(original_base) / 'users' / owner).resolve())
                    identity = uuid.uuid5(uuid.NAMESPACE_URL, owner + ':' + str(old)).hex
                    copied_base = data / 's' / identity[:16] if custom_storage else data / 'data/imported' / owner / identity
                    new = copied_base / 'users' / owner if custom_storage else copied_base
                    if new.exists():
                        raise ValueError('外部照片复制目标已存在，已停止以避免覆盖副本内容')
                    report_progress('external')
                    # Copy companions and directory configuration too; never move.
                    if any(path.is_symlink() or (hasattr(path,"is_junction") and path.is_junction()) for path in old.rglob("*")):
                        raise ValueError("外部图库含链接，请先处理后再转换")
                    copied_files = [p for p in old.rglob('*') if p.is_file()]
                    for index, path in enumerate(copied_files, 1):
                        destination_file = new / path.relative_to(old)
                        Path(filesystem_path(destination_file.parent)).mkdir(parents=True, exist_ok=True)
                        shutil.copy2(filesystem_path(path), filesystem_path(destination_file))
                        report_progress('external', index, len(copied_files))
                    for path in old.rglob("*"):
                        if path.is_file() and file_hash(path) != file_hash(new / path.relative_to(old)):
                            raise ValueError("外部照片复制校验失败")
                    owner = item["ownerId"]
                    mappings.setdefault(owner, []).append((old, new))
                    rows = db.execute("SELECT id,file_path FROM photos WHERE owner_id=?", (owner,)).fetchall()
                    db.executemany("UPDATE photos SET file_path=? WHERE id=?", [(rebase_value(path,old,new),photo_id) for photo_id,path in rows])
                    raw = db.execute("SELECT settings FROM users WHERE id=?", (owner,)).fetchone()[0]
                    settings = rebase_value(json.loads(raw or "{}"), old, new)
                    storage = settings.setdefault("storage", {})
                    # Preserve a custom storage base as a complete user layout;
                    # other selected folders remain explicit external scan roots.
                    if custom_storage:
                        # Keep uploads, thumbnails, chunks and configuration under
                        # the same per-user base used by every media endpoint.
                        storage['photo_storage_path'] = str(copied_base)
                    elif str(new) not in storage.setdefault('external_directories', []):
                        storage['external_directories'].append(str(new))
                    db.execute("UPDATE users SET settings=? WHERE id=?", (json.dumps(settings,ensure_ascii=False),owner))
                    config_mappings = [(old, new)]
                    if custom_storage:
                        config_mappings.append((Path(original_base), copied_base))
                    for config_file in new.glob('config/*.json'):
                        value = json.loads(config_file.read_text(encoding='utf-8'))
                        write_json(config_file, remap_path_fields(value, config_mappings))
                for task_id, owner, raw in db.execute("SELECT id,owner_id,payload FROM tasks WHERE payload IS NOT NULL").fetchall():
                    payload = transform_paths(json.loads(raw), encode=False, root=data)
                    task_owner = owner or (payload.get("user_id") if isinstance(payload, dict) else None)
                    if task_owner:
                        rewritten = remap_path_fields(payload, mappings.get(str(task_owner), []))
                    else:
                        # Older global tasks may lack an owner. Only remap them
                        # when all matching owners agree on the destination.
                        variants = [remap_path_fields(payload, paths) for paths in mappings.values()]
                        changed = [value for value in variants if value != payload]
                        if changed and any(value != changed[0] for value in changed):
                            raise ValueError("待执行任务引用共享外部图库但缺少用户身份，请在原客户端取消该任务后重试")
                        rewritten = changed[0] if changed else payload
                    db.execute("UPDATE tasks SET payload=? WHERE id=?", (json.dumps(rewritten, ensure_ascii=False), task_id))
        report_progress("database")
        os.environ.update(TS_DESKTOP="1", TS_DESKTOP_PORTABLE="1", TS_DESKTOP_ROOT=str(data), TS_DATA_DIR=str(data / "data"))
        from desktop_entry import _prepare_desktop_database
        try:
            _prepare_desktop_database()
        finally:
            # Session.close returns connections to the pool. Windows cannot
            # rename or remove the staging directory until the pool closes them.
            import sys
            for module_name in ("app.db.session", "railway.db.session"):
                module = sys.modules.get(module_name)
                if module is not None:
                    module.engine.dispose()
        manifest_path = program / "manifest.json"
        if manifest_path.is_file(): manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        else:
            from app.core.config_manager import VERSION
            manifest = {"schemaVersion":1,"version":VERSION,"buildId":VERSION+"-"+file_hash(program/"trailsnap-desktop.exe")[:12],
                        "platform":"windows-"+("aarch64" if __import__('platform').machine().lower() in {"arm64","aarch64"} else "x86_64"),"minLauncherVersion":1,"executable":"trailsnap-desktop.exe"}
        build = manifest["buildId"]
        if Path(build).name != build or ":" in build or build in {".",".."}: raise ValueError("程序版本标识无效")
        report_progress("program")
        destination = stage / "app" / build
        destination.mkdir(parents=True)
        # Installation and data historically can share a directory. Copy only
        # program resources rather than nesting another copy of the photo library.
        for entry in program.iterdir():
            if entry.name in {"server", "resources", "webview-runtime"} and entry.is_dir():
                shutil.copytree(filesystem_path(entry), filesystem_path(destination / entry.name))
            elif entry.is_file() and (entry.name in {"trailsnap-desktop.exe", "portable-launcher.exe", "ai-extensions.json"} or entry.suffix.lower() == ".dll"):
                shutil.copy2(filesystem_path(entry), filesystem_path(destination / entry.name))
        write_json(destination / "manifest.json", manifest)
        shutil.copy2(filesystem_path(launcher), filesystem_path(destination / "portable-launcher.exe"))
        shutil.copy2(filesystem_path(launcher), filesystem_path(stage / "TrailSnap.exe"))
        instance = {"schemaVersion":1,"mode":"portable","instanceId":str(uuid.uuid4()),"displayName":target.name,
                    "activeBuild":build,"previousBuild":None,"dataRoot":{"kind":"relative","path":"userdata"},"serverPort":None,"fixedPort":False}
        write_json(stage / "instance.json", instance)
        write_json(stage / "portable.json", {"schemaVersion":1,"activeBuild":build})
        with closing(sqlite3.connect(data / "data/trailsnap.sqlite")) as db:
            for table,count in preview["counts"].items():
                if db.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] != count:
                    raise ValueError(f"转换后 {table} 记录数量不一致")
        from app.utils.desktop_import import photo_count
        previous_data = os.getenv('TS_IMPORT_PREVIOUS_DATA')
        previous_entry = os.getenv('TS_IMPORT_ORIGIN') if previous_data and photo_count(Path(previous_data)) else None
        write_json(stage / "conversion.json", {"source":str(source),"counts":preview["counts"],"externalCopied":copy_external,"verified":True,"operationId":operation,
                                               "previousEntry":previous_entry,"previousInstanceId":os.getenv('TS_IMPORT_ORIGIN_ID')})
        report_progress("verifying")
        verify_media(data, baseline)
        if target.exists(): target.rmdir()
        publish_directory(stage, target)
        return {"target":str(target),"counts":preview["counts"],"externalCopied":copy_external}
    finally:
        if stage.exists(): shutil.rmtree(filesystem_path(stage))
