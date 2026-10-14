"""Offline, source-explicit media checks shared by conversion and update recovery."""
from contextlib import closing
import hashlib
import sqlite3
from pathlib import Path

from app.service.storage_paths import validate_relative


def photo_paths(db, root: Path):
    columns = {row[1] for row in db.execute('PRAGMA table_info(photos)')}
    if not {'id', 'owner_id', 'file_path'}.issubset(columns):
        return
    if 'storage_root_id' not in columns:
        yield from db.execute('SELECT id, owner_id, file_path FROM photos')
        return
    roots = {row[0]: row[1:] for row in db.execute('SELECT id,owner_id,kind,location FROM storage_roots')}
    for photo, owner, legacy, ref, relative in db.execute('SELECT id,owner_id,file_path,storage_root_id,storage_relative_path FROM photos'):
        if ref is None and relative is None:
            yield photo, owner, legacy
            continue
        record = roots.get(ref)
        if record is None or record[0] != owner or not relative:
            raise ValueError('照片的存储目录引用无效，请先修复图库')
        _, kind, location = record
        if kind in {'managed', 'instance-relative'}:
            anchor = (root / validate_relative(location, allow_dot=True)).resolve()
            if not anchor.is_relative_to(root):
                raise ValueError('存储目录超出图库范围')
        elif kind == 'external' and Path(location).is_absolute():
            anchor = Path(location).resolve()
        else:
            raise ValueError('存储目录配置无效')
        path = (anchor / validate_relative(relative)).resolve()
        if not path.is_relative_to(anchor):
            raise ValueError('照片路径超出存储目录')
        yield photo, owner, str(path)


def _sample(path):
    with open(path, 'rb') as stream:
        return hashlib.sha256(stream.read(65536)).hexdigest()


def media_baseline(root: Path, limit=32):
    database = root / 'data/trailsnap.sqlite'
    if not database.is_file():
        return []
    result = []
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='photos'").fetchone():
            return []
        for photo, _, path in photo_paths(db, root):
            if Path(path).is_file():
                result.append({'id': photo, 'sha256Prefix': _sample(path)})
                if len(result) >= limit:
                    break
    return result


def verify_media(root: Path, baseline):
    expected = {item['id']: item['sha256Prefix'] for item in baseline}
    if not expected:
        return 0  # Empty libraries and already-offline external disks are valid.
    verified = 0
    with closing(sqlite3.connect((root / 'data/trailsnap.sqlite').as_uri() + '?mode=ro', uri=True)) as db:
        for photo, _, path in photo_paths(db, root):
            if photo not in expected:
                continue
            try:
                if _sample(path) != expected.pop(photo):
                    raise ValueError('文件内容与升级前不一致')
            except (OSError, ValueError) as error:
                raise ValueError(f'升级前可读取的照片现在无法验证：{path}。已停止切换，请查看日志。') from error
            verified += 1
    if expected:
        raise ValueError('升级后的图库缺少原有照片记录，已停止切换')
    return verified
