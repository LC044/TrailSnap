"""First-launch upgrade journal. Source deletion is permitted only after a real launch.

Never move a whole legacy root: it can also contain the new installation or
unrelated files. Only remove unchanged files listed before the verified copy.
"""
from contextlib import closing, contextmanager
import json
import os
from pathlib import Path
import sqlite3
import uuid
import hashlib

from app.utils.portable_library import file_hash, write_json
from app.utils.desktop_import import discover_libraries
from app.utils.desktop_data_migration import migrate_data_directory, remove_staging_directory, _wait_for_sidecars
from app.utils.desktop_verification import media_baseline, photo_paths, verify_media
from app.utils.windows_paths import filesystem_path


def _read(path):
    return json.loads(path.read_text(encoding='utf-8'))


@contextmanager
def _legacy_lock(source):
    """Older shells lock this global pointer; the new per-library lock is different."""
    handles = []
    try:
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                          wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
            kernel.CreateFileW.restype = wintypes.HANDLE
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            locations = {source / '.instance.lock'}
            local = os.getenv('LOCALAPPDATA')
            if local:
                locations.add(Path(local) / 'TrailSnap-desktop.lock')
            paths = [(path, 0xC0000000, 0, 4) for path in locations]
            # Deny new writers even in older shells that predate the global
            # pointer lock. Allow reads and our final deletion while held.
            paths.append((source / 'data/trailsnap.sqlite', 0x80000000, 5, 3))
            for path, access, share, disposition in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                handle = kernel.CreateFileW(str(path), access, share, None, disposition, 0x80, None)
                if handle == wintypes.HANDLE(-1).value:
                    raise ValueError('旧版行影集仍在使用图库，请完全退出后重新启动新版。')
                handles.append((kernel, handle))
        _wait_for_sidecars(source)
        yield
    finally:
        for kernel, handle in reversed(handles):
            kernel.CloseHandle(handle)


def _inventory(source, progress=None):
    from app.utils.portable_conversion import conversion_exclusions
    excluded = conversion_exclusions(source) | {'.instance.lock', '.desktop-migration-ready',
                                               '.trailsnap-migration.json', 'webview-context.json'}
    records = []
    for current, dirs, names in os.walk(source, onerror=lambda error: (_ for _ in ()).throw(error)):
        current = Path(current)
        dirs[:] = [name for name in dirs if (current / name).relative_to(source).as_posix() not in excluded
                   and not (current == source and (name == 'webview' or name.startswith('webview-backup-')))]
        for name in dirs + names:
            if progress:
                progress(len(records), 0)
            path = current / name
            relative = path.relative_to(source).as_posix()
            if relative in excluded:
                continue
            if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
                raise ValueError('旧数据目录含链接，已停止自动迁移，请保留原目录。')
            if path.is_file():
                managed = Path(relative).parts[0] in {'data', 'logs', 'models', 'runtime', 'extensions', 'ai-extensions', 'ai-config.json'}
                if progress:
                    digest = hashlib.sha256()
                    with open(filesystem_path(path), 'rb') as stream:
                        while chunk := stream.read(1024 * 1024):
                            progress(len(records), 0)
                            digest.update(chunk)
                    sha256 = digest.hexdigest()
                else:
                    sha256 = file_hash(path)
                records.append({'path': relative, 'sha256': sha256, 'cleanup': managed})
    return sorted(records, key=lambda row: row['path'])


def _prepare(data):
    from desktop_entry import _prepare_desktop_database
    os.environ.update(TS_DESKTOP='1', TS_DESKTOP_PORTABLE='1', TS_DESKTOP_ROOT=str(data), TS_DATA_DIR=str(data / 'data'))
    # Keep mobile sessions valid for an upgrade of the same library.
    config_path = data / 'data/system_config.json'
    security = (_read(config_path).get('security') or {}) if config_path.is_file() else None
    try:
        _prepare_desktop_database()
    finally:
        import sys
        for name in ('app.db.session', 'railway.db.session'):
            module = sys.modules.get(name)
            if module is not None:
                module.engine.dispose()
    if security is not None:
        config = _read(config_path)
        config['security'] = security
        write_json(config_path, config)


def _check_journal(root, job):
    if job.get('schemaVersion') != 1 or str(uuid.UUID(job['id'])) != job['id']:
        raise ValueError('自动迁移记录无效，请保留目录并检查日志。')
    source = Path(job['source']).resolve(strict=True)
    if os.path.normcase(str(source)) != os.path.normcase(job['source']) or source == Path(source.anchor):
        raise ValueError('旧数据根目录已改变或指向磁盘根目录，已停止迁移和清理。')
    if source == root / 'userdata' or source.is_relative_to(root / 'userdata'):
        raise ValueError('旧数据位置不能指向新图库。')
    stage = root.parent / ('.trailsnap-auto-' + job['id'])
    return source, stage


