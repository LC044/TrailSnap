"""Optional real collector replay; defaults to no external-data dependency."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from railway.history_cache import HistoryCache

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def test_railway_compact_production_replay(tmp_path):
    report_file = os.getenv('RAILWAY_COMPACT_REPLAY_REPORT')
    if not report_file:
        pytest.skip('Set RAILWAY_COMPACT_REPLAY_REPORT to the collector verify:compact report')
    report = json.loads(Path(report_file).read_text(encoding='utf-8'))
    # Freeze the actual pre-extension v2 implementation, not a mocked selector.
    reference = 'e9c6755c2baa3f76ce0bd53070f26326be7d687f'
    root = Path(__file__).resolve().parents[4]
    source = subprocess.check_output(['git', 'show', f'{reference}:package/server/railway/history_cache.py'], cwd=root).decode()
    namespace = {'__name__': 'legacy_railway_cache'}
    exec(compile(source, 'legacy_railway_cache.py', 'exec'), namespace)
    legacy_type = namespace['HistoryCache']
    downloaded = []
    def load(name):
        downloaded.append(name)
        return Path(report['files'][name]).read_bytes()
    baseline = legacy_type(tmp_path / 'baseline.sqlite')
    baseline.sync(report['baseline'], load)
    for name in ('legacy', 'upgraded'):
        shutil.copyfile(baseline.file, tmp_path / f'{name}.sqlite')
    upgraded = HistoryCache(tmp_path / 'upgraded.sqlite')
    legacy = legacy_type(tmp_path / 'legacy.sqlite')
    downloaded.clear()
    upgraded.sync(report['current'], load)
    assert downloaded == [report['current']['compact_deltas'][-1]['file']]
    downloaded.clear()
    legacy.sync(report['current'], load)
    assert downloaded == [report['current']['snapshot']['file']]
    fresh = HistoryCache(tmp_path / 'fresh.sqlite')
    fresh.sync(report['current'], load)
    def signature(cache):
        tables = {}
        with cache.connect() as db:
            for table, columns in [('entity', 'key,body'), ('train_version', 'code,hash,body'),
                                   ('observation', 'code,day,hash'), ('station_name', 'name,code')]:
                digest = hashlib.sha256()
                count = 0
                for row in db.execute(f'SELECT {columns} FROM {table} ORDER BY {columns}'):
                    values = list(row)
                    if columns.endswith('body'):
                        values[-1] = json.loads(values[-1])
                    digest.update(json.dumps(values, sort_keys=True, ensure_ascii=False).encode())
                    count += 1
                tables[table] = (count, digest.hexdigest())
        return tables
    expected = signature(fresh)
    assert signature(upgraded) == expected
    assert signature(legacy) == expected
    downloaded.clear()
    upgraded.sync(report['current'], load)
    assert not downloaded
