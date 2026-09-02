from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory
from app.db.models.task import TaskType
from typing import List, Dict
import math
import asyncio
import logging
import os
import json
from uuid import UUID
from sqlalchemy.orm import Session
from app.db.models.task import Task, TaskStatus, TaskType
from app.db.models.photo import Photo, ImageType, FileType
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.scene import Scene
from app.utils import exif

def determine_image_type(filename: str, width: int, height: int, exif_data: dict,
                         file_type: 'FileType | None' = None) -> ImageType:
    """
    Determine image type based on filename, dimensions, and EXIF data.

    file_type 为视频时直接返回 OTHER：屏录视频的分辨率会命中下面的手机分辨率白名单
    被误判成 SCREENSHOT，而视频元数据里的 Make/Model 也不代表"相机拍摄"这一图片语义。
    """
    if file_type == FileType.video:
        return ImageType.OTHER

    filename_lower = filename.lower()

    # 1. Check for Screenshot
    # Keywords
    screenshot_keywords = ['screenshot', 'qq截图', '屏幕截图']
    if any(keyword in filename_lower for keyword in screenshot_keywords):
        return ImageType.SCREENSHOT

    # Common screen dimensions (width, height) - covering both landscape and portrait
    common_resolutions = {
        # (1920, 1080), (1080, 1920),
        # (2560, 1440), (1440, 2560),
        (1366, 768), (768, 1366),
        # (1280, 720), (720, 1280),
        # (3840, 2160), (2160, 3840), # 4K
        (1440, 900), (900, 1440),
        (1600, 900), (900, 1600),
        (1680, 1050), (1050, 1680),
        (1536, 864), (864, 1536),
        # Mobile common resolutions
        (1170, 2532), (2532, 1170), # iPhone 12/13/14
        (1284, 2778), (2778, 1284), # iPhone 12/13/14 Pro Max
        (1290, 2796), (2796, 1290), # iPhone 14 Pro Max
        (1179, 2556), (2556, 1179), # iPhone 14 Pro
        (1080, 2340), (2340, 1080), # Common Android
        (1080, 2400), (2400, 1080), # Common Android
        (1440, 3088), (3088, 1440), # Samsung Ultra
        (1440, 3200), (3200, 1440),
        (1260, 2800), (2800, 1260),
        (1600, 2560), (2560, 1600)
    }

    if width and height:
        if (width, height) in common_resolutions:
             return ImageType.SCREENSHOT
    # 2. Check for Camera
    if exif_data:
        make = exif_data.get('Make')
        model = exif_data.get('Model')
        if make or model:
            return ImageType.CAMERA
    # 3. Default
    return ImageType.OTHER

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000  # radius of Earth in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2) 
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    c = 2*math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def is_point_in_polygon(lat, lng, polygon):
    """
    Ray casting algorithm. 
    Polygon is list of [lat, lng].
    """
    if not polygon or len(polygon) < 3:
        return False
        
    n = len(polygon)
    inside = False
    p1_lat, p1_lng = polygon[0]
    
    for i in range(n + 1):
        p2_lat, p2_lng = polygon[i % n]
        if lng > min(p1_lng, p2_lng):
            if lng <= max(p1_lng, p2_lng):
                if lat <= max(p1_lat, p2_lat):
                    if p1_lng != p2_lng:
                        xinters = (lng - p1_lng) * (p2_lat - p1_lat) / (p2_lng - p1_lng) + p1_lat
                    if p1_lat == p2_lat or lat <= xinters:
                        inside = not inside
        p1_lat, p1_lng = p2_lat, p2_lng
    return inside

