"""Station coordinates and conservative Tianditu POI matching; never log credentials."""
import json
import logging
import math
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

logger=logging.getLogger(__name__)


def valid_coordinates(latitude,longitude):
    try:
        latitude,longitude=float(latitude),float(longitude)
        if all(map(math.isfinite,(latitude,longitude))) and -90<=latitude<=90 and -180<=longitude<=180 and (latitude,longitude)!=(0,0):
            return latitude,longitude
    except (TypeError,ValueError):
        pass
    return None


def station_keyword(name):
    return re.sub(r'(铁路车站|火车站|高铁站|站)$','',re.sub(r'\s+','',name or ''))


def read_feed_coordinates(value):
    versions=value.get('versions') or []
    if not versions:return None
    data=versions[-1]['data'];gps=data.get('gps') or {}
    coordinates=valid_coordinates(gps.get('latitude'),gps.get('longitude',gps.get('longitute')))
    if coordinates:
        return (*coordinates,data.get('coordinate_system') or 'unknown')
    return None


def configured_tianditu_keys():
    explicit=os.getenv('RAILWAY_TIANDITU_KEY','').strip()
    if explicit:return [explicit]
    from app.db.session import SessionLocal
    from app.db.models.user import User
    from app.core.config_manager import config_manager
    with SessionLocal() as db:
        for admin in db.query(User).filter(User.is_superuser.is_(True),User.is_active.is_(True)).order_by(User.id).all():
            config=config_manager.get_user_config(admin.id,db)
            if config.map.provider=='tianditu':
                keys=[key.strip() for key in config.map.api_keys if key.strip()]
                if keys:return keys
    return []


class TiandituStationGeocoder:
    def __init__(self,keys,request=None):
        self.keys=list(dict.fromkeys(keys));self.request=request or requests.get

    def lookup(self,name,city='',province=''):
        if not self.keys:return {'status':'no_key'}
        suffix='' if name.endswith('站') else '站'
        keyword=' '.join(part for part in (province,city,name+suffix) if part)
        # Ordinary POI search, documented by the official server/search2 API.
        query={'keyWord':keyword,'queryType':1,'level':12,'mapBound':'73,18,135,54','start':0,'count':20}
        try:
            response=self.request('https://api.tianditu.gov.cn/v2/search',
                params={'postStr':json.dumps(query,ensure_ascii=False,separators=(',',':')),'type':'query','tk':self.keys[0]},
                headers={'User-Agent':'TrailSnap-Railway/1.0'},timeout=(3,7))
            if response.status_code==429:return {'status':'rate_limited'}
            if response.status_code in (401,403):return {'status':'invalid_key'}
            if not response.ok:return {'status':'error'}
            payload=response.json()
        except (requests.RequestException,ValueError):
            return {'status':'error'}
        if not isinstance(payload,dict):return {'status':'error'}
        status=payload.get('status') or {}
        if isinstance(status,dict):
            info=str(status.get('infocode','1000'));message=str(status.get('cndesc',''))
            if any(term in message.lower() for term in ('quota','配额','限额','频率')):return {'status':'rate_limited'}
            if info not in ('1000','3001'):return {'status':'invalid_key' if 'key' in message.lower() or '密钥' in message else 'error'}
        matches=[]
        for poi in payload.get('pois') or []:
            if not isinstance(poi,dict):continue
            if station_keyword(poi.get('name')) != station_keyword(name):continue
            # Reject named shops/entrances, unrelated city matches and administrative centers.
            returned_city=poi.get('city') or poi.get('cityName') or ''
            if city and returned_city and city.removesuffix('市') not in returned_city:continue
            if city and not returned_city and city.removesuffix('市') not in str(poi.get('address','')):continue
            try:longitude,latitude=poi.get('lonlat','').split(',')
            except (ValueError,AttributeError):continue
            coordinates=valid_coordinates(latitude,longitude)
            if coordinates:matches.append(coordinates)
        unique={(round(lat,4),round(lng,4)) for lat,lng in matches}
        if len(unique)!=1:return {'status':'ambiguous' if unique else 'not_found'}
        latitude,longitude=matches[0]
        return {'status':'ready','latitude':latitude,'longitude':longitude,'source':'tianditu','system':'CGCS2000'}


def sync_coordinate_cache(cache,rows):
    with cache.connect() as connection:
        for row in rows:
            coordinates=valid_coordinates(row.latitude,row.longitude)
            if coordinates:
                cache.store_coordinates(row.telecode,*coordinates,row.coordinate_source or 'local',
                                        row.coordinate_system or 'unknown',row.coordinates_updated_at,
                                        connection=connection)


def backfill_missing_coordinates(*,sessions=None,cache=None,geocoder=None,limit=None,budget_seconds=45,sleep=time.sleep):
    from railway.db.models.models import Station
    from railway.history_cache import HistoryCache
    if sessions is None:
        from railway.db.session import SessionLocal
        sessions=SessionLocal
    cache=cache or HistoryCache()
    geocoder=geocoder or TiandituStationGeocoder(configured_tianditu_keys())
    if not geocoder.keys:return {'status':'no_key','looked_up':0,'updated':0}
    limit=limit if limit is not None else int(os.getenv('RAILWAY_COORDINATE_BATCH_SIZE','50'))
    now=datetime.now(timezone.utc);deadline=time.monotonic()+budget_seconds
    counts={'status':'complete','looked_up':0,'updated':0}
    with sessions() as db:
        # Repairs a cache write interrupted after the station transaction committed.
        sync_coordinate_cache(cache,db.query(Station).filter(Station.latitude.isnot(None),Station.longitude.isnot(None)).all())
        # Fetch a bounded ordered batch; invalid/out-of-range coordinates count as missing.
        rows=db.query(Station).filter(
            ((Station.latitude.is_(None)) | (Station.longitude.is_(None)) |
             (Station.latitude < -90) | (Station.latitude > 90) |
             (Station.longitude < -180) | (Station.longitude > 180) |
             ((Station.latitude==0) & (Station.longitude==0))),
            ((Station.coordinate_retry_after.is_(None)) | (Station.coordinate_retry_after<=now)),
        ).order_by(Station.coordinate_lookup_at.asc().nullsfirst(),Station.telecode).limit(max(1,min(limit,1000))).all()
        for row in rows:
            if time.monotonic()>=deadline:counts['status']='budget_exhausted';break
            result=geocoder.lookup(row.station_name,row.city or '',row.province or '')
            counts['looked_up']+=1
            db.refresh(row)
            if valid_coordinates(row.latitude,row.longitude):
                sync_coordinate_cache(cache,[row])
                continue
            row.coordinate_lookup_at=now;row.coordinate_status=result['status']
            if result['status']=='ready':
                row.latitude=result['latitude'];row.longitude=result['longitude']
                row.coordinate_source=result['source'];row.coordinate_system=result['system']
                row.coordinates_updated_at=now;row.coordinate_retry_after=None
                counts['updated']+=1
            else:
                retry_days=7 if result['status'] in ('not_found','ambiguous') else 1
                row.coordinate_retry_after=now+timedelta(days=retry_days)
            db.commit()
            sync_coordinate_cache(cache,[row])
            if result['status'] in ('rate_limited','invalid_key'):
                counts['status']=result['status'];break
            sleep(0.25)
    return counts
