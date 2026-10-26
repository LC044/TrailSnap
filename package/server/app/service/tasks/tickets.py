from app.service.tasks.photo_generator import generate_photo_tasks
from app.service.ai_model_state import ai_response_error
from app.service.disk_budget import disk_budget
from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory
from app.db.models.task import DEFAULT_PRIORITIES
import logging
import json
import aiohttp
from sqlalchemy.orm import Session
from app.db.models.task import Task, TaskType
from app.db.models.photo import Photo
from app.crud import train_ticket as crud_train_tickets
from app.crud import flight_ticket as crud_flight_tickets
from app.schemas.train_ticket import TrainTicketCreate
from app.schemas.flight_ticket import FlightTicketCreate

from typing import Dict, Any, List
from datetime import datetime
from app.core.config_manager import config_manager
from app.service import storage
import asyncio

logger = logging.getLogger(__name__)

async def get_schedule_info(train_code: str, day=None, departure=None, arrival=None) -> Dict[str, Any]:
    """Use the same date-aware offline history as the public railway API."""
    def query_history():
        from railway.history_cache import HistoryCache
        return HistoryCache().resolve(train_code, day or datetime.now().date(), departure, arrival)
    return await asyncio.to_thread(query_history)


async def get_endpoint_distance(ticket):
    def distance():
        from railway.history_cache import HistoryCache
        return HistoryCache().distance(ticket.departure_station,ticket.arrival_station,str(ticket.date_time.date()))
    return await asyncio.to_thread(distance)


async def calculate_ticket_mileage_and_time(ticket: TrainTicketCreate, evidence=None) -> Dict[str, Any]:
    historical = {}
    corrections = {}
    try:
        if evidence is not None:
            def repair():
                from railway.history_seed import station_metadata
                from railway.history_cache import HistoryCache
                from app.service.ticket_journey import repair_station_names
                known = {name for s in station_metadata().values() for name in s['names']}
                if ticket.departure_station in known and ticket.arrival_station in known:
                    return {}
                return repair_station_names(ticket, HistoryCache(), evidence)
            corrections = await asyncio.to_thread(repair)
            for key, value in corrections.items():
                setattr(ticket, key, value['resolved'])
        historical = await get_schedule_info(ticket.train_code, getattr(ticket, 'date_time', None),
                                            ticket.departure_station, ticket.arrival_station)
        if evidence is not None and historical.get('distance_km') is None:
            distance=await get_endpoint_distance(ticket)
            if distance is not None:
                historical=dict(historical,distance_km=distance,distance_source='gps-endpoints-haversine-x1.2')
        result = {
            'total_mileage': historical['distance_km'],
            'total_time': historical['duration_minutes'],
            'stop_stations': [dict(station_telecode=s['c'], station_name=s['n'],
                                   arrival_time=s['a'], departure_time=s['d'])
                              for s in historical['stops']],
        }
    except Exception as exc:
        logger.warning('Historical railway lookup unavailable: %s', exc)
        result = {'total_mileage': None, 'total_time': None, 'stop_stations': []}
    if evidence is not None:
        from app.service.ticket_journey import enrich_journey
        result = enrich_journey(result, historical, evidence, ticket.train_code)
        if corrections:
            result['sources']['station_corrections'] = corrections
    return result

