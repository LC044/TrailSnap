"""Create a tiny offline v2 seed for PR-only Docker validation images."""
import gzip
import hashlib
import json
from pathlib import Path


def main():
    root = Path(__file__).parents[1] / 'resources' / 'railway-history'
    pack = {
        'schema_version': 2,
        'sequence': 1,
        'full': True,
        'stations': [],
        'train_versions': [],
        'observations': [],
    }
    raw = gzip.compress(json.dumps(pack, separators=(',', ':')).encode('utf-8'), mtime=0)
    digest = hashlib.sha256(raw).hexdigest()
    file = f'packs/{digest}.json.gz'
    target = root / file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    manifest = {
        'schema_version': 2,
        'sequence': 1,
        'metadata': {'source': 'pull-request-validation'},
        'snapshot': {'sequence': 1, 'file': file, 'sha256': digest, 'bytes': len(raw)},
        'deltas': [],
    }
    (root / 'manifest.json').write_text(
        json.dumps(manifest, separators=(',', ':')) + '\n', encoding='utf-8'
    )


if __name__ == '__main__':
    main()
