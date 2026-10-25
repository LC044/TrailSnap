"""Scheduled optional railway feed sync; failure leaves the last local cache usable."""
import logging
import os
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


def sync_history():
    from railway.history_cache import HistoryCache, fetch_feed
    try:
        from railway.initialization import wait_for_initialization
        wait_for_initialization()
        cache = HistoryCache()
        result = fetch_feed(cache=cache)
        sequence = result['sequence']
        if sequence <= cache.projected_sequence():
            logger.debug('Railway history unchanged at sequence %s; skipping', sequence)
            return
        project_stations()
        # Mark only after a successful projection so interrupted updates retry.
        cache.mark_projected(sequence)
        logger.info('Railway history synced: %s', result)
    except Exception:
        logger.warning('Railway history sync unavailable; keeping local data', exc_info=True)


def project_stations(*, cache=None, sessions=None):
    """Update the legacy station search/city projection without replacing IDs or local details."""
    import json
    from railway.history_cache import HistoryCache
    from railway.db.models.models import Station
    from railway.coordinates import read_feed_coordinates, valid_coordinates, sync_coordinate_cache
    cache = cache or HistoryCache()
    if sessions is None:
        from railway.db.session import SessionLocal
        sessions = SessionLocal
    with cache.connect() as source, sessions() as db:
        stations = {s.telecode:s for s in db.query(Station).all()}
        for record in source.execute("SELECT body FROM entity WHERE key LIKE 'station:%'"):
            value = json.loads(record[0])
            latest = (value.get('versions') or [{}])[-1].get('data', {})
            names = [n['name'] for n in value['names']]
            row = stations.get(value['telecode'])
            if row is None:
                row = Station(telecode=value['telecode'], station_name=names[-1], station_pinyin='', station_py='',city='')
                db.add(row)
            aliases = list(dict.fromkeys([*(getattr(row, 'alias_names', None) or []), row.station_name, *names]))
            row.station_name = names[-1]
            # Older railway seed schemas have no alias column; full history remains
            # queryable in HistoryCache without changing the legacy ORM schema.
            if hasattr(Station, 'alias_names'):
                row.alias_names = [n for n in aliases if n and n != row.station_name]
            row.station_pinyin = latest.get('pinyin') or value.get('pinyin') or row.station_pinyin
            row.station_py = latest.get('pinyin_short') or value.get('pinyin_short') or row.station_py
            row.city = latest.get('city') or value.get('city') or row.city
            row.status = 1 if value['status']=='active' else 0
            coordinates = read_feed_coordinates(value)
            if coordinates and (not valid_coordinates(row.latitude, row.longitude) or row.coordinate_source == '12306'):
                lat, lng, system = coordinates
                if valid_coordinates(row.latitude, row.longitude) != (lat, lng):
                    row.coordinates_updated_at = datetime.now(timezone.utc)
                row.latitude, row.longitude = lat, lng
                row.coordinate_source, row.coordinate_system = '12306', system
                row.coordinate_status, row.coordinate_retry_after = 'ready', None
        db.commit()
        sync_coordinate_cache(cache, db.query(Station).all())


def sync_missing_coordinates():
    from railway.initialization import wait_for_initialization
    from railway.coordinates import backfill_missing_coordinates
    try:
        wait_for_initialization()
        result = backfill_missing_coordinates()
        logger.info('Railway coordinate backfill: %s', result)
    except Exception:
        # External request exceptions may include the credential-bearing URL.
        logger.warning('Railway coordinate backfill unavailable; retrying later')


def register_history_sync(scheduler):
    if os.getenv('RAILWAY_COORDINATE_SYNC_ENABLED', '1') != '0':
        scheduler.register_interval_job('railway-coordinate-sync', seconds=3600,
            fn=sync_missing_coordinates, next_run_time=datetime.now(timezone.utc)+timedelta(seconds=120))
    if os.getenv('RAILWAY_HISTORY_SYNC_ENABLED', '1') == '0':
        return
    scheduler.register_interval_job('railway-history-sync',
        seconds=max(3600, int(os.getenv('RAILWAY_HISTORY_SYNC_SECONDS', '86400'))),
        fn=sync_history, next_run_time=datetime.now(timezone.utc)+timedelta(seconds=60))