def prepare(root):
    root = root.resolve(strict=True)
    from app.utils.upgrade_progress import UpgradeProgress
    progress = UpgradeProgress(root)
    progress.report('checking')
    journal = root / 'maintenance/automatic-upgrade.json'
    if journal.is_file():
        job = _read(journal)
        _check_journal(root, job)
        if job['phase'] in {'published', 'validated', 'committed', 'completed'}:
            config = _read(root / 'instance.json')
            if config['instanceId'] != job['instance']['instanceId'] or config['dataRoot'] != {'kind': 'relative', 'path': 'userdata'}:
                raise ValueError('自动迁移的图库身份或位置已改变，已停止处理。')
            return job
    else:
        if (root / 'instance.json').exists():
            return {'phase': 'none'}
        local = os.getenv('LOCALAPPDATA')
        discovery = discover_libraries(root, root / 'userdata', Path(local) if local else None)
        candidates = discovery['candidates']
        selection = root / 'maintenance/automatic-upgrade-source.json'
        if selection.is_file():
            from app.utils.portable_conversion import validate_library_source
            source = validate_library_source(Path(_read(selection)['source']))
            candidates = [{'path': str(source), 'error': None}]
            discovery['notices'] = []
        if discovery['notices'] or len(candidates) > 1:
            paths = '；'.join(item['path'] for item in candidates)
            raise ValueError('检测到多个或不可用的旧图库，已停止自动迁移，请先在旧版确认数据位置并保留原目录。' + paths + '；'.join(discovery['notices']))
        if not candidates:
            return {'phase': 'none'}
        if candidates[0]['error']:
            raise ValueError(candidates[0]['error'])
        source = Path(candidates[0]['path']).resolve(strict=True)
        if source == Path(source.anchor):
            raise ValueError('不能自动迁移磁盘根目录，请先将图库放入独立文件夹。')
        if (source / 'library.json').exists():
            raise ValueError('检测到已有便携图库，请从原目录启动；不会自动复制或清理另一个实例。')
        if (root / 'userdata').exists() and any((root / 'userdata').iterdir()):
            raise ValueError('新版 userdata 已有数据，请确认图库来源后处理；不会覆盖或新建空库。')
        descriptor = _read(root / 'portable.json')
        build = descriptor['activeBuild']
        if Path(build).name != build or ':' in build or build in {'.', '..'}:
            raise ValueError('程序版本无效')
        instance = {'schemaVersion': 1, 'mode': 'portable', 'instanceId': str(uuid.uuid4()),
                    'displayName': root.name, 'activeBuild': build, 'previousBuild': None,
                    'dataRoot': {'kind': 'relative', 'path': 'userdata'}, 'serverPort': None, 'fixedPort': False}
        if local:
            pointer = Path(local) / 'TrailSnap-desktop.json'
            if pointer.is_file():
                old = _read(pointer)
                if Path(old['root']).resolve() == source:
                    instance['serverPort'] = old.get('server_port')
        job = {'schemaVersion': 1, 'id': str(uuid.uuid4()), 'source': str(source),
               'phase': 'copying', 'instance': instance}
        write_json(journal, job)
    source, stage = _check_journal(root, job)
    staged_data = stage / 'userdata'
    data = root / 'userdata'
    with _legacy_lock(source):
        if job['phase'] == 'prepared':
            progress.report('publishing', cancellable=False)
            # Publishing userdata and instance.json is recovered after either rename.
            if not data.exists():
                os.replace(filesystem_path(staged_data), filesystem_path(data))
            if _read(data / 'automatic-upgrade-owner.json') != {'operationId': job['id']}:
                raise ValueError('新图库不属于本次迁移，已停止以避免覆盖。')
        else:
            if data.exists() and any(data.iterdir()):
                raise ValueError('userdata 已有数据，自动迁移不会覆盖。')
            if stage.exists():
                # The stage is a deterministic sibling owned by this persisted job.
                if stage.is_symlink() or (hasattr(stage, 'is_junction') and stage.is_junction()):
                    raise ValueError('迁移临时目录含链接')
                marker = stage / 'automatic-upgrade-owner.json'
                if marker.is_file() and _read(marker) == {'operationId': job['id']}:
                    remove_staging_directory(stage)
                else:
                    raise ValueError('迁移临时目录需检查，未删除任何文件。')
            job['files'] = _inventory(source, lambda done, total: progress.report('inventory', done, total))
            from app.utils.portable_conversion import conversion_exclusions
            job['media'] = media_baseline(source, limit=None, full=True,
                                         excluded_entries=conversion_exclusions(source),
                                         progress=lambda done, total: progress.report('baseline', done, total, unit='photos'))
            write_json(stage / 'automatic-upgrade-owner.json', {'operationId': job['id']})
            migrate_data_directory(source, staged_data, skip_browser_state=True,
                                   excluded_entries=conversion_exclusions(source) | {'automatic-upgrade-owner.json'},
                                   checkpoint=progress.checkpoint,
                                   byte_progress=lambda done, total: progress.report('copying', done, total, unit='bytes'))
            write_json(staged_data / 'automatic-upgrade-owner.json', {'operationId': job['id']})
            # Compare all source files again, so a legacy writer cannot silently
            # change the source while the migration helper copies it.
            if _inventory(source, lambda done, total: progress.report('checking_source', done, total)) != job['files']:
                raise ValueError('旧图库在复制过程中发生变化，已停止切换，原数据保留。')
            progress.report('database', cancellable=False)
            _prepare(staged_data)
            verify_media(staged_data, job['media'], progress=lambda done, total: progress.report('verifying', done, total, unit='photos'))
            progress.report('publishing', cancellable=False)
            job['phase'] = 'prepared'
            write_json(journal, job)
            if data.exists():
                data.rmdir()
            os.replace(filesystem_path(staged_data), filesystem_path(data))
        os.environ['TS_DESKTOP_ROOT'] = str(data)
        from app.utils.portable_library import prepare_portable_library
        prepare_portable_library(data)
        verify_media(data, job['media'], progress=lambda done, total: progress.report('verifying', done, total, unit='photos', cancellable=False))
        write_json(root / 'instance.json', job['instance'])
        # Suppress the manual legacy prompt; this library was upgraded in place.
        write_json(root / 'conversion.json', {'source': str(source), 'verified': True,
                                            'automatic': True, 'media': job['media']})
        job['phase'] = 'published'
        write_json(journal, job)
        progress.report('launching', cancellable=False)
    return job


