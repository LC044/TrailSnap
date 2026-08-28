from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory
from app.db.models.task import TaskType
from typing import List, Dict
import logging
import json
import aiohttp
from aiohttp import FormData
from sqlalchemy.orm import Session
from app.db.models.task import Task, TaskType
from app.db.models.photo import Photo, FileType
from app.db.models.trip import TrainTicket, FlightTicket
from app.crud import train_ticket as crud_train_tickets
from app.crud import flight_ticket as crud_flight_tickets
from app.schemas.train_ticket import TrainTicketCreate, TrainTicketUpdate
from app.schemas.flight_ticket import FlightTicketCreate, FlightTicketUpdate

from typing import Dict, Any, List
from datetime import datetime
from app.core.config_manager import config_manager
from app.service import storage
import re

logger = logging.getLogger(__name__)

async def get_schedule_info(train_code: str) -> Dict[str, Any]:
    """获取火车站车信息
    {
        "code": 200,
        "msg": "操作成功",
        "data": {
            "total": 0,
            "page": 0,
            "page_size": 0,
            "total_page": 0,
            "list": [
            {
                "schedule_id": 0,
                "train_no": "string",
                "train_code": "string",
                "station_telecode": "string",
                "station_name": "string",
                "sequence": 0,
                "arrive_day_diff": 0,
                "arrival_time": "15:03:23.627Z",
                "departure_time": "15:03:23.627Z",
                "stop_duration": 0,
                "accumulated_mileage": 0,
                "running_time": 0,
                "is_departure": 0,
                "is_arrival": 0
            }
            ]
        }
    }
    """
    url = f"http://127.0.0.1:8000/railway/train-schedules"
    params = {"train_code": train_code}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            if resp.status == 200:
                return await resp.json()
            logger.error(f"Failed to get schedule info for train {train_code}: {resp.status}")
            return None

