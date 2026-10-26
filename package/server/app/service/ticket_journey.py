"""Keep OCR evidence and explicit estimates separate from timetable matches."""
import math
import re
from datetime import datetime


def parse_ticket_datetime(value,photo_time):
    for fmt in ('%Y年%m月%d日 %H:%M','%Y年%m月%d日%H:%M','%Y-%m-%d %H:%M','%Y/%m/%d %H:%M'):
        try:
            parsed=datetime.strptime(value,fmt)
            if not 1850<=parsed.year<=datetime.now().year+2:raise ValueError('Invalid ticket year')
            return parsed,False
        except (ValueError,TypeError):pass
    try:
        # A leap-year sentinel accepts a yearless February 29.
        parsed=datetime.strptime('2000年'+value,'%Y年%m月%d日 %H:%M')
    except (ValueError,TypeError):
        raise ValueError('票据日期时间无法识别，请重试或手动添加')
    if not photo_time:raise ValueError('票据缺少年份且照片无拍摄时间，请手动添加')
    for year in range(photo_time.year,photo_time.year-5,-1):
        try:return parsed.replace(year=year),True
        except ValueError:pass
    raise ValueError('票据日期时间无法识别，请重试或手动添加')


def _one_edit(first, second):
    if abs(len(first)-len(second)) > 1:
        return False
    if len(first) == len(second):
        return sum(a != b for a,b in zip(first,second)) == 1
    short,long = sorted((first,second), key=len)
    return any(long[:i]+long[i+1:] == short for i in range(len(long)))


def repair_station_names(ticket, cache, evidence=None):
    """Correct one OCR character only when the train route corroborates it.

    Requires the other endpoint to be known and the proposed ordered segment
    to exist. Never infer a redacted/missing station or replace a known name.
    """
    fields = ('departure_station','arrival_station')
    names = [getattr(ticket,k) for k in fields]
    if any(not re.fullmatch(r'[\u4e00-\u9fff]{2,8}',name or '') for name in names):
        return {}
    known = [bool(cache.stations(n)) for n in names]
    if sum(known) != 1:
        return {}
    route = cache.resolve(ticket.train_code,ticket.date_time)
    stops = route.get('stops') or []
    if not stops:
        return {}
    index = known.index(False)
    proposals = {s['n'] for s in stops if _one_edit(names[index],s['n'])}
    clock_confirmed=False
    duration=(evidence or {}).get('duration_minutes')
    if not proposals and index==0 and type(duration) is int and 0<duration<=10080:
        # Two damaged glyphs need both printed departure clock and elapsed time
        # to corroborate a unique route. Edit distance alone is insufficient.
        printed=ticket.date_time.hour*60+ticket.date_time.minute
        for stop in stops:
            name=stop['n'];clock=stop.get('d')
            if len(name)!=len(names[index]) or len(name)!=2 or not clock:continue
            hour,minute=map(int,clock.split(':')[:2]);difference=abs(hour*60+minute-printed)
            if min(difference,1440-difference)>5:continue
            resolved=cache.resolve(ticket.train_code,ticket.date_time,name,names[1])
            elapsed=resolved.get('duration_minutes')
            if elapsed is not None and abs(elapsed-duration)<=10:
                proposals.add(name);clock_confirmed=True
    valid = []
    for name in proposals:
        candidate=list(names);candidate[index]=name
        resolved=cache.resolve(ticket.train_code,ticket.date_time,*candidate)
        if resolved.get('match') in ('exact','nearest'):
            valid.append(name)
    if len(valid) != 1:
        return {}
    return {fields[index]:{'original':names[index],'resolved':valid[0],
                           'source':'unique-route-clock-and-duration' if clock_confirmed else 'unique-one-edit-in-train-route'}}


def resolve_code_candidates(info, day, cache):
    """Disambiguate an OCR-damaged code using both ordered ticket endpoints."""
    candidates=info.get('train_code_candidates') or []
    if info.get('train_code') or not 1<=len(candidates)<=4:
        return None
    if not info.get('departure_station') or not info.get('arrival_station'):
        return None
    matches=[]
    for code in set(candidates):
        if not isinstance(code,str) or not re.fullmatch(r'[GDCKTZSNLYA]\d{1,4}',code):continue
        result=cache.resolve(code,day,info['departure_station'],info['arrival_station'])
        if result.get('match') in ('exact','nearest'):matches.append(code)
    return matches[0] if len(matches)==1 else None


def enrich_journey(result, historical, evidence, train_code):
    result = dict(result)
    sources = {
        'match': historical.get('match', 'unavailable'),
        'matched_date': historical.get('matched_date'),
        'distance_source': historical.get('distance_source'),
        'duration_source': 'railway-history' if result.get('total_time') is not None else None,
    }
    duration = evidence.get('duration_minutes')
    if (type(duration) is int and 0 < duration <= 10080
            and evidence.get('duration_source') in ('ticket-duration', 'ticket-clocks')):
        result['total_time'] = duration
        sources['duration_source'] = evidence['duration_source']
    elif result.get('total_time') is None:
        distance = result.get('total_mileage')
        if isinstance(distance, (int, float)) and math.isfinite(distance) and distance > 0:
            # Last resort only: an approximate journey duration, never a schedule.
            speed = {'G': 200, 'D': 140, 'C': 100, 'Z': 70, 'T': 70}.get(train_code[:1].upper(), 60)
            result['total_time'] = max(1, round(distance / speed * 60))
            sources.update(duration_source='estimated-distance-speed', assumed_speed_kmh=speed)
    result['sources'] = sources
    return result

