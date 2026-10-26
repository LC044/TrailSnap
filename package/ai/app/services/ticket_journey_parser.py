"""Read elapsed time from the ticket card, without using the phone's clock."""
import re


def apply_shared_ticket_date(texts, tickets):
    """A single explicit page date may apply to several visible ticket cards."""
    dates = set()
    codes = {m[0] for text in texts for m in re.finditer(r'(?<![A-Za-z0-9])[GDCKTZSNLYA]\d{1,4}(?![A-Za-z0-9])',text)}
    for text in texts:
        match=re.match(r'^\s*(?:乘车日期[:：]\s*)?((?:\d{4}年)?\d{1,2}月\d{1,2}日)',text)
        if match:dates.add(match[1])
    if len(dates)!=1 or any(not t.get('train_code') or t['train_code'] not in codes for t in tickets):
        return
    date=next(iter(dates))
    for ticket in tickets:
        if re.fullmatch(r'\d{1,2}:\d{2}',ticket.get('datetime') or ''):
            ticket['datetime']=date+' '+ticket['datetime']
            ticket['date_source']='shared-ticket-header'


def apply_section_ticket_dates(texts,polys,tickets):
    headers=[]
    for text,poly in zip(texts,polys):
        match=re.match(r'^乘车日期[:：]\s*((?:\d{4}年)?\d{1,2}月\d{1,2}日)',text.strip())
        point=_center(poly)
        if match and point:headers.append((point[1],match[1]))
    for ticket in tickets:
        clock=ticket.get('datetime') or ''
        if not re.fullmatch(r'\d{1,2}:\d{2}',clock):continue
        anchors=[_center(poly) for text,poly in zip(texts,polys)
                 if re.search(r'(?<!\d)'+re.escape(clock)+r'(?!\d)',text)]
        anchors=[p for p in anchors if p]
        if len(anchors)!=1:continue
        preceding=[h for h in headers if h[0]<=anchors[0][1]]
        if preceding:
            ticket['datetime']=max(preceding)[1]+' '+clock
            ticket['date_source']='ticket-section-header'


def _center(poly):
    if poly is None or len(poly) < 4:
        return None
    return (sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly))


def extract_journey_time(texts, polys, ticket):
    """Return ticket evidence only. Never estimate a timetable inside OCR."""
    code = ticket.get('train_code') or ''
    anchors = [_center(p) for text, p in zip(texts, polys) if code and code in text]
    anchors = [p for p in anchors if p]
    durations = []
    for text, poly in zip(texts, polys):
        if re.search(r'换乘|中转|提前|停止|检票|退票|候车|免费|\d[年月日]', text):
            continue
        match = re.search(r'(?<![A-Za-z0-9:：])(?:(\d{1,2})\s*天\s*)?(\d{1,3})\s*(?:小时|时(?![刻间])|h(?![A-Za-z]))\s*(?:(\d{1,2})\s*(?:分钟|分|m(?![A-Za-z])))?', text, re.I)
        duration_text = re.sub(r'^' + re.escape(code) + r'[·\s:：-]*', '', text.strip()) if code else text.strip()
        minute_only = re.fullmatch(r'(?:历时|耗时|全程)?\s*(\d{1,3})\s*(?:分钟|分)', duration_text)
        if not match and not minute_only:
            continue
        elapsed = int(match[1] or 0) * 1440 + int(match[2]) * 60 + int(match[3] or 0) if match else int(minute_only[1])
        if not 0 < elapsed <= 10080 or (match and int(match[3] or 0) >= 60):
            continue
        point = _center(poly)
        if point and anchors:
            distance = min(abs(point[1] - p[1]) + abs(point[0] - p[0]) * .2 for p in anchors)
        else:
            distance = 0
        durations.append((distance, elapsed))
    if durations:
        durations.sort()
        if len(durations) == 1 or durations[0][0] < durations[1][0]:
            return {'duration_minutes': durations[0][1], 'duration_source': 'ticket-duration'}

    for text in texts:
        pair=re.search(r'(?<!\d)(\d{1,2})[:：](\d{2})\s*至\s*(\d{1,2})[:：](\d{2})(?!\d)',text)
        if pair and int(pair[1])<24 and int(pair[3])<24 and int(pair[2])<60 and int(pair[4])<60:
            elapsed=(int(pair[3])*60+int(pair[4])-int(pair[1])*60-int(pair[2]))%1440
            if elapsed:return {'duration_minutes':elapsed,'duration_source':'ticket-clocks'}

    # Two clocks in the route row, close to the resolved stations, exclude status bars.
    stations = []
    for key in ('departure_station', 'arrival_station'):
        name = ticket.get(key)
        candidates = [_center(p) for t, p in zip(texts, polys)
                      if name and re.sub(r'^[^\u4e00-\u9fa5]+|[^\u4e00-\u9fa5]+$', '', t.strip()).removesuffix('站') == name]
        candidates = [p for p in candidates if p]
        if len(candidates) != 1:
            return {}
        stations.append(candidates[0])
    clocks = []
    for text, poly in zip(texts, polys):
        match = re.fullmatch(r'\s*(\d{1,2})[:：](\d{2})\s*(?:[+＋]\s*\d\s*(?:天|日)?)?\s*', text)
        if not match and any(ticket.get(k) and ticket[k] in text for k in ('departure_station','arrival_station')):
            match = re.search(r'(?<!\d)(\d{1,2})[:：](\d{2})(?!\d)', text)
        point = _center(poly)
        if match and point and int(match[1]) < 24 and int(match[2]) < 60:
            clocks.append((point, int(match[1]) * 60 + int(match[2]), text))
    selected = []
    for x, y in stations:
        nearby = [(abs(point[1] - y) + abs(point[0] - x), minute, text, point)
                  for point, minute, text in clocks
                  if abs(point[0] - x) <= 120 and abs(point[1] - y) <= 180]
        if not nearby:
            return {}
        selected.append(min(nearby))
    if selected[0][3] == selected[1][3]:
        return {}
    start, end = selected
    # Only a same-row pair represents the departure/arrival clocks of this card.
    vertical = abs(stations[0][0] - stations[1][0]) < 40 and abs(stations[0][1] - stations[1][1]) > 25
    if not vertical and abs(start[3][1] - end[3][1]) > 40:
        return {}
    day_match = re.search(r'[+＋]\s*(\d)\s*(?:天|日)?', end[2])
    days = int(day_match[1]) if day_match else 0
    if not day_match:
        for text,poly in zip(texts,polys):
            marker=re.fullmatch(r'\s*[+＋]\s*(\d)\s*(?:天|日)?\s*',text)
            point=_center(poly)
            if marker and point and abs(point[0]-end[3][0])<=80 and abs(point[1]-end[3][1])<=60:
                days=int(marker[1]);day_match=marker
                break
    elapsed = end[1] - start[1] + days * 1440
    if elapsed < 0 and not day_match:
        elapsed += 1440
    if elapsed > 0:
        return {'duration_minutes': elapsed, 'duration_source': 'ticket-clocks'}
    return {}
