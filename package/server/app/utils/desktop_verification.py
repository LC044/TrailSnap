"""Offline, source-explicit media checks shared by conversion and update recovery."""
from contextlib import closing
import hashlib
import json
import sqlite3
import threading
from pathlib import Path

from app.service.storage_paths import validate_relative
from app.utils.windows_paths import filesystem_path


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


def _sample(path, full=False, checkpoint=None):
    with open(filesystem_path(Path(path)), 'rb') as stream:
        if full and checkpoint:
            digest = hashlib.sha256()
            while chunk := stream.read(1024 * 1024):
                checkpoint()
                digest.update(chunk)
            return digest.hexdigest()
        if full:
            return hashlib.file_digest(stream, 'sha256').hexdigest()
        return hashlib.sha256(stream.read(65536)).hexdigest()


def media_baseline(root: Path, limit=32, full=False, progress=None, *,
                   copy_external=False, excluded_entries=()):
    """Fingerprint media included in a copy, never untouched external originals."""
    root = root.resolve()
    database = root / 'data/trailsnap.sqlite'
    if not database.is_file():
        return []
    result = []
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='photos'").fetchone():
            return []
        for photo, _, path in photo_paths(db, root):
            resolved = Path(path).resolve()
            if resolved.is_relative_to(root):
                relative = resolved.relative_to(root)
                if any(relative == Path(entry) or Path(entry) in relative.parents for entry in excluded_entries):
                    continue
            elif not copy_external:
                continue
            if progress:
                progress(len(result), 0)
            if Path(path).is_file():
                result.append({'id': photo, 'copied': True,
                               'sha256' if full else 'sha256Prefix': _sample(path, full, (lambda: progress(len(result), 0)) if progress else None)})
                if limit is not None and len(result) >= limit:
                    break
    return result


def verify_media(root: Path, baseline, progress=None):
    root = root.resolve()
    expected = {item['id']: item for item in baseline}
    if not expected:
        return 0  # Empty libraries and already-offline external disks are valid.
    verified = 0
    with closing(sqlite3.connect((root / 'data/trailsnap.sqlite').as_uri() + '?mode=ro', uri=True)) as db:
        for photo, _, path in photo_paths(db, root):
            if photo not in expected:
                continue
            item = expected.pop(photo)
            internal = Path(path).resolve().is_relative_to(root)
            # Old 0.18.0 journals included every external original. Discard those
            # entries without opening the file, including offline external disks.
            # New proofs explicitly mark copied media and must never accept a
            # copied record redirected outside the destination library.
            if not internal and not item.get('copied'):
                continue
            try:
                if not internal:
                    raise ValueError('复制后的照片路径超出新图库')
                digest, full = item.get('sha256', item.get('sha256Prefix')), 'sha256' in item
                if progress:
                    progress(verified, len(baseline))
                if _sample(path, full, (lambda: progress(verified, len(baseline))) if progress else None) != digest:
                    raise ValueError('文件内容与升级前不一致')
            except (OSError, ValueError) as error:
                raise ValueError(f'升级前可读取的照片现在无法验证：{path}。{error}。已停止切换，请查看日志。') from error
            verified += 1
            if progress:
                progress(verified, len(baseline))
    if expected:
        raise ValueError('升级后的图库缺少原有照片记录，已停止切换')
    return verified


_runtime_lock = threading.Lock()
_runtime_results = {}


def verify_runtime_media(root: Path, baseline_path: Path, nonce: str):
    """One immutable proof per candidate launch, even after HTTP disconnects.

    Cache failures too: retries must report the original failure instead of
    starting another whole-library read. A new candidate nonce permits a retry.
    """
    key = (str(root.resolve()), str(baseline_path.resolve()), nonce)
    with _runtime_lock:
        if key not in _runtime_results:
            try:
                expected = json.loads(baseline_path.read_text(encoding='utf-8'))
                verify_media(root, expected.get('media', []))
            except (ValueError, OSError) as error:
                _runtime_results[key] = str(error)
            else:
                _runtime_results[key] = None
        error = _runtime_results[key]
    if error is not None:
        raise ValueError(error)
