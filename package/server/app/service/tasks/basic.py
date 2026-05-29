from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory
from app.db.models.task import TaskType, DEFAULT_PRIORITIES
from typing import List, Dict, Any
import asyncio
import logging
import os
import json
from uuid import UUID, uuid4
from PIL import Image
from pillow_heif import register_heif_opener

from app.core.config_manager import config_manager

# Register HEIF opener to enable HEIC/HEIF support in Pillow
register_heif_opener()
from sqlalchemy.orm import Session

from app.db.models.task import Task, TaskStatus, TaskType
from app.db.models.photo import FileType
from app.db.models.index_log import IndexLog
import app.crud.photo
from app.schemas.metadata import PhotoMetadataCreate
from app.service import storage
from app.utils import exif
from app.utils.hash import calculate_file_md5
from app.schemas import photo as photo_schemas
from app.utils import motion_photo

def process_basic_cpu_job(file_path: str, file_id: UUID, storage_root: str, user_id: str):
    """
    CPU-intensive task running in a separate process.
    Generates thumbnails and extracts BASIC metadata (no heavy geolocation).
    """
    try:
        # Initialize storage root cache in this process
        storage.update_storage_root_cache(user_id, storage_root)
        # print(file_path)
        # Open image once if possible to reduce IO
        image_obj = None
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ('.png', '.jpg', '.jpeg', '.webp', '.heic'):
             try:
                 image_obj = Image.open(file_path)
             except Exception:
                 pass

        # 1. Generate thumbnail
        thumb_path = storage.generate_thumbnail(user_id, file_path, file_id, image_obj=image_obj)

        # 2. Extract metadata (BASIC ONLY)
        file_name = os.path.basename(file_path)
        meta = exif.extract_metadata(file_path, file_name, image_obj=image_obj, extract_location_details=False)
        if meta.get("exif_info"):
            # Serialize for storage
            # Convert non-serializable objects to string
            def default_serializer(obj):
                if isinstance(obj, (bytes, bytearray)):
                    return str(obj)
                return str(obj)
            meta['exif_info'] = json.dumps(meta["exif_info"], default=default_serializer, ensure_ascii=False)
        # 3. Get dimensions/size
        size = storage.get_file_size(file_path)
        width, height, duration = storage.get_image_dimensions(file_path, image_obj=image_obj)

        if image_obj:
            image_obj.close()

        # 4. Calculate MD5
        md5_hash = calculate_file_md5(file_path)

        # Check for Google Motion Photo and extract video
        is_motion_photo = False
        if ext in ('.jpg', '.jpeg'):
            video_path = motion_photo.extract_video(file_path, video_path=thumb_path[:-4] + '.mp4')
            if video_path:
                is_motion_photo = True

        return {
            "success": True,
            "thumb_path": thumb_path,
            "meta": meta,
            "size": size,
            "width": width,
            "height": height,
            "duration": duration,
            "file_name": file_name,
            "photo_create_data": None, # Placeholder
            "is_motion_photo": is_motion_photo,
            "md5_hash": md5_hash
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def process_basic_cpu_batch_job(tasks_data: List[Dict]) -> List[Dict]:
    """
    CPU-intensive task running in a separate process/thread to process a batch of tasks.
    Avoids frequent thread pool switching overhead.
    """
    results = []
    for data in tasks_data:
        file_path = data['file_path']
        file_id = data['file_id']
        storage_root = data['storage_root']
        user_id = data['user_id']
        
        res = process_basic_cpu_job(file_path, file_id, storage_root, user_id)
        res['task_id'] = data['task_id']
        results.append(res)
    return results

@TaskStrategyFactory.register(TaskType.PROCESS_BASIC)
class BasicTaskStrategy(BaseTaskStrategy):
    @property
    def task_category(self) -> str:
        return 'CPU'

    async def process(self, worker, task: Task, db: Session) -> Any:
        pass

    async def process_batch(self, worker, tasks: List[Task], db: Session) -> List[Dict]:
        results = []
        batch_jobs_data = []
        
        for task in tasks:
            file_path = task.payload.get('file_path')
            live_photo_video_path = task.payload.get('live_photo_video_path')
            is_live_photo = task.payload.get('is_live_photo', False)
            user_id = task.payload.get('user_id')
            if not user_id and task.owner_id:
                user_id = str(task.owner_id)
            
            if not file_path or not os.path.exists(file_path):
                results.append({
                    'task_id': task.id,
                    'task_type': task.type,
                    'status': 'completed',
                    'result': {'status': 'skipped', 'reason': 'file not found'}
                })
                continue
                
            photo_id = uuid4()
            storage_root = storage._get_storage_root(user_id, db)
            
            batch_jobs_data.append({
                'task_id': task.id,
                'task_type': task.type,
                'file_path': file_path,
                'file_id': photo_id,
                'storage_root': storage_root,
                'user_id': user_id,
                'live_photo_video_path': live_photo_video_path,
                'is_live_photo': is_live_photo
            })
            
        if not batch_jobs_data:
            return results

        loop = asyncio.get_running_loop()
        batch_results = await loop.run_in_executor(
            worker.thread_pool,
            process_basic_cpu_batch_job,
            batch_jobs_data
        )

        for data, res in zip(batch_jobs_data, batch_results):
            if not res['success']:
                results.append({
                    'task_id': data['task_id'],
                    'task_type': data['task_type'],
                    'status': 'failed',
                    'error': res.get('error', 'Unknown error')
                })
                continue
                
            # Check resolution filter
            user_id = data['user_id']
            filter_config = config_manager.get_user_config(user_id, db).filter
            if filter_config.enable:
                if filter_config.min_width > 0 and res['width'] < filter_config.min_width:
                     results.append({'task_id': data['task_id'], 'task_type': data['task_type'], 'status': 'completed', 'result': {'status': 'skipped', 'reason': 'filtered_by_width'}})
                     continue
                if filter_config.min_height > 0 and res['height'] < filter_config.min_height:
                     results.append({'task_id': data['task_id'], 'task_type': data['task_type'], 'status': 'completed', 'result': {'status': 'skipped', 'reason': 'filtered_by_height'}})
                     continue

            # Construct PhotoCreate data
            meta = res['meta']
            ext = os.path.splitext(res['file_name'])[1]
            file_type = FileType.image
            if ext.lower() in ['.mp4', '.mov', '.avi', '.mkv', '.webm']:
                file_type = FileType.video
            if data['is_live_photo'] or res.get('is_motion_photo'):
                file_type = FileType.live_photo
                
            photo_create = photo_schemas.PhotoCreate(
                file_type=file_type,
                size=res['size'],
                width=res['width'],
                height=res['height'],
                duration=res['duration'],
                filename=res['file_name'],
                photo_time=meta["photo_time"],
                md5=res.get('md5_hash')
            )

            metadata_create = PhotoMetadataCreate(
                exif_info=meta["exif_info"]
            )

            results.append({
                'task_id': data['task_id'],
                'task_type': data['task_type'],
                'status': 'completed',
                'result': {
                    'photo_create_data': {
                        'photo': photo_create,
                        'metadata': metadata_create,
                        'photo_id': data['file_id'],
                        'file_path': data['file_path'],
                        'user_id': user_id
                    }
                }
            })

        return results

    async def handle_completion(self, worker, items: List[Dict], db: Session) -> None:
        photos_to_create = {} # user_id -> list of data
        index_logs = []
        processed_photos = {} # photo_id -> {path: file_path, owner_id: user_id}

        for item in items:
            status = item['status']
            if status == TaskStatus.COMPLETED:
                res = item['result']
                if 'photo_create_data' in res:
                    data = res['photo_create_data']
                    user_id = data.get('user_id')
                    if user_id not in photos_to_create:
                        photos_to_create[user_id] = []
                    photos_to_create[user_id].append(data)
                    index_logs.append(IndexLog(action='added', file_path=data['file_path'], photo_id=data['photo_id'], owner_id=user_id))
                    processed_photos[str(data['photo_id'])] = {'path': data['file_path'], 'owner_id': user_id}
                    worker.scan_status['added'] += 1
                    worker.scan_status['processed_files'] += 1

        if photos_to_create:
            # print(photos_to_create)
            for uid, photos in photos_to_create.items():
                app.crud.photo.batch_create_photos(db, photos, user_id=uid)
            db.add_all(index_logs)
            # return
            for photo_id, info in processed_photos.items():
                file_path = info['path']
                owner_id = info['owner_id']

                # 1. Metadata Task
                db.add(Task(type=TaskType.EXTRACT_METADATA, payload={'file_path': file_path, 'photo_id': photo_id}, priority=DEFAULT_PRIORITIES[TaskType.EXTRACT_METADATA], status=TaskStatus.PENDING, owner_id=owner_id))
                # 2. Face Recognition Task
                db.add(Task(type=TaskType.RECOGNIZE_FACE, payload={'file_path': file_path, 'photo_id': photo_id}, priority=DEFAULT_PRIORITIES[TaskType.RECOGNIZE_FACE], status=TaskStatus.PENDING, owner_id=owner_id))
                # 3. OCR Task
                db.add(Task(type=TaskType.OCR, payload={'file_path': file_path, 'photo_id': photo_id}, priority=DEFAULT_PRIORITIES[TaskType.OCR], status=TaskStatus.PENDING, owner_id=owner_id))
                # 4. Classification Task
                db.add(Task(type=TaskType.CLASSIFY_IMAGE, payload={'file_path': file_path, 'photo_id': photo_id}, priority=DEFAULT_PRIORITIES[TaskType.CLASSIFY_IMAGE], status=TaskStatus.PENDING, owner_id=owner_id))
                # 5. Ticket Recognition Task
                # db.add(Task(type=TaskType.RECOGNIZE_TICKET, payload={'file_path': file_path, 'photo_id': photo_id}, priority=DEFAULT_PRIORITIES.get(TaskType.RECOGNIZE_TICKET, 2), status=TaskStatus.PENDING, owner_id=owner_id))
                # 6. Visual Description Task
                db.add(Task(type=TaskType.VISUAL_DESCRIPTION, payload={'file_path': file_path, 'photo_id': photo_id}, priority=DEFAULT_PRIORITIES[TaskType.VISUAL_DESCRIPTION], status=TaskStatus.PENDING, owner_id=owner_id))
                # 7. Embedding Generation Task
                db.add(Task(type=TaskType.IMAGE_EMBEDDING, payload={'file_path': file_path, 'photo_id': photo_id}, priority=DEFAULT_PRIORITIES[TaskType.IMAGE_EMBEDDING], status=TaskStatus.PENDING, owner_id=owner_id))

def release_resources():
    pass