def finish(root, action):
    root = root.resolve(strict=True)
    journal = root / 'maintenance/automatic-upgrade.json'
    job = _read(journal)
    source, _ = _check_journal(root, job)
    config = _read(root / 'instance.json')
    if config['instanceId'] != job['instance']['instanceId'] or config['dataRoot'] != {'kind': 'relative', 'path': 'userdata'}:
        raise ValueError('自动迁移目标已改变，未清理旧数据。')
    if action == 'validated':
        if job['phase'] == 'published':
            job['phase'] = 'validated'
            write_json(journal, job)
        return job
    if action != 'cleanup' or job['phase'] not in {'validated', 'committed', 'completed'}:
        raise ValueError('未通过启动验证，禁止清理旧数据。')
    if job['phase'] == 'completed':
        return job
    data = root / 'userdata'
    with _legacy_lock(source):
        media = job['media']
        # Legacy proofs have no copied flag. Consult the unchanged SOURCE
        # database before cleanup so a copied record redirected outside userdata
        # cannot be mistaken for an untouched external original and skipped.
        if any('copied' not in item for item in media) and (source / 'data/trailsnap.sqlite').is_file():
            with closing(sqlite3.connect((source / 'data/trailsnap.sqlite').as_uri() + '?mode=ro', uri=True)) as db:
                copied_ids = {photo for photo, _, path in photo_paths(db, source)
                              if Path(path).resolve().is_relative_to(source)}
            media = [dict(item, copied=True) if item['id'] in copied_ids else item for item in media]
        verify_media(data, media)
        # Validate the complete deletion set before the first unlink. Unknown or
        # changed files stay in place; never recursively delete a legacy root.
        targets = []
        for record in job['files']:
            if not record.get('cleanup', False):
                continue  # Copied ancillary files may belong to another application.
            relative = Path(record['path'])
            path = source / relative
            if relative.is_absolute() or '..' in relative.parts or not path.resolve().is_relative_to(source):
                raise ValueError('旧数据清理路径无效')
            if path.is_symlink() or any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()) for p in [path, *path.parents] if p.is_relative_to(source)):
                raise ValueError('旧数据清理路径含链接')
            if path.exists():
                if file_hash(path) != record['sha256']:
                    raise ValueError('旧数据已变化，已保留旧库，未自动清理。')
                targets.append(path)
            elif job['phase'] != 'committed':
                raise ValueError('旧数据已变化，已停止清理。')
        job['phase'] = 'committed'
        write_json(journal, job)
        for path in targets:
            path.unlink()
        directories = {p for path in targets for p in path.parents if p != source and p.is_relative_to(source)}
        for directory in sorted(directories, key=lambda p: len(p.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass  # Unknown files and directories remain untouched.
        job['phase'] = 'completed'
        write_json(journal, job)
        stage = root.parent / ('.trailsnap-auto-' + job['id'])
        owner = stage / 'automatic-upgrade-owner.json'
        if owner.is_file() and _read(owner) == {'operationId': job['id']}:
            owner.unlink()
            try:
                stage.rmdir()
            except OSError:
                pass
    return job


def automatic_upgrade(root, action):
    return prepare(Path(root)) if action == 'prepare' else finish(Path(root), action)