@TaskStrategyFactory.register(TaskType.RECOGNIZE_TICKET)
class RecognizeTicketStrategy(BaseTaskStrategy):
    @property
    def task_category(self) -> str:
        return 'AI'

    @property
    def resource_key(self) -> str:
        return 'tickets'

    async def process(self, worker, task: Task, db: Session) -> Dict[str, Any]:
        try:
            force = task.payload.get('force', False)

            if task.payload and 'photo_id' in task.payload:
                photo_id = task.payload['photo_id']
                photo = db.query(Photo).filter(Photo.id == photo_id).first()
                if not photo:
                    return {'status': 'skipped', 'reason': 'photo not found'}

                if not force:
                    tasks_status = photo.processed_tasks or {}
                    if tasks_status.get('tickets'):
                         return {'status': 'skipped', 'reason': 'already processed'}

                return await self.process_single_photo(worker, photo, db)

            generated_count = generate_photo_tasks(
                db, worker, task, task_type=TaskType.RECOGNIZE_TICKET,
                status_key='tickets', priority=DEFAULT_PRIORITIES[TaskType.RECOGNIZE_TICKET],
            )

            return {
                'processed': 0,
                'generated_tasks': generated_count,
                'message': f'Generated {generated_count} ticket recognition tasks'
            }

        except Exception as e:
            logger.error(f"Ticket task failed: {e}")
            raise e


    async def process_batch(self, worker, tasks: List[Task], db: Session) -> List[Dict]:
        results = []
        generator_tasks = []
        photo_tasks = []
        for task in tasks:
            if task.payload and 'photo_id' in task.payload:
                photo_tasks.append(task)
            else:
                generator_tasks.append(task)

        for task in generator_tasks:
            try:
                res = await self.process(worker, task, db)
                results.append({
                    'task_id': task.id,
                    'task_type': task.type,
                    'status': 'failed' if res and isinstance(res, dict) and res.get('status') == 'failed' else 'completed',
                    'result': res,
                    'error': res.get('error') if res and isinstance(res, dict) else None
                })
            except Exception as e:
                logger.error(f"Error processing generator task {task.id}: {e}")
                results.append({
                    'task_id': task.id,
                    'task_type': task.type,
                    'status': 'failed',
                    'error': str(e)
                })

        if not photo_tasks:
            return results

        tasks_by_owner = {}
        for task in photo_tasks:
            owner_id = task.owner_id
            if owner_id not in tasks_by_owner:
                tasks_by_owner[owner_id] = []
            tasks_by_owner[owner_id].append(task)

        import base64
        for owner_id, owner_tasks in tasks_by_owner.items():
            try:
                photo_ids = [t.payload['photo_id'] for t in owner_tasks]
                photos = db.query(Photo).filter(
                    Photo.id.in_(photo_ids), Photo.owner_id == owner_id, Photo.is_deleted.is_(False)
                ).all()
                photo_map = {str(p.id): p for p in photos}
                
                valid_tasks = []
                b64_images = []
                valid_photos = []
                
                for task in owner_tasks:
                    photo_id = str(task.payload['photo_id'])
                    photo = photo_map.get(photo_id)

                    if not photo:
                        results.append({'task_id': task.id, 'task_type': task.type, 'status': 'completed', 'result': {'status': 'skipped', 'reason': 'photo not found'}})
                        continue

                    target_path = storage.get_available_photo_path(photo.owner_id, photo.id, photo.file_path)
                    if not target_path:
                        results.append({'task_id': task.id, 'task_type': task.type, 'status': 'failed', 'error': 'file not found'})
                        continue

                    try:
                        with disk_budget.slot(target_path), open(target_path, 'rb') as f_img:
                            b64_data = base64.b64encode(f_img.read()).decode('utf-8')
                        b64_images.append(b64_data)
                        valid_tasks.append(task)
                        valid_photos.append(photo)
                    except Exception as e:
                        results.append({'task_id': task.id, 'task_type': task.type, 'status': 'failed', 'error': f'read file error: {e}'})

                if not valid_tasks:
                    continue

                api_url = f"{config_manager.get_user_config(owner_id, db).ai.ai_api_url}/tickets/predict"
                async with aiohttp.ClientSession() as session:
                    async with session.post(api_url, json={"images": b64_images}) as response:
                        if response.status == 200:
                            result_data = await response.json()
                            ai_results = result_data.get('results', [])
                            if not isinstance(ai_results, list):
                                raise ValueError('识别服务返回的结果格式无效，请重试')

                            for idx, task in enumerate(valid_tasks):
                                photo = valid_photos[idx]
                                res_item = ai_results[idx] if idx < len(ai_results) else None
                                result = await self.save_recognition_result(photo, res_item, db)
                                results.append({
                                    'task_id': task.id, 'task_type': task.type,
                                    'status': 'failed' if result['status'] == 'failed' else 'completed',
                                    'result': result, 'error': result.get('error'),
                                })
                        else:
                            err_msg = await ai_response_error(response)
                            for task in valid_tasks:
                                results.append({'task_id': task.id, 'task_type': task.type, 'status': 'failed', 'error': err_msg})
                                
            except Exception as e:
                db.rollback()
                logger.error(f"Error in Ticket Recognition processing batch for owner {owner_id}: {e}")
                for task in owner_tasks:
                    if not any(r['task_id'] == task.id for r in results):
                        results.append({'task_id': task.id, 'task_type': task.type, 'status': 'failed', 'error': str(e)})
        return results

    async def save_recognition_result(self, photo: Photo, result: Any, db: Session) -> Dict[str, Any]:
        """Validate before writing; a photo's tickets and completion flag commit together.

        Re-recognition is additive: never delete existing tickets or their album links.
        A duplicate counts as already saved, rather than a failed insert.
        """
        try:
            if not isinstance(result, dict) or not isinstance(result.get('tickets'), list):
                raise ValueError('识别服务返回的票据结果缺失或格式无效，请重试')
            if result.get('error'):
                raise ValueError('票据识别失败：' + str(result['error']))
            prepared = []
            for info in result['tickets']:
                if not isinstance(info, dict):
                    raise ValueError('识别服务返回了无效票据')
                dt_str = info.get('datetime')
                from app.service.ticket_journey import parse_ticket_datetime
                dt,inferred_year=parse_ticket_datetime(dt_str,getattr(photo,'photo_time',None))
                inferred_year = inferred_year or str(info.get('year_source') or '').startswith('inferred')
                price = str(info.get('price') or '0').replace('元', '').replace('￥', '').replace('¥', '').strip()
                common = dict(date_time=dt, price=price, name=info.get('name') or '未知',
                              total_mileage=0, total_running_time=0,
                              comments=f"自动识别自图片: {photo.filename}", photo_id=str(photo.id))
                kind = info.get('type') or 'train'
                code_correction = None
                if kind=='train' and not info.get('train_code') and info.get('train_code_candidates'):
                    def resolve_code():
                        from railway.history_cache import HistoryCache
                        from app.service.ticket_journey import resolve_code_candidates
                        return resolve_code_candidates(info,dt,HistoryCache())
                    resolved_code=await asyncio.to_thread(resolve_code)
                    if resolved_code:
                        code_correction={'original':info.get('train_code_raw'),'resolved':resolved_code,
                                         'source':'unique-code-candidate-in-ordered-route'}
                        info=dict(info,train_code=resolved_code)
                required = ('flight_code',) if kind == 'flight' else ('train_code', 'departure_station', 'arrival_station')
                if kind not in ('train', 'flight') or any(not info.get(key) for key in required):
                    raise ValueError('票据关键字段不完整，请重试或手动添加')
                if kind=='train' and any(word in info[key] for key in ('departure_station','arrival_station')
                                         for word in ('去看看','时刻表','其他问题','年月日')):
                    raise ValueError('车站字段包含界面文字或日期碎片，请重试或手动核对')
                if kind=='train' and info['departure_station'].strip().removesuffix('站')==info['arrival_station'].strip().removesuffix('站'):
                    raise ValueError('出发站和到达站重复，请重试或手动核对')
                journey_sources = None
                if kind == 'flight':
                    ticket = FlightTicketCreate(
                        flight_code=info['flight_code'], departure_city=info.get('departure_city') or '未知',
                        arrival_city=info.get('arrival_city') or '未知', **common)
                else:
                    ticket = TrainTicketCreate(
                        train_code=info['train_code'], departure_station=info['departure_station'],
                        arrival_station=info['arrival_station'], carriage=info.get('carriage') or '',
                        seat_num=info.get('seat_num') or '无座', berth_type=info.get('berth_type') or '无',
                        seat_type=info.get('seat_type') or '未知', stop_stations='[]', **common)
                    try:
                        extra = await calculate_ticket_mileage_and_time(ticket, evidence=info)
                        ticket.total_mileage = extra['total_mileage']
                        ticket.total_running_time = extra['total_time']
                        ticket.stop_stations = json.dumps(extra['stop_stations'])
                        journey_sources = extra.get('sources')
                        if code_correction and journey_sources:
                            journey_sources['train_code_correction']=code_correction
                        if journey_sources:
                            notes=[]
                            if journey_sources.get('distance_source') in ('gps-haversine-x1.2','gps-endpoints-haversine-x1.2'):
                                notes.append('里程按车站坐标估算')
                            if journey_sources.get('duration_source') == 'estimated-distance-speed':
                                notes.append('时长按里程及车次类型速度估算')
                            if notes:
                                ticket.comments += '；' + '；'.join(notes)
                    except Exception as exc:
                        logger.warning('Optional railway enrichment failed: %s', exc)
                prepared.append((kind, ticket, inferred_year, journey_sources))

            added = existing = 0
            time_sources = dict((photo.processed_tasks or {}).get('ticket_time_sources') or {})
            all_journey_sources = dict((photo.processed_tasks or {}).get('ticket_journey_sources') or {})
            for kind, ticket, inferred_year, journey_sources in prepared:
                create = (crud_flight_tickets.create_flight_ticket if kind == 'flight'
                          else crud_train_tickets.create_train_ticket)
                saved = create(db, ticket, owner_id=photo.owner_id, commit=False)
                if saved is None:
                    existing += 1
                else:
                    added += 1
                    if inferred_year:
                        time_sources[f'{kind}:{saved.id}'] = 'inferred_year'
                    if journey_sources:
                        all_journey_sources[f'{kind}:{saved.id}'] = journey_sources
            photo.processed_tasks = dict(photo.processed_tasks or {}, tickets=True, tickets_version=2)
            if time_sources:
                photo.processed_tasks = dict(photo.processed_tasks, ticket_time_sources=time_sources)
            if all_journey_sources:
                photo.processed_tasks = dict(photo.processed_tasks, ticket_journey_sources=all_journey_sources)
            db.add(photo)
            db.commit()
            return {'status': 'success' if prepared else 'no_tickets',
                    'tickets_added': added, 'tickets_existing': existing}
        except Exception as exc:
            db.rollback()
            logger.warning('Ticket recognition/save failed for photo %s: %s', photo.id, exc)
            try:
                photo.processed_tasks = dict(photo.processed_tasks or {}, tickets=False)
                db.add(photo)
                db.commit()
            except Exception:
                db.rollback()
                logger.exception('Could not reset ticket processing flag')
            return {'status': 'failed', 'error': f'票据识别或保存失败：{exc}'}

    async def process_single_photo(self, worker, photo: Photo, db: Session) -> Dict[str, Any]:
        try:
            target_path = storage.get_available_photo_path(photo.owner_id, photo.id, photo.file_path)
            if not target_path:
                return {'status': 'failed', 'error': 'file not found'}
            import base64
            with disk_budget.slot(target_path), open(target_path, 'rb') as file:
                image = base64.b64encode(file.read()).decode('utf-8')
            api_url = f"{config_manager.get_user_config(photo.owner_id, db).ai.ai_api_url}/tickets/predict"
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json={'images': [image]}) as response:
                    if response.status != 200:
                        return {'status': 'failed', 'error': await ai_response_error(response)}
                    body = await response.json()
                    results = body.get('results', [])
                    return await self.save_recognition_result(photo, results[0] if results else None, db)
        except Exception as exc:
            db.rollback()
            logger.warning('Error processing tickets for photo %s: %s', photo.id, exc)
            return {'status': 'failed', 'error': str(exc)}

    def release_resources(self) -> None:
        pass