def identify_scene(db: Session, lat: float, lng: float):
    # Optimisation: Filter by rough bounding box first?
    # For now, fetch all scenes. If thousands, it's okay-ish for a background task.
    # To optimize, we can select only scenes where lat/lng is within a certain range (e.g. +/- 0.5 deg)
    # But some scenes might be huge.
    
    # Let's try to fetch all scenes with basic info.
    scenes = db.query(Scene).all()
    
    for scene in scenes:
        # Check polygon first
        if scene.polygon:
            try:
                poly = json.loads(scene.polygon) if isinstance(scene.polygon, str) else scene.polygon
                if is_point_in_polygon(lat, lng, poly):
                    return scene.id
            except Exception as e:
                logging.error(f"Error parsing polygon for scene {scene.id}: {e}")
                
        # Check radius if polygon is empty (or as fallback? User said "If polygon empty, check radius")
        elif scene.radius and scene.latitude is not None and scene.longitude is not None:
            dist = haversine_distance(lat, lng, float(scene.latitude), float(scene.longitude))
            if dist <= scene.radius:
                return scene.id
                
    return None

def rebuild_metadata_cpu_job(file_path: str, file_id: UUID):
    try:
        file_name = os.path.basename(file_path)
        # Defaults to extract_location_details=True
        meta = exif.extract_metadata(file_path, file_name)
        return {"success": True, "meta": meta}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def sync_rebuild_metadata_cpu_job(file_path: str, file_id: UUID):
    try:
        file_name = os.path.basename(file_path)
        # Defaults to extract_location_details=True
        meta = exif.extract_metadata(file_path, file_name)
        return {"success": True, "meta": meta}
    except Exception as e:
        return {"success": False, "error": str(e)}

@TaskStrategyFactory.register(TaskType.EXTRACT_METADATA)
class ExtractMetadataStrategy(BaseTaskStrategy):
    @property
    def task_category(self) -> str:
        return 'IO'

    async def process(self, worker, task: Task, db: Session):
        """
        Handle single file metadata extraction (Heavy task: Geolocation etc.)
        """
        photo_id_str = task.payload.get('photo_id')
        if not photo_id_str:
            return {'status': 'skipped', 'reason': 'missing photo_id'}

        # Check if photo still exists
        try:
            photo_id = UUID(photo_id_str)
        except:
            return {'status': 'failed', 'reason': 'invalid uuid'}

        photo = db.query(Photo).filter(Photo.id == photo_id).first()
        if not photo:
             return {'status': 'skipped', 'reason': 'photo not found'}

        file_path = task.payload.get('file_path')
        if not file_path:
            file_path = photo.file_path

        # loop = asyncio.get_running_loop()
        # res = await loop.run_in_executor(
        #     worker.thread_pool,
        #     rebuild_metadata_cpu_job,
        #     file_path,
        #     photo_id
        # )
        # res = rebuild_metadata_cpu_job(file_path,photo_id)
        res = await sync_rebuild_metadata_cpu_job(file_path, photo_id)
        if res['success']:
            meta = res['meta']
            update_photo_metadata_from_extract(db, photo, meta)
            return {'status': 'success'}
        else:
            raise Exception(res.get('error'))

