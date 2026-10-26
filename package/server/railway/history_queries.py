"""Read compatibility for public railway queries, backed only by observed history."""
from datetime import date

from railway.history_cache import HistoryCache


def _selected(day, train_code=None):
    # Prefer detailed history exactly as HistoryCache.resolve does. Pick a date
    # before filtering endpoints so an old route cannot masquerade as today's.
    where = 'WHERE o.code LIKE ?' if train_code else ''
    params = [str(day), str(day)]
    if train_code:
        params.append('%' + train_code.strip().upper() + '%')
    sql = f'''WITH ranked AS (
        SELECT o.code, o.day, v.body,
            row_number() OVER (PARTITION BY o.code ORDER BY
                CASE WHEN json_array_length(v.body, '$.s') > 0 THEN 0 ELSE 1 END,
                abs(julianday(o.day)-julianday(?)),
                CASE WHEN o.day >= ? THEN 0 ELSE 1 END, o.day DESC, o.hash) AS rank
        FROM observation o JOIN train_version v ON v.code=o.code AND v.hash=o.hash {where}
    ), selected AS (SELECT code, day, body FROM ranked WHERE rank=1)
    '''
    return sql, params


def trains(query, day=None, cache=None, train_no=None):
    cache = cache or HistoryCache()
    day = day or date.today()
    prefix, params = _selected(day, query.train_code)
    sql = '''SELECT code AS train_code, json_extract(body,'$.no') AS train_no,
        substr(code,1,1) AS train_type,
        coalesce(json_extract(body,'$.s[0].c'),'') AS from_station,
        coalesce(json_extract(body,'$.s[#-1].c'),'') AS to_station,
        json_extract(body,'$.f') AS departure_station_name,
        json_extract(body,'$.t') AS arrival_station_name, day AS matched_date
        FROM selected WHERE 1=1'''
    if train_no:
        sql += " AND json_extract(body,'$.no')=?"
        params.append(train_no)
    for field, value in [('train_type', query.train_type), ('from_station', query.from_station), ('to_station', query.to_station)]:
        if value:
            if field == 'train_type':
                sql += ' AND substr(code,1,1)=?'
                params.append(value.upper())
            else:
                endpoint = '0' if field == 'from_station' else '#-1'
                name_field = 'f' if field == 'from_station' else 't'
                sql += f''' AND (json_extract(body,'$.s[{endpoint}].c')=?
                    OR json_extract(body,'$.{name_field}') LIKE ?
                    OR json_extract(body,'$.s[{endpoint}].c') IN
                        (SELECT code FROM station_name WHERE name LIKE ?))'''
                params.extend([value, '%'+value+'%', '%'+value+'%'])
    sql += ' ORDER BY code'
    with cache.connect() as db:
        # SQLite WITH must precede the count wrapper as well.
        total = db.execute(prefix + 'SELECT count(*) FROM (' + sql + ')', params).fetchone()[0]
        rows = db.execute(prefix + sql + ' LIMIT ? OFFSET ?', [*params, query.page_size, (query.page-1)*query.page_size]).fetchall()
    items = [dict(row, train_id=None, query_date=str(day), match='exact' if row['matched_date']==str(day) else 'nearest') for row in rows]
    return {'total':total,'page':query.page,'page_size':query.page_size,
            'total_page':(total+query.page_size-1)//query.page_size,'list':items}


def schedules(query, day=None, cache=None):
    cache = cache or HistoryCache()
    day = day or date.today()
    prefix, params = _selected(day, query.train_code)
    sql = '''SELECT selected.code, selected.day, CAST(stop.key AS INTEGER) AS position
        FROM selected, json_each(selected.body,'$.s') stop WHERE 1=1'''
    if query.train_no:
        sql += " AND json_extract(body,'$.no')=?"
        params.append(query.train_no)
    if query.train_code:
        sql += ' AND selected.code=?'
        params.append(query.train_code.strip().upper())
    if query.station_telecode:
        sql += " AND json_extract(stop.value,'$.c')=?"
        params.append(query.station_telecode)
    if query.station_name:
        sql += """ AND (json_extract(stop.value,'$.n') LIKE ? OR json_extract(stop.value,'$.c') IN
            (SELECT code FROM station_name WHERE name LIKE ?))"""
        params.extend(['%'+query.station_name+'%']*2)
    for field, expression in [('is_departure', 'CAST(stop.key AS INTEGER)=0'),
                              ('is_arrival', "CAST(stop.key AS INTEGER)=json_array_length(body,'$.s')-1")]:
        value = getattr(query, field)
        if value is not None:
            sql += f' AND ({expression})=?'
            params.append(value)
    with cache.connect() as db:
        total = db.execute(prefix + 'SELECT count(*) FROM ('+sql+')', params).fetchone()[0]
        rows = db.execute(prefix+sql+' ORDER BY selected.code, position LIMIT ? OFFSET ?',
                          [*params, query.page_size, (query.page-1)*query.page_size]).fetchall()
    results, resolved = [], {}
    for row in rows:
        if row['code'] not in resolved:
            resolved[row['code']] = schedule_details(cache.resolve(row['code'], day))
        results.append(resolved[row['code']][row['position']])
    return {'total':total,'page':query.page,'page_size':query.page_size,
            'total_page':(total+query.page_size-1)//query.page_size,'list':results}


def schedule_details(result):
    def minutes(value):
        if not value:
            return None
        hour, minute = value.split(':')[:2]
        return int(hour)*60+int(minute)
    stops = result['stops']
    first_clock = minutes(stops[0].get('d') or stops[0].get('a')) if stops else None
    baseline = stops[0]['dd']*1440+first_clock if first_clock is not None else None
    rows = []
    for index, stop in enumerate(stops):
        raw = stop.get('raw') or {}
        running = minutes(raw.get('running_time'))
        if running is None:
            clock = minutes(stop.get('a') or stop.get('d'))
            running = max(0, stop['dd']*1440+clock-baseline) if clock is not None and baseline is not None else None
        dwell = (minutes(stop['d'])-minutes(stop['a']))%1440 if stop.get('a') and stop.get('d') else 0
        rows.append(dict(schedule_id=None, train_no=result['train_no'], train_code=result['train_code'],
                         station_telecode=stop.get('c',''), station_name=stop['n'], sequence=index+1,
                         arrive_day_diff=stop['dd'], arrival_time=stop.get('a'), departure_time=stop.get('d'),
                         stop_duration=dwell, accumulated_mileage=stop['accumulated_mileage'], running_time=running,
                         is_departure=int(index==0), is_arrival=int(index==len(stops)-1),
                         query_date=result['query_date'], matched_date=result['matched_date'], match=result['match']))
    return rows
