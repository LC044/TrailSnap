"""Copied media proofs exclude untouched originals and survive HTTP retries."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import threading

import pytest

from app.utils import desktop_verification as verification
from app.utils.portable_library import snapshot_library

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


@pytest.fixture
def media(tmp_path):
    root = tmp_path / 'library'
    (root / 'data').mkdir(parents=True)
    internal = root / 'data/upload.jpg'
    external = tmp_path / 'external/video.mp4'
    external.parent.mkdir()
    internal.write_bytes(b'original' * 20000)
    external.write_bytes(b'external original')
    database = root / 'data/trailsnap.sqlite'
    with closing(sqlite3.connect(database)) as db, db:
        db.execute('CREATE TABLE photos(id TEXT, owner_id TEXT, file_path TEXT)')
        db.executemany('INSERT INTO photos VALUES (?,?,?)',
                       [('upload', 'owner', str(internal)), ('external', 'owner', str(external))])
    return root, internal, external, database


def test_only_copied_media_is_read_and_damage_beyond_prefix_is_rejected(media, monkeypatch):
    root, internal, external, _ = media
    original = verification._sample
    reads = []

    def sample(path, *args):
        assert Path(path) != external, 'untouched external media must never be opened'
        reads.append(Path(path))
        return original(path, *args)

    monkeypatch.setattr(verification, '_sample', sample)
    baseline = verification.media_baseline(root, limit=None, full=True)
    assert [item['id'] for item in baseline] == ['upload']
    assert verification.verify_media(root, baseline) == 1
    with internal.open('r+b') as stream:
        stream.seek(70000)
        stream.write(b'corruption')
    with pytest.raises(ValueError, match='内容与升级前不一致'):
        verification.verify_media(root, baseline)
    assert reads == [internal] * 3


def test_copy_external_opt_in_verifies_copied_destination(media):
    root, _, external, database = media
    baseline = verification.media_baseline(root, limit=None, full=True, copy_external=True)
    assert {item['id'] for item in baseline} == {'upload', 'external'}
    destination = root / 'data/imported.mp4'
    destination.write_bytes(external.read_bytes())
    with closing(sqlite3.connect(database)) as db, db:
        db.execute('UPDATE photos SET file_path=? WHERE id=?', (str(destination), 'external'))
    external.unlink()  # The independent copy must not depend on its source.
    assert verification.verify_media(root, baseline) == 2
    destination.write_bytes(b'broken copy')
    with pytest.raises(ValueError, match='无法验证'):
        verification.verify_media(root, baseline)


def test_old_all_media_proof_skips_changed_or_offline_external_file(media, monkeypatch):
    root, _, external, _ = media
    baseline = verification.media_baseline(root, limit=None, full=True, copy_external=True)
    for item in baseline:
        item.pop('copied')  # Already-published 0.18.0 upgrade journals.
    external.write_bytes(b'edited EXIF after migration')
    original = verification._sample

    def sample(path, *args):
        assert Path(path) != external
        return original(path, *args)

    monkeypatch.setattr(verification, '_sample', sample)
    assert verification.verify_media(root, baseline) == 1
    external.unlink()
    assert verification.verify_media(root, baseline) == 1


def test_copied_reference_cannot_escape_destination_or_disappear(media):
    root, _, external, database = media
    baseline = verification.media_baseline(root, full=True)
    with closing(sqlite3.connect(database)) as db, db:
        db.execute('UPDATE photos SET file_path=? WHERE id=?', (str(external), 'upload'))
    with pytest.raises(ValueError, match='路径超出新图库'):
        verification.verify_media(root, baseline)
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("DELETE FROM photos WHERE id='upload'")
    with pytest.raises(ValueError, match='缺少原有照片记录'):
        verification.verify_media(root, baseline)


def test_excluded_installation_data_does_not_enter_copy_proof(media):
    root, _, _, database = media
    excluded = root / 'userdata/data/other.jpg'
    excluded.parent.mkdir(parents=True)
    excluded.write_bytes(b'new live library, excluded from copy')
    with closing(sqlite3.connect(database)) as db, db:
        db.execute('INSERT INTO photos VALUES (?,?,?)', ('excluded', 'owner', str(excluded)))
    baseline = verification.media_baseline(root, limit=None, excluded_entries={'userdata'})
    assert [item['id'] for item in baseline] == ['upload']


def test_database_snapshot_does_not_read_any_media(media, monkeypatch):
    root, _, _, _ = media

    def unexpected(*args, **kwargs):
        pytest.fail('a database/config snapshot does not copy photos')

    monkeypatch.setattr(verification, '_sample', unexpected)
    destination = root / 'backups/test'
    snapshot_library(root, destination)
    assert json.loads((destination / 'snapshot.json').read_text())['media'] == []


@pytest.mark.parametrize('failure', [False, True])
def test_runtime_retries_share_one_inflight_verification_and_cache_result(tmp_path, monkeypatch, failure):
    proof = tmp_path / 'proof.json'
    proof.write_text('{"media": []}')
    entered, release, retry_started = threading.Event(), threading.Event(), threading.Event()
    calls = []
    monkeypatch.setattr(verification, '_runtime_results', {})

    def verify(*args):
        calls.append(args)
        entered.set()
        assert release.wait(5)
        if failure:
            raise ValueError('damaged copied photo')

    def request(retry=False):
        if retry:
            retry_started.set()
        try:
            verification.verify_runtime_media(tmp_path, proof, 'candidate-1')
        except ValueError as error:
            return str(error)
        return 'ok'

    monkeypatch.setattr(verification, 'verify_media', verify)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(request)
        assert entered.wait(5)
        second = pool.submit(request, True)
        assert retry_started.wait(5)
        release.set()
        expected = 'damaged copied photo' if failure else 'ok'
        assert first.result(timeout=5) == second.result(timeout=5) == expected
    assert request() == expected
    assert len(calls) == 1
    if failure:
        with pytest.raises(ValueError, match='damaged copied photo'):
            verification.verify_runtime_media(tmp_path, proof, 'candidate-2')
    else:
        verification.verify_runtime_media(tmp_path, proof, 'candidate-2')
    assert len(calls) == 2
