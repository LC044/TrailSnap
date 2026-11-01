"""Receive pg_dumpall on stdin; preserve private state via the Docker bind mount."""
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

os.umask(0o077)
state = Path('/state')
record = json.loads((state/'runtime/installation.json').read_text())
base = state/'backups'
base.mkdir(exist_ok=True)
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
staging = base/('.incomplete-'+stamp)
staging.mkdir()
count = 0
with gzip.open(staging/'databases.sql.gz', 'wb') as stream:
    while chunk := sys.stdin.buffer.read(1024*1024):
        count += len(chunk)
        stream.write(chunk)
if count < 100:
    raise RuntimeError('数据库备份为空或不完整。')
with gzip.open(staging/'databases.sql.gz', 'rb') as stream:
    while stream.read(1024*1024):
        pass
shutil.copytree(state/'runtime', staging/'runtime')
shutil.copy2(state/'data/system_config.json', staging/'system_config.json')
for path in [base, staging, *staging.rglob('*')]:
    os.chown(path, record['uid'], record['gid'])
    os.chmod(path, 0o700 if path.is_dir() else 0o600)
staging.rename(base/('pre-upgrade-'+stamp))
print('升级前数据库及配置备份完成。')