# 计算车票里程和时间
async def calculate_ticket_mileage_and_time(ticket: TrainTicketCreate) -> Dict[str, Any]:
    """计算车票里程和时间"""
    total_mileage = 0
    total_time = 0
    stop_stations = []
    departure_station = ticket.departure_station
    arrival_station = ticket.arrival_station

    schedule_json = await get_schedule_info(ticket.train_code)
    print(schedule_json)
    if schedule_json and schedule_json.get('code') == 200:
        schedule = schedule_json.get('data', {}).get('list', [])
        # 计算出发站和到达站之间的距离和时间
        departure_index = next((i for i, s in enumerate(schedule) if s['station_name'] == departure_station), None)
        arrival_index = next((i for i, s in enumerate(schedule) if s['station_name'] == arrival_station), None)
        if departure_index is None or arrival_index is None:
            logger.error(f"Departure or arrival station not found in schedule for train {ticket.train_code}")
            return {'total_mileage': 0, 'total_time': 0, 'stop_stations': []}
        for i in range(departure_index, arrival_index):
            total_mileage += schedule[i + 1]['accumulated_mileage'] - schedule[i]['accumulated_mileage']
            total_time += (datetime.strptime(schedule[i + 1]['departure_time'], '%H:%M:%S') -
                           datetime.strptime(schedule[i]['arrival_time'], '%H:%M:%S')).seconds // 60
            stop_stations.append({
                'station_telecode': schedule[i]['station_telecode'],
                'station_name': schedule[i]['station_name'],
                'arrival_time': schedule[i]['arrival_time'],
                'departure_time': schedule[i]['departure_time'],
            })
    return {'total_mileage': total_mileage, 'total_time': total_time, 'stop_stations': stop_stations}

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

            # Generator Mode
            batch_size = 1000
            offset = 0
            generated_count = 0

            while True:
                batch = db.query(Photo).offset(offset).limit(batch_size).all()
                if not batch:
                    break

                tasks_to_create = []
                for p in batch:
                    if p.file_type == FileType.video:
                        continue
                    should_process = False
                    if force:
                        should_process = True
                    else:
                        tasks_status = p.processed_tasks or {}
                        if not tasks_status.get('tickets'):
                            should_process = True
                    if should_process:
                        tasks_to_create.append({
                            'type': TaskType.RECOGNIZE_TICKET,
                            'payload': {'photo_id': str(p.id), 'force': force, 'file_path': p.file_path},
                            'priority': 2,
                            'owner_id': p.owner_id
                        })

                if tasks_to_create:
                    worker.add_tasks(db, tasks_to_create)
                    generated_count += len(tasks_to_create)

                offset += batch_size

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
        from datetime import datetime
        for owner_id, owner_tasks in tasks_by_owner.items():
            try:
                photo_ids = [t.payload['photo_id'] for t in owner_tasks]
                photos = db.query(Photo).filter(Photo.id.in_(photo_ids)).all()
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
                        with open(target_path, 'rb') as f_img:
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

                            for idx, task in enumerate(valid_tasks):
                                photo = valid_photos[idx]
                                res_item = ai_results[idx] if idx < len(ai_results) else {}
                                tickets_data = res_item.get('tickets', [])

                                crud_train_tickets.delete_train_ticket_by_photo_id(db, photo.id)
                                crud_flight_tickets.delete_flight_ticket_by_photo_id(db, photo.id)

                                added_count = 0
                                if tickets_data:
                                    for t_info in tickets_data:
                                        try:
                                            dt_str = t_info.get('datetime')
                                            dt = None
                                            formats = [
                                                "%Y年%m月%d日 %H:%M",
                                                "%Y年%m月%d日%H:%M",
                                                "%Y-%m-%d %H:%M",
                                                "%Y/%m/%d %H:%M",
                                                "%m月%d日 %H:%M",
                                            ]
                                            for fmt in formats:
                                                try:
                                                    dt = datetime.strptime(dt_str, fmt)
                                                    break
                                                except ValueError:
                                                    continue

                                            if dt and dt.year == 1900 and photo.photo_time:
                                                dt = dt.replace(year=photo.photo_time.year)

                                            if not dt:
                                                continue

                                            price_val = 0.0
                                            price_str = str(t_info.get('price', '0')).replace('元', '').replace('￥', '').strip()
                                            try:
                                                price_val = float(price_str)
                                            except:
                                                pass

                                            ticket_type = t_info.get('type', 'train')

                                            if ticket_type == 'flight':
                                                if not t_info.get('flight_code'):
                                                    continue
                                                new_ticket = FlightTicketCreate(
                                                    flight_code=t_info['flight_code'],
                                                    departure_city=t_info.get('departure_city', '未知'),
                                                    arrival_city=t_info.get('arrival_city', '未知'),
                                                    date_time=dt,
                                                    price=price_val,
                                                    name=t_info.get('name') or '未知',
                                                    total_mileage=0,
                                                    total_running_time=0,
                                                    comments=f"自动识别自图片: {photo.filename}",
                                                    photo_id=str(photo.id)
                                                )
                                                ticket = crud_flight_tickets.create_flight_ticket(db, new_ticket, owner_id=photo.owner_id)
                                                if ticket:
                                                    added_count += 1
                                            else:
                                                if not t_info.get('train_code') or not t_info.get('departure_station') or not t_info.get('arrival_station'):
                                                    continue
                                                new_ticket = TrainTicketCreate(
                                                    train_code=t_info['train_code'],
                                                    departure_station=t_info['departure_station'],
                                                    arrival_station=t_info['arrival_station'],
                                                    date_time=dt,
                                                    price=price_val,
                                                    name=t_info.get('name') or '未知',
                                                    carriage=t_info.get('carriage', ''),
                                                    seat_num=t_info.get('seat_num', ''),
                                                    berth_type=t_info.get('berth_type', ''),
                                                    seat_type=t_info.get('seat_type', ''),
                                                    total_mileage=0,
                                                    total_running_time=0,
                                                    stop_stations='[]',
                                                    comments=f"自动识别自图片: {photo.filename}",
                                                    photo_id=str(photo.id)
                                                )
                                                res = await calculate_ticket_mileage_and_time(new_ticket)
                                                new_ticket.total_mileage = res['total_mileage']
                                                new_ticket.total_running_time = res['total_time']
                                                new_ticket.stop_stations = json.dumps(res['stop_stations'])
                                                ticket = crud_train_tickets.create_train_ticket(db, new_ticket, owner_id=photo.owner_id)
                                                if ticket:
                                                    added_count += 1
                                        except Exception as e:
                                            logger.warning(f"Failed to parse ticket data in batch: {e}")
                                            
                                tasks_status = dict(photo.processed_tasks or {})
                                tasks_status['tickets'] = True
                                photo.processed_tasks = tasks_status
                                db.add(photo)
                                db.commit()
                                
                                results.append({
                                    'task_id': task.id,
                                    'task_type': task.type,
                                    'status': 'completed',
                                    'result': {'status': 'success', 'tickets_added': added_count}
                                })
                        else:
                            err_msg = f"AI Service error: {response.status}"
                            for task in valid_tasks:
                                results.append({'task_id': task.id, 'task_type': task.type, 'status': 'failed', 'error': err_msg})
                                
            except Exception as e:
                logger.error(f"Error in Ticket Recognition processing batch for owner {owner_id}: {e}")
                for task in owner_tasks:
                    if not any(r['task_id'] == task.id for r in results):
                        results.append({'task_id': task.id, 'task_type': task.type, 'status': 'failed', 'error': str(e)})
        return results

    async def process_single_photo(self, worker, photo: Photo, db: Session) -> Dict[str, Any]:
        try:
            target_path = storage.get_available_photo_path(photo.owner_id, photo.id, photo.file_path)
            if not target_path:
                return {'status': 'failed', 'error': 'file not found'}
            # 删除photo对应的车票和机票
            crud_train_tickets.delete_train_ticket_by_photo_id(db, photo.id)
            crud_flight_tickets.delete_flight_ticket_by_photo_id(db, photo.id)

            async with aiohttp.ClientSession() as session:
                with open(target_path, 'rb') as f:
                    file_data = f.read()

                import base64
                b64_data = base64.b64encode(file_data).decode('utf-8')
                json_data = {"images": [b64_data]}

                api_url = f"{config_manager.get_user_config(photo.owner_id, db).ai.ai_api_url}/tickets/predict"
                async with session.post(api_url, json=json_data) as response:
                    if response.status == 200:
                        result = await response.json()
                        results = result.get('results', [])
                        tickets_data = results[0].get('tickets', []) if results else []
                        # === Auto-add tickets to database ===
                        if tickets_data:
                            added_count = 0
                            for t_info in tickets_data:
                                try:
                                    # Common parsing for datetime and price
                                    # Parse datetime
                                    dt_str = t_info.get('datetime')
                                    dt = None
                                    # Try standard formats
                                    formats = [
                                        "%Y年%m月%d日 %H:%M",
                                        "%Y年%m月%d日%H:%M",
                                        "%Y-%m-%d %H:%M",
                                        "%Y/%m/%d %H:%M",
                                        "%m月%d日 %H:%M",
                                    ]
                                    for fmt in formats:
                                        try:
                                            dt = datetime.strptime(dt_str, fmt)
                                            break
                                        except ValueError:
                                            continue
                                    # 如果dt_str没有年份""%m月%d日 %H:%M""，默认使用photo.photo_time的年份
                                    if dt and dt.year == 1900:
                                        dt = dt.replace(year=photo.photo_time.year)
                                    
                                    if not dt:
                                        logger.warning(f"Skipping ticket due to invalid datetime: {dt_str}")
                                        continue

                                    # Parse Price
                                    price_val = 0.0
                                    price_str = str(t_info.get('price', '0')).replace('元', '').replace('￥', '').strip()
                                    try:
                                        price_val = float(price_str)
                                    except:
                                        pass

                                    ticket_type = t_info.get('type', 'train')

                                    if ticket_type == 'flight':
                                        # Process Flight Ticket
                                        if not t_info.get('flight_code'):
                                            continue

                                        new_ticket = FlightTicketCreate(
                                            flight_code=t_info['flight_code'],
                                            departure_city=t_info.get('departure_city', '未知'),
                                            arrival_city=t_info.get('arrival_city', '未知'),
                                            date_time=dt,
                                            price=price_val,
                                            name=t_info.get('name') or '未知',
                                            total_mileage=0,
                                            total_running_time=0,
                                            comments=f"自动识别自图片: {photo.filename}",
                                            photo_id=str(photo.id)
                                        )
                                        # Create Ticket
                                        ticket = crud_flight_tickets.create_flight_ticket(db, new_ticket, owner_id=photo.owner_id)
                                        if not ticket:
                                            continue
                                        t_info['saved_id'] = ticket.id
                                        added_count += 1
                                    else:
                                        # Process Train Ticket
                                        if not t_info.get('train_code') or not t_info.get('departure_station') or not t_info.get('arrival_station'):
                                            continue
                                            
                                        new_ticket = TrainTicketCreate(
                                            train_code=t_info['train_code'],
                                            departure_station=t_info['departure_station'],
                                            arrival_station=t_info['arrival_station'],
                                            date_time=dt,
                                            price=price_val,
                                            name=t_info.get('name') or '未知',
                                            seat_type=t_info.get('seat_type', '未知'),
                                            total_mileage=0,
                                            total_running_time=0,
                                            stop_stations="[]",
                                            comments=f"自动识别自图片: {photo.filename}",
                                            photo_id=str(photo.id)
                                        )

                                        res = await calculate_ticket_mileage_and_time(new_ticket)
                                        new_ticket.total_mileage = res['total_mileage']
                                        new_ticket.total_running_time = res['total_time']
                                        new_ticket.stop_stations = json.dumps(res['stop_stations'])

                                        ticket = crud_train_tickets.create_train_ticket(db, new_ticket, owner_id=photo.owner_id)
                                        if not ticket:
                                            continue
                                        t_info['saved_id'] = ticket.id
                                        added_count += 1

                                except Exception as e:
                                    logger.warning(f"Failed to parse ticket data: {e}")
                            
                            if added_count > 0:
                                logger.info(f"Successfully added {added_count} tickets from photo {photo.id}")

                        # Update processed status
                        tasks_status = dict(photo.processed_tasks or {})
                        tasks_status['tickets'] = True
                        photo.processed_tasks = tasks_status
                        db.add(photo)
                        db.commit()
                        return {'status': 'success', 'tickets_added': added_count if 'added_count' in locals() else 0}
                    else:
                        text = await response.text()
                        logger.error(f"AI Service error: {response.status} {text}")
                        return {'status': 'failed', 'error': f"AI Service error: {response.status}"}

        except Exception as e:
            logger.error(f"Error processing Tickets for photo {photo.id}: {e}")
            tasks_status = dict(photo.processed_tasks or {})
            tasks_status['tickets'] = False
            photo.processed_tasks = tasks_status
            db.add(photo)
            db.commit()
            raise e

    def release_resources(self) -> None:
        pass
