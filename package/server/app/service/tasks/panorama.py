"""One persisted job per photo allows normal worker retries and restart recovery."""
import asyncio

from app.db.models.photo import Photo, FileType
from app.db.models.task import TaskType
from app.service.panorama import detect_file
from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory
from app.utils.panorama import apply_detection


@TaskStrategyFactory.register(TaskType.SCAN_PANORAMA)
class ScanPanoramaStrategy(BaseTaskStrategy):
    async def process(self, worker, task, db) -> dict:
        photo = db.query(Photo).filter(Photo.id == task.photo_id, Photo.owner_id == task.owner_id,
                                       Photo.is_deleted.is_(False)).first()
        if not photo or photo.file_type != FileType.image:
            return {"skipped": True}
        detected = await asyncio.to_thread(detect_file, photo.file_path)
        # Refresh after IO: a manual decision may have arrived while reading.
        db.refresh(photo, with_for_update=True)
        apply_detection(photo, detected)
        photo.processed_tasks = dict(photo.processed_tasks or {}, panorama=True)
        db.commit()
        return {"panorama": bool(photo.panorama_projection)}
