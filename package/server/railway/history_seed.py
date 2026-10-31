"""Offline historical feed bundled outside the writable data volume."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from railway.history_cache import HistoryCache


def seed_directory():
    from app.core.paths import BUNDLE_ROOT
    return Path(BUNDLE_ROOT) / 'resources' / 'railway-history'


def station_metadata():
    from app.core.paths import BUNDLE_ROOT
    value = json.loads((Path(BUNDLE_ROOT) / 'resources' / 'railway-stations.json').read_text(encoding='utf-8'))
    if value['schema_version'] != 1:
        raise ValueError('Unsupported station metadata schema')
    return value['stations']


def update_history_seed(directory=None):
    """Download a Release snapshot into a build image's offline seed directory."""
    from railway.history_cache import read_feed
    manifest, download = read_feed()
    directory = Path(directory) if directory is not None else seed_directory()
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / 'manifest.json').exists():
        previous = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        if previous['schema_version'] == manifest['schema_version'] and previous['sequence'] > manifest['sequence']:
            raise ValueError('Bundled railway feed rollback refused')
    with TemporaryDirectory() as temporary:
        cache = HistoryCache(Path(temporary) / 'validation.sqlite')
        def load(file):
            raw = download(file)
            target = Path(temporary) / file
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            return raw
        result = cache.sync(dict(manifest, deltas=[]), load)
        file = manifest['snapshot']['file']
        target = directory / file
        target.parent.mkdir(parents=True, exist_ok=True)
        staged = target.with_suffix('.tmp')
        staged.write_bytes((Path(temporary) / file).read_bytes())
        os.replace(staged, target)
        staged_manifest = directory / 'manifest.json.tmp'
        staged_manifest.write_text(json.dumps(dict(manifest, deltas=[]), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        os.replace(staged_manifest, directory / 'manifest.json')
    return result


def import_history_seed(cache=None, directory=None):
    cache = cache or HistoryCache()
    directory = Path(directory) if directory is not None else seed_directory()
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    snapshot_path = directory / manifest['snapshot']['file']
    if snapshot_path.is_file():
        loader = lambda file: (directory / file).read_bytes()
    else:
        # Source checkouts do not contain full snapshots. Docker builds fetch the
        # immutable Release asset into the image; local/dev startup can fetch it too.
        from railway.history_cache import read_feed
        manifest, loader = read_feed()
    # Upgrading/downgrading an image must never roll back a newer user cache.
    status = cache.status()
    if status['schema_version'] != manifest['schema_version'] or status['sequence'] < manifest['sequence']:
        cache.sync(dict(manifest, deltas=[]), loader)
    return cache.status()


def ensure_history_seed():
    from railway.history_sync import project_stations
    cache = HistoryCache()
    result = import_history_seed(cache)
    # Projection belongs to the target relational database. Reapply on startup
    # even when its volume was recreated independently of the history cache.
    project_stations(cache=cache)
    cache.mark_projected(result['sequence'])
    return result
