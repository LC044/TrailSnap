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
from app.utils.portable_library import file_hash, write_json
from app.utils.windows_paths import filesystem_path, publish_directory
from app.utils.portable_config import transform_paths, remap_path_fields
from app.utils.desktop_verification import photo_paths, media_baseline, verify_media


def preview_conversion(source: Path) -> dict:
    source = source.resolve(strict=True)
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
    size = sum(path.stat().st_size for path in source.rglob("*") if path.is_file() and not path.is_symlink())
    return {"source": str(source), "bytes": size, "counts": counts, "externalRoots": external, "unregisteredPhotos":unregistered}


def convert_to_portable(source: Path, target: Path, program: Path, launcher: Path, *, copy_external: bool = False) -> dict:
    source, target, program, launcher = source.resolve(strict=True), target.resolve(), program.resolve(strict=True), launcher.resolve(strict=True)
    if target == source or target.is_relative_to(source) or source.is_relative_to(target):
        raise ValueError("新旧目录不能相同或互相包含")
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ValueError("便携实例目标必须是空文件夹")
    if not launcher.is_file() or not (program / "trailsnap-desktop.exe").is_file() or not (program / "server/trailsnap-server.exe").is_file():
        raise ValueError("转换需要完整的新桌面程序、后端与启动器")
    preview = preview_conversion(source)
    baseline = media_baseline(source)
    if copy_external and any(not item["available"] for item in preview["externalRoots"]):
        raise ValueError("外部图库磁盘不可用，不能创建完整便携副本")
    if copy_external and preview["unregisteredPhotos"]:
        raise ValueError("存在未登记存储根的照片，请先补充外部图库目录后再创建完整便携副本")
    target.parent.mkdir(parents=True, exist_ok=True)
    required = preview["bytes"] + sum(path.stat().st_size for path in program.rglob("*") if path.is_file())
    required += (source / "data/trailsnap.sqlite").stat().st_size + 128 * 1024 * 1024
    if copy_external:
        required += sum(path.stat().st_size for item in preview["externalRoots"] for path in Path(item["path"]).rglob("*") if path.is_file())
    if shutil.disk_usage(target.parent).free < required:
        raise ValueError("目标磁盘空间不足，需要图库、程序、数据库快照与额外余量")
    stage = Path(tempfile.mkdtemp(prefix=".trailsnap-portable-", dir=target.parent))
    try:
        from app.utils.desktop_data_migration import migrate_data_directory, rebase_value
        data = stage / "userdata"
        migrate_data_directory(source, data, skip_browser_state=True)
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
                    new = data / "data/imported" / item["ownerId"] / uuid.uuid5(uuid.NAMESPACE_URL, str(old)).hex
                    # Copy companions and directory configuration too; never move.
                    if any(path.is_symlink() or (hasattr(path,"is_junction") and path.is_junction()) for path in old.rglob("*")):
                        raise ValueError("外部图库含链接，请先处理后再转换")
                    shutil.copytree(filesystem_path(old), filesystem_path(new))
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
                    # Copied custom user roots become an explicit scan root, while
                    # future uploads use the portable default user layout.
                    if str(new) not in storage.setdefault("external_directories",[]): storage["external_directories"].append(str(new))
                    base = storage.get("photo_storage_path")
                    if base and not Path(base).resolve().is_relative_to(data): storage["photo_storage_path"] = str(data / "data")
                    db.execute("UPDATE users SET settings=? WHERE id=?", (json.dumps(settings,ensure_ascii=False),owner))
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
        write_json(stage / "conversion.json", {"source":str(source),"counts":preview["counts"],"externalCopied":copy_external,"verified":True})
        verify_media(data, baseline)
        if target.exists(): target.rmdir()
        publish_directory(stage, target)
        return {"target":str(target),"counts":preview["counts"],"externalCopied":copy_external}
    finally:
        if stage.exists(): shutil.rmtree(filesystem_path(stage))
