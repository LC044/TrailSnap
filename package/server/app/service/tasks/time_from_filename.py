import json
import os
import logging
from datetime import datetime
from typing import Dict, Any

from PIL import Image
from sqlalchemy.orm import Session, joinedload
from app.db.models.task import Task, TaskType
from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory
from app.db.models.photo import Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.utils.exif import get_exif_data

try:
    import piexif
    PIEXIF_AVAILABLE = True
except ImportError:
    PIEXIF_AVAILABLE = False
    logging.warning("piexif not available, EXIF modification will be skipped.")

@TaskStrategyFactory.register(TaskType.BATCH_TIME_FROM_FILENAME)
class TimeFromFilenameStrategy(BaseTaskStrategy):
    @property
    def task_category(self) -> str:
        return 'IO'

    def _has_missing_metadata(self, photo: Photo) -> bool:
        """Check if photo is missing device metadata (make or model)."""
        if not photo.metadata_info:
            return True
        make = photo.metadata_info.make
        model = photo.metadata_info.model
        return not make or not model or (make.strip() == '') or (model.strip() == '')

    async def process(self, worker, task: Task, db: Session) -> Dict[str, Any]:
        payload = task.payload or {}
        target_root_path = payload.get('target_root_path')
        only_missing_metadata = payload.get('only_missing_metadata', False)
        make = payload.get('make')
        model = payload.get('model')
        time_mode = payload.get('time_mode', 'auto')
        custom_time_str = payload.get('custom_time')

        if not target_root_path:
            raise ValueError("Missing target_root_path in task payload")

        abs_target = os.path.abspath(target_root_path)

        # Parse custom_time if provided
        custom_time = None
        if custom_time_str:
            try:
                custom_time = datetime.strptime(custom_time_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                raise ValueError(f"Invalid custom_time format: {custom_time_str}. Expected YYYY-MM-DD HH:mm:ss")

        # Get photos with metadata eagerly loaded to avoid N+1 queries
        photos = (
            db.query(Photo)
            .outerjoin(PhotoMetadata, Photo.id == PhotoMetadata.photo_id)
            .options(joinedload(Photo.metadata_info))
            .filter(Photo.owner_id == task.owner_id, Photo.is_deleted.is_(False))
            .all()
        )

        target_photos = []
        for p in photos:
            if p.file_path and os.path.exists(p.file_path):
                try:
                    if os.path.abspath(p.file_path).startswith(abs_target):
                        if only_missing_metadata:
                            if self._has_missing_metadata(p):
                                target_photos.append(p)
                        else:
                            target_photos.append(p)
                except Exception:
                    pass

        task.total_items = len(target_photos)
        db.commit()

        success_count = 0
        processed = 0

        for p in target_photos:
            try:
                photo_time = None

                if time_mode == 'auto':
                    # Use existing database time (already auto-recognized during initial processing)
                    photo_time = p.photo_time
                elif time_mode == 'custom':
                    # Use user-specified time for all photos
                    photo_time = custom_time
                    p.photo_time = custom_time
                # elif time_mode == 'none': photo_time remains None

                # Update or create PhotoMetadata with make/model
                metadata = p.metadata_info
                if not metadata:
                    metadata = PhotoMetadata(photo_id=p.id)
                    db.add(metadata)
                    p.metadata_info = metadata

                if make:
                    metadata.make = make
                if model:
                    metadata.model = model

                # Update file system time and EXIF if we have a valid time
                if photo_time and time_mode != 'none':
                    # 1. Update system file modification time (os.utime)
                    timestamp = photo_time.timestamp()
                    try:
                        os.utime(p.file_path, (timestamp, timestamp))
                    except Exception as e:
                        logging.error(f"Failed to modify utime for {p.file_path}: {e}")

                    # 2. Modify EXIF if format supports it
                    _, ext = os.path.splitext(p.file_path)
                    if PIEXIF_AVAILABLE and ext.lower() in ['.jpg', '.jpeg', '.tiff', '.webp']:
                        try:
                            exif_dict = piexif.load(p.file_path)
                            dt_str = photo_time.strftime('%Y:%m:%d %H:%M:%S').encode('utf-8')
                            # print(dt_str, exif_dict)
                            if "Exif" not in exif_dict:
                                exif_dict["Exif"] = {}

                            exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = dt_str
                            exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = dt_str

                            if make or model:
                                if "0th" not in exif_dict:
                                    exif_dict["0th"] = {}
                                if make:
                                    exif_dict["0th"][piexif.ImageIFD.Make] = make.encode('utf-8')
                                if model:
                                    exif_dict["0th"][piexif.ImageIFD.Model] = model.encode('utf-8')

                            exif_bytes = piexif.dump(exif_dict)
                            piexif.insert(exif_bytes, p.file_path)
                            
                            # Update exif_info in database after modification
                            exif_text = get_exif_data(Image.open(p.file_path))

                            def default_serializer(obj):
                                if isinstance(obj, (bytes, bytearray)):
                                    return str(obj)
                                return str(obj)
                            if exif_text:
                                metadata.exif_info = json.dumps(exif_text, default=default_serializer, ensure_ascii=False)

                        except Exception as e:
                            logging.error(f"Failed to modify EXIF for {p.file_path}: {e}")

                success_count += 1
            except Exception as e:
                logging.error(f"Error processing photo {p.id} for time modification: {e}")

            processed += 1
            task.processed_items = processed

            if processed % 50 == 0:
                db.commit()

        db.commit()

        if success_count > 0:
            from app.crud.album import trigger_conditional_albums_update
            trigger_conditional_albums_update(db, task.owner_id, [p.id for p in target_photos])

        return {"success_count": success_count, "total_processed": len(target_photos)}
