import os
import logging
from typing import Dict, Any, List, Optional, Set
from sqlalchemy.orm import Session
from app.db.models.task import Task, TaskType
from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory
from app.db.models.photo import Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.utils.export_formatter import format_export_filename, METADATA_VARS
from app.utils.path_validation import validate_target_path

@TaskStrategyFactory.register(TaskType.BATCH_RENAME)
class BatchRenameStrategy(BaseTaskStrategy):
    @property
    def task_category(self) -> str:
        return 'IO'

    async def process(self, worker, task: Task, db: Session) -> Dict[str, Any]:
        payload = task.payload or {}
        target_root_path = payload.get('target_root_path')
        template = payload.get('template', 'IMG_{date}_{time}')

        if not target_root_path:
            raise ValueError("Missing target_root_path in task payload")

        abs_target = os.path.abspath(target_root_path)

        # Get photos that are physically under target_root_path
        # Normalizing paths is important
        photos = db.query(Photo).filter(Photo.owner_id == task.owner_id, Photo.is_deleted.is_(False)).all()
        target_photos = []
        for p in photos:
            if p.file_path and os.path.exists(p.file_path):
                try:
                    if os.path.abspath(p.file_path).startswith(abs_target):
                        target_photos.append(p)
                except Exception:
                    pass

        task.total_items = len(target_photos)
        db.commit()

        # Batch-fetch metadata in ONE query instead of one-per-photo (N+1).
        # Skip the lookup entirely when the template uses no metadata vars.
        metadata_map: Dict = {}
        if target_photos and any(var in template for var in METADATA_VARS):
            photo_ids = [p.id for p in target_photos]
            rows = db.query(PhotoMetadata).filter(PhotoMetadata.photo_id.in_(photo_ids)).all()
            metadata_map = {m.photo_id: m for m in rows}

        # Plan every rename up front so collisions are resolved in memory
        # against the whole batch. A target name must not collide with:
        #   - a pre-existing file on disk (outside this batch)
        #   - another photo's current source path (not yet renamed)
        #   - a target name already assigned in this batch
        # This avoids the old race where a sequential rename could target a
        # sibling's still-on-disk source file.
        source_paths: Set[str] = set()
        for p in target_photos:
            try:
                source_paths.add(os.path.abspath(p.file_path))
            except Exception:
                pass

        planned: List[tuple] = []  # (photo, old_path, new_path|None, new_basename|None)
        assigned: Set[str] = set()
        for i, p in enumerate(target_photos):
            old_path = p.file_path
            old_abs = os.path.abspath(old_path)
            dir_name = os.path.dirname(old_path)
            _, ext = os.path.splitext(old_path)

            metadata = metadata_map.get(p.id)
            base_formatted = format_export_filename(template, p, i + 1, metadata, p.filename)
            new_basename = f"{base_formatted}{ext}"
            new_path = os.path.join(dir_name, new_basename)
            try:
                validate_target_path(new_path)
            except ValueError as exc:
                logging.error("Skipping invalid rename target %s: %s", new_path, exc)
                planned.append((p, old_path, None, None))
                continue
            new_abs = os.path.abspath(new_path)

            if new_abs == old_abs:
                # Name is already correct; no rename needed.
                planned.append((p, old_path, None, None))
                continue

            counter = 1
            while new_abs in source_paths or new_abs in assigned or os.path.exists(new_path):
                new_basename = f"{base_formatted}({counter}){ext}"
                new_path = os.path.join(dir_name, new_basename)
                new_abs = os.path.abspath(new_path)
                counter += 1

            try:
                validate_target_path(new_path)
            except ValueError as exc:
                logging.error("Skipping invalid rename target %s: %s", new_path, exc)
                planned.append((p, old_path, None, None))
                continue

            assigned.add(new_abs)
            planned.append((p, old_path, new_path, new_basename))

        success_count = 0
        processed = 0
        for p, old_path, new_path, new_basename in planned:
            if new_path is not None:
                try:
                    os.rename(old_path, new_path)
                    p.file_path = new_path
                    p.filename = new_basename
                    success_count += 1
                except Exception as e:
                    logging.error(f"Failed to rename {old_path} to {new_path}: {e}")

            processed += 1
            task.processed_items = processed

            if processed % 50 == 0:
                db.commit()

        db.commit()
        return {"success_count": success_count, "total_processed": len(target_photos)}
