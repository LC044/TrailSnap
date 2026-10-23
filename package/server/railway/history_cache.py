"""Versioned railway reference cache. Independent, rebuildable SQLite data, no ORM schema changes."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from contextlib import contextmanager
from datetime import date
from urllib.request import urlopen

DEFAULT_FEED = 'https://raw.githubusercontent.com/LC044/trailsnap-railway-history/main/data/feed/'
MAX_PACK_BYTES = 128 * 1024 * 1024
MAX_JSON_BYTES = 512 * 1024 * 1024


def cache_path():
    from app.core.paths import DATA_DIR
    return Path(os.getenv('RAILWAY_HISTORY_DB') or Path(DATA_DIR) / 'railway-history.sqlite')


class HistoryCache:
    def __init__(self, file=None):
        self.file = Path(file) if file is not None else cache_path()
        self.file.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS entity (key TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS station_name (name TEXT NOT NULL, code TEXT NOT NULL,
                    PRIMARY KEY(name, code));
                CREATE TABLE IF NOT EXISTS train_version (code TEXT NOT NULL, hash TEXT NOT NULL,
                    body TEXT NOT NULL, PRIMARY KEY(code, hash));
                CREATE TABLE IF NOT EXISTS observation (code TEXT NOT NULL, day TEXT NOT NULL, hash TEXT NOT NULL,
                    PRIMARY KEY(code, day, hash));
                CREATE INDEX IF NOT EXISTS observation_code_day ON observation(code, day);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.file, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _sequence(db):
        row = db.execute("SELECT value FROM meta WHERE key='sequence'").fetchone()
        return int(row[0]) if row else 0

    def status(self):
        with self.connect() as db:
            metadata = db.execute("SELECT value FROM meta WHERE key='metadata'").fetchone()
            return {'sequence': self._sequence(db),
                    'metadata': json.loads(metadata[0]) if metadata else {},
                    'stations': db.execute("SELECT count(*) FROM entity WHERE key LIKE 'station:%'").fetchone()[0],
                    'trains': db.execute('SELECT count(DISTINCT code) FROM train_version').fetchone()[0],
                    'versions': db.execute('SELECT count(*) FROM train_version').fetchone()[0]}

    def projected_sequence(self):
        with self.connect() as db:
            row = db.execute("SELECT value FROM meta WHERE key='station_projection_sequence'").fetchone()
            return int(row[0]) if row else 0

    def mark_projected(self, sequence):
        with self.connect() as db:
            db.execute('''INSERT INTO meta VALUES ('station_projection_sequence', ?)
                ON CONFLICT(key) DO UPDATE SET value =
                max(CAST(meta.value AS INTEGER), CAST(excluded.value AS INTEGER))''', (str(sequence),))

    def sync(self, manifest, loader):
        if manifest.get('schema_version') != 1:
            raise ValueError('Unsupported railway feed schema')
        target = manifest['sequence']
        if type(target) is not int or not 1 <= target <= 10000000:
            raise ValueError('Railway feed rollback or invalid sequence')
        with self.connect() as db:
            cursor = self._sequence(db)
        if target < cursor:
            raise ValueError('Railway feed rollback refused')
        if target == cursor:
            return self.status()
        deltas = sorted((d for d in manifest['deltas'] if d['sequence'] > cursor), key=lambda d: d['sequence'])
        contiguous = len(deltas) == target-cursor and all(d['sequence']==cursor+i+1 for i,d in enumerate(deltas))
        if cursor == 0 or not contiguous:
            deltas = [manifest['snapshot']]
            if deltas[0]['sequence'] != target:
                raise ValueError('Invalid snapshot sequence')
        for descriptor in deltas:
            file = descriptor['file']
            if not re.fullmatch(r'packs/[a-f0-9]{64}\.json\.gz', file):
                raise ValueError('Invalid pack path')
            raw = loader(file)
            if len(raw) > MAX_PACK_BYTES or len(raw) != descriptor['bytes'] or hashlib.sha256(raw).hexdigest() != descriptor['sha256']:
                raise ValueError('Railway pack checksum/size mismatch')
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
                decoded = compressed.read(MAX_JSON_BYTES + 1)
            if len(decoded) > MAX_JSON_BYTES:
                raise ValueError('Railway pack too large')
            pack = json.loads(decoded)
            if pack.get('schema_version') != 1 or pack['sequence'] != descriptor['sequence']:
                raise ValueError('Invalid pack schema or sequence')
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                current = self._sequence(db)
                if current >= pack['sequence']:
                    continue
                if current != pack['sequence'] - 1 and not pack.get('full'):
                    raise ValueError('Railway incremental sequence gap')
                for item in pack['upserts']:
                    self._upsert(db, item['key'], item['value'])
                db.execute("INSERT OR REPLACE INTO meta VALUES ('sequence', ?)", (str(pack['sequence']),))
                db.execute("INSERT OR REPLACE INTO meta VALUES ('metadata', ?)", (json.dumps(manifest.get('metadata', {})),))
        return self.status()

    @staticmethod
    def _upsert(db, key, value):
        kind, code = key.split(':', 1)
        if kind == 'station':
            if value['telecode'] != code or not value['names']:
                raise ValueError('Invalid station identity')
            for epoch in value['names']:
                db.execute('INSERT OR IGNORE INTO station_name VALUES (?, ?)', (epoch['name'], code))
        elif kind == 'train':
            if value['code'] != code:
                raise ValueError('Invalid train identity')
            for version in value['versions']:
                days = version.get('dates') or sorted(set([version['fd'], version['ld']]))
                for day in days:
                    date.fromisoformat(day)
                    db.execute('INSERT OR IGNORE INTO observation VALUES (?, ?, ?)', (code, day, version['h']))
                db.execute('INSERT OR REPLACE INTO train_version VALUES (?, ?, ?)',
                           (code, version['h'], json.dumps(version, ensure_ascii=False)))
        else:
            raise ValueError('Unknown railway entity kind')
        db.execute('INSERT OR REPLACE INTO entity VALUES (?, ?)', (key, json.dumps(value, ensure_ascii=False)))

    def stations(self, name_or_code):
        with self.connect() as db:
            rows = db.execute('''SELECT body FROM entity WHERE key=? OR key IN
                (SELECT 'station:' || code FROM station_name WHERE name=?) ORDER BY key''',
                ('station:' + name_or_code, name_or_code)).fetchall()
            return [json.loads(row[0]) for row in rows]

    def _station(self, name_or_code):
        rows = self.stations(name_or_code)
        return rows[0] if len(rows) == 1 else None

    def distance(self, first, second, day=None):
        def coord(station):
            if not station:
                return None
            versions = station.get('versions') or []
            if not versions:
                return None
            if day:
                selected = min(versions, key=lambda v: (min(abs((date.fromisoformat(day)-date.fromisoformat(v[k])).days) for k in ('first','last')), v['first']))
            else:
                selected = versions[-1]
            gps = selected['data'].get('gps') or {}
            try:
                lat, lng = float(gps['latitude']), float(gps.get('longitude', gps.get('longitute')))
                if not math.isfinite(lat) or not math.isfinite(lng) or not -90<=lat<=90 or not -180<=lng<=180 or (lat == 0 and lng == 0):
                    return None
                return lat, lng
            except (KeyError, TypeError, ValueError):
                return None
        a, b = coord(self._station(first)), coord(self._station(second))
        if a is None or b is None:
            return None
        lat1, lng1, lat2, lng2 = map(math.radians, (*a, *b))
        h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lng2-lng1)/2)**2
        return round(2*6371.0088*math.asin(math.sqrt(min(1,max(0,h))))*1.2, 1)

    def resolve(self, train_code, day, departure=None, arrival=None):
        day = date.fromisoformat(str(day)[:10]).isoformat()
        code = train_code.strip().upper()
        with self.connect() as db:
            detailed = db.execute("SELECT 1 FROM train_version WHERE code=? AND json_array_length(body,'$.s')>0 LIMIT 1", (code,)).fetchone()
            # Nearest observations on either side; never read years of repeated timetable JSON.
            detail_filter = " AND json_array_length(v.body,'$.s')>0" if detailed else ''
            rows = []
            for comparator, ordering in [('<=','DESC'), ('>','ASC')]:
                nearest_day = db.execute(f'''SELECT o.day FROM observation o JOIN train_version v
                    ON v.code=o.code AND v.hash=o.hash WHERE o.code=? AND o.day {comparator} ?
                    {detail_filter} ORDER BY o.day {ordering} LIMIT 1''', (code, day)).fetchone()
                if nearest_day:
                    rows.extend(db.execute(f'''SELECT o.day,v.body FROM observation o JOIN train_version v
                        ON v.code=o.code AND v.hash=o.hash WHERE o.code=? AND o.day=? {detail_filter}
                        ORDER BY o.hash''', (code, nearest_day[0])).fetchall())
            rows.sort(key=lambda r:(abs((date.fromisoformat(r['day'])-date.fromisoformat(day)).days), -date.fromisoformat(r['day']).toordinal()))
        # Select date first; endpoints may disambiguate multiple versions on the SAME nearest date.
        chosen = None
        if rows:
            nearest = abs((date.fromisoformat(rows[0]['day'])-date.fromisoformat(day)).days)
            candidates = [r for r in rows if abs((date.fromisoformat(r['day'])-date.fromisoformat(day)).days) == nearest]
            chosen = candidates[0]
            for candidate in candidates:
                version = json.loads(candidate['body'])
                if self._slice(version['s'], departure, arrival) is not None:
                    chosen = candidate
                    break
        if chosen:
            version = json.loads(chosen['body'])
            if not version['s']:
                departure = departure or version['f']
                arrival = arrival or version['t']
            stops = self._slice(version['s'], departure, arrival)
            if stops is not None:
                result = self._result(code, day, stops, version['no'], 'exact' if chosen['day']==day else 'nearest', chosen['day'])
                result['version'] = version['h']
                return result
        stops = [{'n':n, 'c':(self._station(n) or {}).get('telecode',''), 'a':None,'d':None,'dd':0}
                 for n in (departure, arrival) if n]
        result = self._result(code, day, stops, None, 'endpoints', None)
        result['duration_minutes'] = None
        result['stops'] = []
        return result

    def _slice(self, stops, departure, arrival):
        if not stops:
            return None
        def match(stop, name):
            if stop['n'] == name or stop.get('c') == name:
                return True
            station = self._station(name)
            return bool(station and station['telecode'] == stop.get('c'))
        if not departure and not arrival:
            return stops
        for i, stop in enumerate(stops):
            if departure and not match(stop, departure):
                continue
            for j in range(i+1,len(stops)):
                if not arrival or match(stops[j], arrival):
                    return stops[i:j+1]
        return None

    def _result(self, code, day, stops, no, match, matched_date):
        total = 0.0 if len(stops)>1 else None
        cumulative = [0.0] if stops else []
        for a,b in zip(stops,stops[1:]):
            segment = self.distance(a.get('c') or a['n'], b.get('c') or b['n'], matched_date or day)
            total = round(total+segment,1) if segment is not None and total is not None else None
            cumulative.append(total)
        duration = None
        if len(stops)>1 and stops[0].get('d') and stops[-1].get('a'):
            def minutes(t):
                h,m = map(int,t.split(':')[:2]); return h*60+m
            # Raw running_time gives unambiguous elapsed minutes even for departures just after midnight.
            def running(stop):
                raw = stop.get('raw') or {}
                t = raw.get('running_time', '')
                return minutes(t) if re.fullmatch(r'\d+:\d{2}',t) else None
            start, end = running(stops[0]), running(stops[-1])
            if start is not None and end is not None:
                dwell = (minutes(stops[0]['d'])-minutes(stops[0]['a'])) % 1440 if stops[0].get('a') else 0
                duration = end-start-dwell
            else:
                departure_day = stops[0]['dd'] + (1 if stops[0].get('a') and minutes(stops[0]['d']) < minutes(stops[0]['a']) else 0)
                duration = (stops[-1]['dd']-departure_day)*1440+minutes(stops[-1]['a'])-minutes(stops[0]['d'])
            if duration<0:
                duration=None
        return {'train_code':code,'query_date':day,'matched_date':matched_date,'match':match,'train_no':no,
                'departure_station':stops[0]['n'] if stops else None,'arrival_station':stops[-1]['n'] if stops else None,
                'distance_km':total,'distance_source':'gps-haversine-x1.2' if total is not None else None,
                'duration_minutes':duration,'stops':[dict(s, accumulated_mileage=cumulative[i]) for i,s in enumerate(stops)]}


def fetch_feed(base_url=None, cache=None):
    base_url = base_url or os.getenv('RAILWAY_HISTORY_FEED_URL') or DEFAULT_FEED
    if not base_url.startswith('https://'):
        raise ValueError('Railway feed requires HTTPS')
    base_url = base_url.rstrip('/')+'/'
    def download(file):
        with urlopen(base_url+file, timeout=30) as response:
            value=response.read(MAX_PACK_BYTES+1)
        if len(value)>MAX_PACK_BYTES:
            raise ValueError('Railway download too large')
        return value
    manifest=json.loads(download('manifest.json'))
    return (cache or HistoryCache()).sync(manifest, download)
