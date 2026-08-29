import traceback
from uuid import UUID

from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory
from app.db.models.task import TaskType, TaskStatus, DEFAULT_PRIORITIES
from typing import List, Dict, Optional
import logging
import aiohttp
from aiohttp import FormData
from sqlalchemy.orm import Session
from app.db.models.task import Task, TaskType, DEFAULT_PRIORITIES
from app.db.models.photo import Photo, FileType
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.db.models.image_vector import ImageVector
from typing import Dict, Any, List
from app.core.config_manager import config_manager
from app.crud import tag as crud_tag

from app.service import storage

logger = logging.getLogger(__name__)

_tag_cache: Dict[str, str] = {}


def get_tag_id(db: Session, tag_name: str, owner_id: Optional[UUID] = None) -> str:
    if tag_name in _tag_cache:
        return _tag_cache[tag_name]
    else:
        tag = crud_tag.get_tag_by_name(db, tag_name, owner_id)
        if not tag:
            tag = PhotoTag(tag_name=tag_name, type='yolo', owner_id=owner_id)
            db.add(tag)
            db.commit()
            db.refresh(tag)
        _tag_cache[tag_name] = str(tag.id)
        return str(tag.id)


@TaskStrategyFactory.register(TaskType.CLASSIFY_IMAGE)
class ClassifyImageStrategy(BaseTaskStrategy):
    @property
    def task_category(self) -> str:
        return 'AI'

    @property
    def resource_key(self) -> str:
        return 'classification'

    async def process(self, worker, task: Task, db: Session) -> Dict[str, Any]:
        try:
            force = task.payload.get('force', False)

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
                    should_process = False
                    if force:
                        should_process = True
                    else:
                        tasks_status = p.processed_tasks or {}
                        if not tasks_status.get('classification'):
                            should_process = True
                    if should_process:
                        tasks_to_create.append({
                            'type': TaskType.CLASSIFY_IMAGE,
                            'payload': {'photo_id': str(p.id), 'force': force, 'file_path': p.file_path},
                            'priority': DEFAULT_PRIORITIES[TaskType.CLASSIFY_IMAGE],
                            'owner_id': p.owner_id
                        })
                if tasks_to_create:
                    worker.add_tasks(db, tasks_to_create)
                    generated_count += len(tasks_to_create)
                offset += batch_size
            return {
                'processed': 0,
                'generated_tasks': generated_count,
                'message': f'Generated {generated_count} classification tasks'
            }

        except Exception as e:
            logger.error(f"Classification task failed: {e}")
            raise e


    async def process_batch(self, worker, tasks: List[Task], db: Session) -> List[Dict]:
        results = []
        generator_tasks = [t for t in tasks if not (t.payload and 'photo_id' in t.payload)]
        photo_tasks = [t for t in tasks if t.payload and 'photo_id' in t.payload]
        # logger.info(f"tasks num: {len(photo_tasks)}")
        if generator_tasks:
            results.extend(await self._process_generator_tasks(worker, generator_tasks, db))

        if not photo_tasks:
            return results

        tasks_by_owner = {}
        for task in photo_tasks:
            tasks_by_owner.setdefault(task.owner_id, []).append(task)

        for owner_id, owner_tasks in tasks_by_owner.items():
            results.extend(await self._process_owner_batch(owner_id, owner_tasks, db))

        return results

    async def _process_generator_tasks(self, worker, tasks: List[Task], db: Session) -> List[Dict]:
        results = []
        for task in tasks:
            try:
                res = await self.process(worker, task, db)
                status = 'failed' if res and isinstance(res, dict) and res.get('status') == 'failed' else 'completed'
                results.append({
                    'task_id': task.id,
                    'task_type': task.type,
                    'status': status,
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
        return results

    async def _process_owner_batch(self, owner_id: int, tasks: List[Task], db: Session) -> List[Dict]:
        import base64
        results = []
        try:
            photo_ids = [t.payload['photo_id'] for t in tasks]
            crud_tag.remove_tags_from_photo(db, photo_ids, ai_generated=True)
            photos = db.query(Photo).filter(Photo.id.in_(photo_ids)).all()
            photo_map = {str(p.id): p for p in photos}

            valid_tasks = []
            valid_photos = []
            b64_images = []

            for task in tasks:
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
                return results
            # logger.info(f"valid tasks num: {len(valid_tasks)}")
            api_url = f"{config_manager.get_user_config(owner_id, db).ai.ai_api_url}/classification/"
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json={"images": b64_images}) as resp:
                    if resp.status == 200:
                        result_data = await resp.json()
                        ai_results = result_data.get('results', [])
                        ai_batch_results = await self._process_ai_results(valid_tasks, valid_photos, ai_results, photo_ids, db)
                        results.extend(ai_batch_results)
                    else:
                        err_msg = f"AI Service error: {resp.status}"
                        for task in valid_tasks:
                            results.append({'task_id': task.id, 'task_type': task.type, 'status': 'failed', 'error': err_msg})

        except Exception as e:
            logger.error(f"Error in Classification processing batch for owner {owner_id}: {e}")
            logger.error(traceback.format_exc())
            for task in tasks:
                if not any(r['task_id'] == task.id for r in results):
                    results.append({'task_id': task.id, 'task_type': task.type, 'status': 'failed', 'error': str(e)})

        return results

    async def _process_ai_results(self, valid_tasks: List[Task], valid_photos: List[Photo], ai_results: List[Dict], photo_ids: List[str], db: Session) -> List[Dict]:
        results = []
        photos_to_ticket = []
        photo_tag_data = []

        for idx, task in enumerate(valid_tasks):
            photo = valid_photos[idx]
            res_item = ai_results[idx] if idx < len(ai_results) else {}
            predictions = res_item.get('predictions', []) if res_item.get('status') == 'success' else []
            selected_tag = None

            for res in predictions:
                tag_name = res['label']
                confidence = res['confidence'] - 0.01
                if confidence < 0.75 or tag_name == 'others':
                    break
                if tag_name in ['火车票', '机票', '电影票', '火车票截图']:
                    photos_to_ticket.append(photo)
                selected_tag = (photo, tag_name, confidence)
                break
            photo_tag_data.append((task, photo, selected_tag))

        for task, photo, tag_data in photo_tag_data:
            if tag_data:
                _, tag_name, confidence = tag_data
                tag_id = get_tag_id(db, tag_name, photo.owner_id)
                db.add(PhotoTagRelation(photo_id=photo.id, tag_id=tag_id, confidence=confidence))
                tags_found = 1
            else:
                tags_found = 0

            tasks_status = dict(photo.processed_tasks or {})
            tasks_status['classification'] = True
            photo.processed_tasks = tasks_status
            db.add(photo)
            results.append({
                'task_id': task.id,
                'task_type': task.type,
                'status': 'completed',
                'result': {'status': 'success', 'tags_found': tags_found}
            })

        new_tasks = []
        for photo in photos_to_ticket:
            new_tasks.append(
                Task(
                    type=TaskType.RECOGNIZE_TICKET,
                    payload={'file_path': photo.file_path, 'photo_id': str(photo.id)},
                    priority=DEFAULT_PRIORITIES.get(TaskType.RECOGNIZE_TICKET, 2),
                    status=TaskStatus.PENDING,
                    owner_id=photo.owner_id
                )
            )
        if new_tasks:
            db.bulk_save_objects(new_tasks)

        db.commit()
        return results

    async def handle_completion(self, worker, items: List[Dict], db: Session) -> None:
        from app.db.models.task import TaskStatus
        for item in items:
            if item['status'] == TaskStatus.COMPLETED:
                if 'classified' not in worker.scan_status:
                    worker.scan_status['classified'] = 0
                worker.scan_status['classified'] += 1

    def release_resources(self) -> None:
        global _tag_cache
        _tag_cache.clear()