def update_photo_metadata_from_extract(db: Session, photo: Photo, meta: dict):
    # Update DB
    db_meta = db.query(PhotoMetadata).filter(PhotoMetadata.photo_id == photo.id).first()
    if not db_meta:
        db_meta = PhotoMetadata(photo_id=photo.id)
        db.add(db_meta)

    # Update fields
    if meta.get("exif_info"):
        exif_dict = meta["exif_info"]
        # Serialize for storage
        # Convert non-serializable objects to string
        def default_serializer(obj):
            if isinstance(obj, (bytes, bytearray)):
                return str(obj)
            return str(obj)

        db_meta.exif_info = json.dumps(exif_dict, default=default_serializer, ensure_ascii=False)

        # Extract Camera Info
        if exif_dict.get('Make'):
            db_meta.make = str(exif_dict.get('Make')).strip().replace('\x00', '')
        if exif_dict.get('Model'):
            db_meta.model = str(exif_dict.get('Model')).strip().replace('\x00', '')
        
        sp = {}
        # FNumber often comes as a ratio, we store string representation
        if exif_dict.get('FNumber'):
            sp['f_number'] = str(exif_dict.get('FNumber'))
        if exif_dict.get('ExposureTime'):
            sp['exposure_time'] = str(exif_dict.get('ExposureTime'))
        if exif_dict.get('ISOSpeedRatings'):
            sp['iso'] = str(exif_dict.get('ISOSpeedRatings'))
        if exif_dict.get('FocalLength'):
            sp['focal_length'] = str(exif_dict.get('FocalLength'))
        if exif_dict.get('FocalLengthIn35mmFilm'):
            sp['focal_length_35mm'] = str(exif_dict.get('FocalLengthIn35mmFilm'))
        # 视频专属参数。shooting_params 是 JSON 列，无需 migration。
        for meta_key, sp_key in (('duration', 'duration'), ('fps', 'fps'),
                                 ('codec', 'codec'), ('rotation', 'rotation')):
            value = meta.get(meta_key)
            if value is not None:
                sp[sp_key] = value
        if sp:
            db_meta.shooting_params = sp

    loc_details = meta.get("location_details", {})
    if loc_details:
        if loc_details.get("longitude"): db_meta.longitude = loc_details.get("longitude")
        if loc_details.get("latitude"): db_meta.latitude = loc_details.get("latitude")
        if loc_details.get("city"): db_meta.city = loc_details.get("city")
        if loc_details.get("district"): db_meta.district = loc_details.get("district")
        if loc_details.get("province"): db_meta.province = loc_details.get("province")
        if loc_details.get("country"): db_meta.country = loc_details.get("country")
        if loc_details.get("address"): db_meta.address = loc_details.get("address")

        # Identify Scene
        if db_meta.latitude is not None and db_meta.longitude is not None:
            try:
                scene_id = identify_scene(db, float(db_meta.latitude), float(db_meta.longitude))
                if scene_id:
                    db_meta.scene_id = scene_id
            except Exception as e:
                logging.error(f"Error identifying scene: {e}")

    if meta.get("photo_time"):
        photo.photo_time = meta["photo_time"]

    # 视频的宽高交由容器解析补齐（含旋转矩阵校正），仅在原值为空时写入，
    # 避免覆盖 PROCESS_BASIC 阶段 cv2 已经拿到的正确尺寸。
    if getattr(photo, 'width', None) is None and meta.get("width"):
        photo.width = meta["width"]
    if getattr(photo, 'height', None) is None and meta.get("height"):
        photo.height = meta["height"]
    if not getattr(photo, 'duration', None) and meta.get("duration"):
        photo.duration = meta["duration"]

    photo.image_type = determine_image_type(
        photo.filename, photo.width, photo.height, meta.get("exif_info", {}),
        getattr(photo, 'file_type', None)
    )

    # Mark as processed
    tasks_status = dict(photo.processed_tasks or {})
    tasks_status['metadata'] = True
    photo.processed_tasks = tasks_status
    db.add(photo)
    db.commit()
    
    if photo.owner_id:
        from app.crud.album import trigger_conditional_albums_update
        trigger_conditional_albums_update(db, photo.owner_id, [photo.id])

@TaskStrategyFactory.register(TaskType.REBUILD_METADATA)
class RebuildMetadataStrategy(BaseTaskStrategy):
    @property
    def task_category(self) -> str:
        return 'IO'

    async def process(self, worker, task: Task, db: Session):
        scope = task.payload.get('scope', 'all')
        force = task.payload.get('force', False)

        # Generator Mode: Create EXTRACT_METADATA tasks for each photo
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
                    if not tasks_status.get('metadata'):
                        should_process = True

                if should_process:
                    tasks_to_create.append({
                        'type': TaskType.EXTRACT_METADATA,
                        'payload': {'photo_id': str(p.id), 'file_path': p.file_path}, # Pass file_path for optimization
                        'priority': 5,
                        'owner_id': p.owner_id
                    })

            if tasks_to_create:
                worker.add_tasks(db, tasks_to_create)
                generated_count += len(tasks_to_create)

            offset += batch_size

        return {
            'processed': 0,
            'generated_tasks': generated_count,
            'message': f'Generated {generated_count} metadata extraction tasks'
        }

def release_resources():
    import reverse_geocoder as rg
    rg.unload()
    logging.info("Reverse geocoder resources released")