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


def project_stations():
    """Update the legacy station search/city projection without replacing IDs or local details."""
    import json
    from railway.history_cache import HistoryCache
    from railway.db.session import SessionLocal
    from railway.db.models.models import Station
    cache = HistoryCache()
    with cache.connect() as source, SessionLocal() as db:
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
        db.commit()


def register_history_sync(scheduler):
    if os.getenv('RAILWAY_HISTORY_SYNC_ENABLED', '1') == '0':
        return
    scheduler.register_interval_job('railway-history-sync',
        seconds=max(3600, int(os.getenv('RAILWAY_HISTORY_SYNC_SECONDS', '86400'))),
        fn=sync_history, next_run_time=datetime.now(timezone.utc)+timedelta(seconds=60))
