import os
import logging
from typing import Dict, Any
from sqlalchemy.orm import Session
from app.db.models.task import Task, TaskType
from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory
from app.db.models.photo import Photo

@TaskStrategyFactory.register(TaskType.BATCH_RENAME)
class BatchRenameStrategy(BaseTaskStrategy):
    @property
    def task_category(self) -> str:
        return 'IO'
        
    async def process(self, worker, task: Task, db: Session) -> Dict[str, Any]:
        payload = task.payload or {}
        target_root_path = payload.get('target_root_path')
        prefix = payload.get('prefix', 'IMG_')
        suffix = payload.get('suffix', '')
        
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
        
        success_count = 0
        
        # Group by time to handle collisions
        time_groups = {}
        for p in target_photos:
            t = p.photo_time or p.upload_time
            if not t:
                # Fallback if somehow no time is available
                t_str = "UNKNOWN_TIME"
            else:
                t_str = t.strftime('%Y%m%d_%H%M%S')
                
            if t_str not in time_groups:
                time_groups[t_str] = []
            time_groups[t_str].append(p)
            
        processed = 0
        for t_str, group in time_groups.items():
            for i, p in enumerate(group):
                old_path = p.file_path
                dir_name = os.path.dirname(old_path)
                _, ext = os.path.splitext(old_path)
                
                # Base name: {prefix}{YYYYMMDD_HHMMSS}{suffix}
                # If multiple photos have the same time, append (1), (2)...
                collision_suffix = f"({i+1})" if len(group) > 1 else ""
                
                new_basename = f"{prefix}{t_str}{suffix}{collision_suffix}{ext}"
                new_path = os.path.join(dir_name, new_basename)
                
                if os.path.abspath(old_path) != os.path.abspath(new_path):
                    # Handle edge case where the generated name already exists on disk from another process
                    counter = i + 1
                    while os.path.exists(new_path):
                        counter += 1
                        collision_suffix = f"({counter})"
                        new_basename = f"{prefix}{t_str}{suffix}{collision_suffix}{ext}"
                        new_path = os.path.join(dir_name, new_basename)
                        
                    try:
                        os.rename(old_path, new_path)
                        p.file_path = new_path
                        p.filename = new_basename
                        success_count += 1
                    except Exception as e:
                        logging.error(f"Failed to rename {old_path} to {new_path}: {e}")
                else:
                    # Name is already correct
                    pass
                    
                processed += 1
                task.processed_items = processed
                
                if processed % 50 == 0:
                    db.commit()
                    
        db.commit()
        return {"success_count": success_count, "total_processed": len(target_photos)}