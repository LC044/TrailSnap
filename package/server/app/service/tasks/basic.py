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
from app.utils.color import extract_color_info

def process_basic_cpu_job(file_path: str, file_id: UUID, storage_root: str, user_id: str, image_config=None):
    """
    CPU-intensive task running in a separate process.
    Generates thumbnails and extracts BASIC metadata (no heavy geolocation).

    image_config: 预取的 ImageSettings，用于 _save_thumbnails 时避免再开 DB
    session（原实现会为批中每张图 SessionLocal() 一次，撑爆连接池）。
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

        # 1. Generate thumbnail（透传 image_config，避免 hot path 上开 DB session）
        thumb_path = storage.generate_thumbnail(user_id, file_path, file_id, image_obj=image_obj, config=image_config)

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

        # 4. Extract color/emotion info (while image_obj is still open)
        color_info = None
        if image_obj:
            try:
                color_info = extract_color_info(image_obj)
            except Exception as e:
                logging.getLogger(__name__).warning(f"Color extraction failed for {file_path}: {e}")

        if image_obj:
            image_obj.close()

        # 5. Calculate MD5
        md5_hash = calculate_file_md5(file_path)

        # Check for Google Motion Photo and extract video
        # 注意：generate_thumbnail 失败会返回 None，此时不能拿 thumb_path 拼 .mp4 路径
        # （os.path.splitext(None) 会抛 "expected str, bytes or os.PathLike"）。
        is_motion_photo = False
        if ext in ('.jpg', '.jpeg') and thumb_path:
            video_path = motion_photo.extract_video(file_path, video_path=os.path.splitext(thumb_path)[0] + '.mp4')
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
            "md5_hash": md5_hash,
            "color_info": color_info
        }
    except Exception as e:
        import traceback
        logging.getLogger(__name__).error(
            f"process_basic_cpu_job failed for {file_path}: {e}\n{traceback.format_exc()}"
        )
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
        image_config = data.get('image_config')

        res = process_basic_cpu_job(file_path, file_id, storage_root, user_id, image_config=image_config)
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
        from app.db.models.photo import Photo

        results = []
        batch_jobs_data = []
        # 按 user_id 预取一次 image_config，避免 _save_thumbnails 在 CPU worker 中
        # 为批内每张图各开一次 SessionLocal 拉 DB（config_manager 内部有 5s LRU
        # 缓存，同一 user_id 实际只查一次 DB）。
        image_config_cache: Dict[str, Any] = {}

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

            # 若 Photo 已由上传接口预建（payload 带 photo_id）或 DB 已存在同 file_path，
            # 则复用旧 id 并标记 pre_created，跳过 batch_create_photos 避免外键冲突。
            payload_photo_id = task.payload.get('photo_id')
            pre_created_photo_id = None
            if payload_photo_id:
                try:
                    pre_created_photo_id = UUID(payload_photo_id) if not isinstance(payload_photo_id, UUID) else payload_photo_id
                except Exception:
                    pre_created_photo_id = None

            if pre_created_photo_id is None and user_id:
                try:
                    existing = db.query(Photo.id).filter(
                        Photo.owner_id == user_id,
                        Photo.file_path == file_path
                    ).first()
                    if existing:
                        pre_created_photo_id = existing[0]
                except Exception as e:
                    logging.getLogger(__name__).warning(
                        f"BasicTaskStrategy: pre-check existing photo failed for {file_path}: {e}"
                    )

            photo_id = pre_created_photo_id if pre_created_photo_id else uuid4()
            storage_root = storage._get_storage_root(user_id, db)

            # 每个 user_id 预取一次 image_config（本批复用），跨线程传纯 pydantic 对象安全
            if user_id not in image_config_cache:
                try:
                    image_config_cache[user_id] = config_manager.get_user_config(user_id, db).image
                except Exception as e:
                    logging.getLogger(__name__).warning(
                        f"BasicTaskStrategy: prefetch image_config failed for user={user_id}: {e}"
                    )
                    image_config_cache[user_id] = None

            batch_jobs_data.append({
                'task_id': task.id,
                'task_type': task.type,
                'file_path': file_path,
                'file_id': photo_id,
                'storage_root': storage_root,
                'user_id': user_id,
                'live_photo_video_path': live_photo_video_path,
                'is_live_photo': is_live_photo,
                'is_pre_created': pre_created_photo_id is not None,
                'image_config': image_config_cache.get(user_id),
            })
            
        if not batch_jobs_data:
            return results

        loop = asyncio.get_running_loop()
        batch_results = await loop.run_in_executor(
            worker.thread_pool,
            # worker.process_pool,
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
                # get_image_dimensions 对损坏图片 / 未装 cv2 的视频 / 不支持的扩展名
                # 会返回 (None, None, None)，且异常被底层裸 except 吞掉。
                # 这里若不守卫，None < int 会抛 TypeError 并拖垮整批任务。
                if res['width'] is None or res['height'] is None:
                    logging.getLogger(__name__).warning(
                        f"BasicTaskStrategy: dimensions unknown for {data['file_path']} "
                        f"(width={res['width']}, height={res['height']}), skip resolution filter"
                    )
                else:
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
                        'user_id': user_id,
                        'color_info': res.get('color_info'),
                        'is_pre_created': data.get('is_pre_created', False),
                    }
                }
            })

        return results

    async def handle_completion(self, worker, items: List[Dict], db: Session) -> None:
        from app.db.models.photo_color import PhotoColor
        from app.db.models.photo_metadata import PhotoMetadata

        photos_to_create = {}
        pre_created_items = []
        index_logs = []
        processed_photos = {}

        for item in items:
            status = item['status']
            if status == TaskStatus.COMPLETED:
                res = item['result']
                if 'photo_create_data' in res:
                    data = res['photo_create_data']
                    user_id = data.get('user_id')
                    if data.get('is_pre_created'):
                        pre_created_items.append(data)
                    else:
                        if user_id not in photos_to_create:
                            photos_to_create[user_id] = []
                        photos_to_create[user_id].append(data)
                        index_logs.append(IndexLog(action='added', file_path=data['file_path'], photo_id=data['photo_id'], owner_id=user_id))
                        worker.scan_status['added'] += 1
                        worker.scan_status['processed_files'] += 1
                    processed_photos[str(data['photo_id'])] = {
                        'path': data['file_path'],
                        'owner_id': user_id,
                        'color_info': data.get('color_info'),
                        'metadata': data.get('metadata'),
                        'is_pre_created': data.get('is_pre_created', False),
                    }

        # 分支 A：新增 Photo。batch_create_photos 会按 file_path 去重，
        # 被去重丢弃的 photo_id 不会入 photos 表，后续引用它们写 PhotoColor
        # 或派发下游任务会触发外键违反并连坐回滚，故必须限定在 inserted_ids 内。
        inserted_ids = set()
        if photos_to_create:
            for uid, photos in photos_to_create.items():
                inserted_ids.update(
                    str(pid) for pid in app.crud.photo.batch_create_photos(db, photos, user_id=uid)
                )
            db.add_all(index_logs)

        # 分支 B：Photo 已存在，走 "先查再插/更新" 幂等补齐 PhotoMetadata。
        for data in pre_created_items:
            photo_id = str(data['photo_id'])
            meta_schema = data.get('metadata')
            if not meta_schema:
                continue
            try:
                db_meta = db.query(PhotoMetadata).filter(
                    PhotoMetadata.photo_id == data['photo_id']
                ).first()
                if db_meta is None:
                    db.add(PhotoMetadata(
                        photo_id=data['photo_id'],
                        exif_info=meta_schema.exif_info,
                    ))
                elif not db_meta.exif_info and meta_schema.exif_info:
                    # 仅在原为空时补齐，避免覆盖 EXTRACT_METADATA 精修结果
                    db_meta.exif_info = meta_schema.exif_info
                    db.add(db_meta)
            except Exception as e:
                logging.getLogger(__name__).warning(
                    f"Failed to upsert PhotoMetadata for pre-created photo {photo_id}: {e}"
                )

        eligible_ids = set(inserted_ids)
        for data in pre_created_items:
            eligible_ids.add(str(data['photo_id']))

        if not eligible_ids:
            return

        for photo_id, info in processed_photos.items():
            if photo_id not in eligible_ids:
                continue
            color_info = info.get('color_info')
            if color_info and color_info.get('dominant_colors'):
                try:
                    existing_color = db.query(PhotoColor).filter(
                        PhotoColor.photo_id == photo_id
                    ).first()
                    if existing_color:
                        continue
                    color_record = PhotoColor(
                        photo_id=photo_id,
                        dominant_colors=color_info.get('dominant_colors'),
                        brightness=color_info.get('brightness'),
                        saturation=color_info.get('saturation'),
                        emotion_hint=color_info.get('emotion_hint'),
                    )
                    db.add(color_record)
                except Exception as e:
                    logging.getLogger(__name__).warning(f"Failed to save color info for photo {photo_id}: {e}")

        for photo_id, info in processed_photos.items():
            if photo_id not in eligible_ids:
                continue
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
