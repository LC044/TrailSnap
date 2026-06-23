from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory
from app.db.models.task import TaskType
from typing import List, Dict, Any
import asyncio
import logging
import os
from uuid import UUID
from sqlalchemy.orm import Session
from app.db.models.task import Task, TaskStatus, TaskType
from app.db.models.photo import Photo
from app.db.models.photo_color import PhotoColor
from app.service import storage
from app.core.config_manager import ImageSettings, config_manager
from app.utils.color import extract_color_info

def rebuild_thumbnail_cpu_job(user_id: str, file_path: str, file_id: UUID, storage_root: str, config: ImageSettings = None):
    try:
        storage.update_storage_root_cache(user_id, storage_root)
        thumb_path = storage.generate_thumbnail(user_id, file_path, file_id, config=config)

        # Extract color info from the original image
        color_info = None
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ('.png', '.jpg', '.jpeg', '.webp', '.heic'):
            try:
                from PIL import Image as PILImage
                with PILImage.open(file_path) as img:
                    color_info = extract_color_info(img)
            except Exception as e:
                logging.getLogger(__name__).warning(f"Color extraction failed for {file_path}: {e}")

        return {"success": True, "thumb_path": thumb_path, "color_info": color_info}
    except Exception as e:
        return {"success": False, "error": str(e)}

def rebuild_thumbnail_cpu_batch_job(tasks_data: List[Dict], config: ImageSettings = None) -> List[Dict]:
    results = []

    for data in tasks_data:
        res = rebuild_thumbnail_cpu_job(
            data['user_id'],
            data['file_path'],
            data['file_id'],
            data['storage_root'],
            config=config
        )
        res['task_id'] = data['task_id']
        results.append(res)
    return results

@TaskStrategyFactory.register(TaskType.GENERATE_THUMBNAIL)
class GenerateThumbnailStrategy(BaseTaskStrategy):
    @property
    def task_category(self) -> str:
        return 'CPU'

    async def process(self, worker, task: Task, db: Session) -> Any:
        pass

    async def process_batch(self, worker, tasks: List[Task], db: Session) -> List[Dict]:
        results = []
        batch_jobs_data = []

        for task in tasks:
            payload = task.payload or {}
            photo_id_str = payload.get('photo_id')
            
            # If no photo_id, it's a scan/rebuild task
            if not photo_id_str:
                res = await self._process_scan(worker, task, db)
                results.append({
                    'task_id': task.id,
                    'task_type': task.type,
                    'status': 'completed',
                    'result': res
                })
                continue

            try:
                photo_id = UUID(photo_id_str)
            except:
                results.append({
                    'task_id': task.id,
                    'task_type': task.type,
                    'status': 'failed',
                    'error': 'invalid uuid'
                })
                continue

            photo = db.query(Photo).filter(Photo.id == photo_id).first()
            if not photo:
                results.append({
                    'task_id': task.id,
                    'task_type': task.type,
                    'status': 'completed',
                    'result': {'status': 'skipped', 'reason': 'photo not found'}
                })
                continue

            if not os.path.exists(photo.file_path):
                results.append({
                    'task_id': task.id,
                    'task_type': task.type,
                    'status': 'failed',
                    'error': 'file not found'
                })
                continue

            storage_root = storage._get_storage_root(photo.owner_id, db)
            batch_jobs_data.append({
                'task_id': task.id,
                'task_type': task.type,
                'user_id': str(photo.owner_id),
                'file_path': photo.file_path,
                'file_id': photo.id,
                'storage_root': storage_root,
                'photo_obj': photo  # Keep reference to update status later
            })

        if not batch_jobs_data:
            return results
        
        config = config_manager.get_user_config(photo.owner_id, db).image
        
        loop = asyncio.get_running_loop()
        batch_results = await loop.run_in_executor(
            worker.thread_pool,
            rebuild_thumbnail_cpu_batch_job,
            batch_jobs_data,
            config
        )

        for data, res in zip(batch_jobs_data, batch_results):
            if res['success']:
                photo = data['photo_obj']
                tasks_status = dict(photo.processed_tasks or {})
                tasks_status['thumbnail'] = True
                photo.processed_tasks = tasks_status
                db.add(photo)

                # Save color info
                color_info = res.get('color_info')
                if color_info and color_info.get('dominant_colors'):
                    try:
                        existing = db.query(PhotoColor).filter(PhotoColor.photo_id == photo.id).first()
                        if existing:
                            existing.dominant_colors = color_info.get('dominant_colors')
                            existing.brightness = color_info.get('brightness')
                            existing.saturation = color_info.get('saturation')
                            existing.emotion_hint = color_info.get('emotion_hint')
                        else:
                            color_record = PhotoColor(
                                photo_id=photo.id,
                                dominant_colors=color_info.get('dominant_colors'),
                                brightness=color_info.get('brightness'),
                                saturation=color_info.get('saturation'),
                                emotion_hint=color_info.get('emotion_hint'),
                            )
                            db.add(color_record)
                    except Exception as e:
                        logging.getLogger(__name__).warning(f"Failed to save color info for photo {photo.id}: {e}")

                results.append({
                    'task_id': data['task_id'],
                    'task_type': data['task_type'],
                    'status': 'completed',
                    'result': {'status': 'success'}
                })
            else:
                results.append({
                    'task_id': data['task_id'],
                    'task_type': data['task_type'],
                    'status': 'failed',
                    'error': res.get('error', 'Unknown error')
                })
                
        db.commit()
        return results

    async def _process_scan(self, worker, task: Task, db: Session) -> Dict:
        scope = task.payload.get('scope', 'all')
        force = task.payload.get('force', False)
        
        batch_size = 1000
        offset = 0
        generated_count = 0
    
        while True:
            query = db.query(Photo)
            if task.owner_id:
                query = query.filter(Photo.owner_id == task.owner_id)
                
            batch = query.offset(offset).limit(batch_size).all()
            if not batch:
                break
        
            tasks_to_create = []
            for p in batch:
                should_process = False
                if force:
                    should_process = True
                else:
                    tasks_status = p.processed_tasks or {}
                    if not tasks_status.get('thumbnail'):
                        should_process = True

                if should_process:
                    tasks_to_create.append({
                        'type': TaskType.GENERATE_THUMBNAIL,
                        'payload': {'photo_id': str(p.id), 'force': force, 'file_path': p.file_path},
                        'priority': 8,
                        'owner_id': p.owner_id
                    })

            if tasks_to_create:
                worker.add_tasks(db, tasks_to_create)
                generated_count += len(tasks_to_create)

            offset += batch_size

        return {
            'processed': 0,
            'generated_tasks': generated_count,
            'message': f'Generated {generated_count} thumbnail generation tasks'
        }

def release_resources():
    pass