"""Read-only legacy discovery and space checks; never select the active library."""
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3


def photo_count(root: Path) -> int:
    database = root / 'data/trailsnap.sqlite'
    if not database.is_file():
        return 0
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
        return db.execute('SELECT count(*) FROM photos').fetchone()[0]


def discover_libraries(installation: Path, current: Path, local_data: Path | None = None) -> dict:
    installation, current = installation.resolve(), current.resolve()
    roots = [installation]
    notices = []
    if local_data is not None:
        roots.extend([local_data / 'TrailSnap', local_data / 'com.trailsnap.desktop'])
        for pointer in (local_data / 'TrailSnap-desktop.json', installation / 'TrailSnap-desktop.json'):
            if not pointer.is_file():
                continue
            try:
                raw = json.loads(pointer.read_text(encoding='utf-8-sig'))['root']
                root = Path(raw)
                root = (root if root.is_absolute() else pointer.parent / root).resolve()
                roots.insert(0, root)
                if not root.is_dir():
                    notices.append(f'旧版本记录的数据位置不可用，请连接原磁盘：{root}')
            except (OSError, ValueError, KeyError, TypeError):
                notices.append(f'旧数据位置配置无法读取，请保留该文件并手动选择旧目录：{pointer}')
    candidates, seen = [], {os.path.normcase(str(current))}
    for root in roots:
        root = root.resolve()
        key = os.path.normcase(str(root))
        if key in seen or not (root / 'data/trailsnap.sqlite').is_file():
            continue
        seen.add(key)
        try:
            candidates.append({'path': str(root), 'photos': photo_count(root), 'error': None})
        except sqlite3.Error:
            candidates.append({'path': str(root), 'photos': None, 'error': '数据库暂时无法读取，请退出旧版后重试；请保留原目录。'})
    return {'candidates': candidates, 'notices': notices, 'currentPhotos': photo_count(current),
            'completed': (installation / 'conversion.json').is_file()}


def conversion_space(source: Path, target: Path, program: Path, copy_external: bool) -> dict:
    from app.utils.portable_conversion import preview_conversion
    preview = preview_conversion(source)
    required = preview['bytes'] + sum(p.stat().st_size for p in program.rglob('*') if p.is_file())
    # Migration and candidate validation each retain a database snapshot.
    required += 3 * sum(p.stat().st_size for p in (source / 'data').glob('*.sqlite')) + 128 * 1024 * 1024
    external_bytes = 0
    if copy_external:
        for item in preview['externalRoots']:
            if not item['available']:
                raise ValueError('外部照片磁盘未连接，请连接后重新检查。')
            for current, dirs, files in os.walk(item['path'], onerror=lambda error: (_ for _ in ()).throw(error)):
                external_bytes += sum((Path(current) / name).stat().st_size for name in files)
    ancestor = target.resolve()
    while not ancestor.exists():
        ancestor = ancestor.parent
    free = shutil.disk_usage(ancestor).free
    return {'requiredBytes': required + external_bytes, 'freeBytes': free, 'externalBytes': external_bytes,
            'enough': free >= required + external_bytes}


def cleanup_staging(target: Path, operation_id: str) -> None:
    """Only delete this operation's unpublished sibling, never a target/library."""
    import uuid
    if str(uuid.UUID(operation_id)) != operation_id:
        raise ValueError('复制操作标识无效')
    target = target.resolve()
    stage = target.parent / ('.trailsnap-portable-' + operation_id)
    if not stage.exists():
        return
    if stage.is_symlink() or (hasattr(stage, 'is_junction') and stage.is_junction()):
        raise ValueError('临时目录含链接，已停止清理')
    marker = json.loads((stage / 'import-operation.json').read_text(encoding='utf-8'))
    if marker != {'operationId': operation_id, 'target': str(target)}:
        raise ValueError('临时目录不属于本次复制，已停止清理')
    for path in stage.rglob('*'):
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise ValueError('临时目录含链接，已停止清理')
    from app.utils.windows_paths import filesystem_path
    shutil.rmtree(filesystem_path(stage))
