from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory
from app.db.models.task import TaskType
from typing import List, Dict
import logging
import os
import asyncio
from uuid import UUID
from sqlalchemy.orm import Session
from app.db.models.task import Task, TaskStatus, TaskType
from app.db.models.photo import Photo
from app.utils.hash import calculate_file_md5_async

@TaskStrategyFactory.register(TaskType.FIND_DUPLICATE_PHOTOS)
class FindDuplicatePhotosStrategy(BaseTaskStrategy):
    @property
    def task_category(self) -> str:
        return 'IO'

    @property
    def timeout(self) -> int:
        return 60 * 60  # 1 hour timeout

    async def process(self, worker, task: Task, db: Session):
        """
        Handle finding duplicate photos task by calculating MD5 for photos that don't have one.
        """
        try:
            user_id = str(task.owner_id)
            logging.info(f"Starting duplicate photo scan for user {user_id}")

            # 1. Fetch all photos for the user where MD5 is empty or null
            photos_query = db.query(Photo).filter(
                Photo.owner_id == user_id,
                Photo.is_deleted.is_(False),
                (Photo.md5 == None) | (Photo.md5 == "")
            )
            requested_ids = (task.payload or {}).get("photo_ids") or []
            if requested_ids:
                parsed_ids = []
                for value in requested_ids[:500]:
                    try:
                        parsed_ids.append(UUID(str(value)))
                    except (ValueError, TypeError, AttributeError):
                        continue
                photos_query = photos_query.filter(Photo.id.in_(parsed_ids)) if parsed_ids else photos_query.filter(False)
            photos = photos_query.all()

            total_photos = len(photos)
            task.total_items = total_photos
            task.processed_items = 0
            db.commit()

            if total_photos == 0:
                task.result = {'message': 'No photos need MD5 calculation'}
                task.status = TaskStatus.COMPLETED
                db.commit()
                return {'status': 'completed', 'count': 0}

            # 2. Process photos in batches concurrently
            processed_count = 0
            updated_count = 0
            batch_size = 20  # You can adjust concurrency level here

            for i in range(0, total_photos, batch_size):
                batch_photos = photos[i:i + batch_size]
            
                # Create async tasks for MD5 calculation
                md5_tasks = []
                for photo in batch_photos:
                    if photo.file_path and os.path.exists(photo.file_path):
                        md5_tasks.append(calculate_file_md5_async(photo.file_path))
                    else:
                        async def empty_md5(): return ""
                        md5_tasks.append(empty_md5())
            
                # Gather results concurrently
                md5_results = await asyncio.gather(*md5_tasks)
            
                # Update photo objects
                for photo, md5_hash in zip(batch_photos, md5_results):
                    if md5_hash:
                        photo.md5 = md5_hash
                        updated_count += 1
                    processed_count += 1
            
                # Update progress and commit in batches
                task.processed_items = processed_count
                db.commit()

            # Final commit for any remaining items
            task.processed_items = total_photos
            task.status = TaskStatus.COMPLETED
            task.result = {'updated_count': updated_count}
            db.commit()
        
            logging.info(f"Finished duplicate photo scan for user {user_id}. Updated {updated_count}/{total_photos} photos.")
            return {'status': 'completed', 'updated_count': updated_count}

        except Exception as e:
            logging.error(f"Duplicate task failed: {e}")
            raise e

