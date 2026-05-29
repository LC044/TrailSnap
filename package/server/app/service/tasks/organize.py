import os
import shutil
import uuid
import logging
from typing import Dict, Any
from sqlalchemy.orm import Session, joinedload
from app.db.models.task import Task, TaskType
from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory
from app.db.models.photo import Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.tag import PhotoTag
from app.db.models.face import Face

@TaskStrategyFactory.register(TaskType.ORGANIZE_PHOTOS)
class OrganizePhotosStrategy(BaseTaskStrategy):
    @property
    def task_category(self) -> str:
        return 'IO'
        
    async def process(self, worker, task: Task, db: Session) -> Dict[str, Any]:
        payload = task.payload or {}
        target_root_path = payload.get('target_root_path')
        strategy = payload.get('strategy')
        action = payload.get('action')
        time_granularity = payload.get('time_granularity', 'ym')
        time_format = payload.get('time_format', 'flat')
        location_granularity = payload.get('location_granularity', 'city')
        location_format = payload.get('location_format', 'flat')
        
        time_range = payload.get('time_range')
        categories = payload.get('categories')
        people = payload.get('people')
        locations = payload.get('locations')
        
        if not target_root_path or not strategy or not action:
            raise ValueError("Missing required parameters in task payload")
            
        abs_target = os.path.abspath(target_root_path)
        os.makedirs(abs_target, exist_ok=True)
        
        # Load photos with relations based on strategy
        query = db.query(Photo).filter(Photo.owner_id == task.owner_id, Photo.is_deleted.is_(False))
        if strategy == 'category':
            query = query.options(joinedload(Photo.tags))
        elif strategy == 'person':
            query = query.options(joinedload(Photo.faces).joinedload(Face.identity))
        elif strategy == 'location':
            query = query.options(joinedload(Photo.metadata_info))
            
        photos = query.all()
        task.total_items = len(photos)
        db.commit()
        
        success_count = 0
        
        for i, photo in enumerate(photos):
            old_path = photo.file_path
            if not old_path or not os.path.exists(old_path):
                task.processed_items = i + 1
                if i % 100 == 0:
                    db.commit()
                continue
                
            subfolders = []
            
            if strategy == 'time':
                t = photo.photo_time or photo.upload_time
                if t:
                    if time_range and len(time_range) == 2:
                        t_str = t.strftime('%Y-%m-%d %H:%M:%S')
                        end_time = time_range[1] if len(time_range[1]) > 10 else time_range[1] + " 23:59:59"
                        if not (time_range[0] <= t_str <= end_time):
                            task.processed_items = i + 1
                            continue
                            
                    if time_granularity == 'ym':
                        if time_format == 'nested':
                            subfolders.append(os.path.join(t.strftime('%Y'), t.strftime('%m')))
                        else:
                            subfolders.append(t.strftime('%Y-%m'))
                    elif time_granularity == 'ymd':
                        if time_format == 'nested':
                            subfolders.append(os.path.join(t.strftime('%Y'), t.strftime('%m'), t.strftime('%d')))
                        else:
                            subfolders.append(t.strftime('%Y-%m-%d'))
                else:
                    if time_range and len(time_range) == 2:
                        task.processed_items = i + 1
                        continue
                    subfolders.append('未知时间')
            elif strategy == 'category':
                if photo.tags:
                    # Sort by confidence
                    sorted_tags = sorted(photo.tags, key=lambda x: getattr(x, 'confidence', 0), reverse=True)
                    if action == 'move':
                        subfolders.append(sorted_tags[0].tag_name)
                    else:
                        subfolders.extend([t.tag_name for t in sorted_tags])
                else:
                    subfolders.append('未分类')
                    
                if categories is not None:
                    subfolders = [s for s in subfolders if s in categories]
            elif strategy == 'person':
                valid_faces = [f for f in photo.faces if f.identity and f.identity.identity_name]
                if valid_faces:
                    sorted_faces = sorted(valid_faces, key=lambda x: getattr(x, 'confidence', 0), reverse=True)
                    if action == 'move':
                        subfolders.append(sorted_faces[0].identity.identity_name)
                    else:
                        # unique names
                        names = set()
                        for f in sorted_faces:
                            names.add(f.identity.identity_name)
                        subfolders.extend(list(names))
                else:
                    subfolders.append('未命名')
                    
                if people is not None:
                    subfolders = [s for s in subfolders if s in people]
            elif strategy == 'location':
                m = photo.metadata_info
                if m and (m.province or m.city or m.district):
                    parts = []
                    if location_granularity == 'province' and m.province:
                        parts.append(m.province)
                    elif location_granularity == 'city' and m.city:
                        parts.append(m.city)
                    elif location_granularity == 'district' and m.district:
                        parts.append(m.district)
                    elif location_granularity == 'province_city':
                        if m.province: parts.append(m.province)
                        if m.city and (not parts or parts[-1] != m.city): parts.append(m.city)
                    elif location_granularity == 'city_district':
                        if m.city: parts.append(m.city)
                        if m.district and (not parts or parts[-1] != m.district): parts.append(m.district)
                    elif location_granularity == 'province_city_district':
                        if m.province: parts.append(m.province)
                        if m.city and (not parts or parts[-1] != m.city): parts.append(m.city)
                        if m.district and (not parts or parts[-1] != m.district): parts.append(m.district)
                    
                    if not parts:
                        subfolders.append('未知位置')
                    else:
                        if location_format == 'nested':
                            subfolders.append(os.path.join(*parts))
                        else:
                            subfolders.append("-".join(parts))
                else:
                    subfolders.append('未知位置')
                    
                if locations is not None:
                    # Filter based on the generated folder names
                    subfolders = [s for s in subfolders if s in locations]
                    
            # Deduplicate subfolders
            subfolders = list(set(subfolders))
            
            for subfolder in subfolders:
                # Sanitize subfolder name, but allow directory separators
                safe_subfolder = "".join([c for c in subfolder if c not in r':*?"<>|'])
                if not safe_subfolder:
                    safe_subfolder = "未命名"
                    
                folder_path = os.path.join(abs_target, safe_subfolder)
                os.makedirs(folder_path, exist_ok=True)
                
                filename = os.path.basename(old_path)
                new_path = os.path.join(folder_path, filename)
                
                # Collision handling
                if os.path.exists(new_path) and os.path.abspath(old_path) != os.path.abspath(new_path):
                    base, ext = os.path.splitext(filename)
                    new_path = os.path.join(folder_path, f"{base}_{uuid.uuid4().hex[:8]}{ext}")
                    
                if action == 'move':
                    if os.path.abspath(old_path) != os.path.abspath(new_path):
                        try:
                            shutil.move(old_path, new_path)
                            photo.file_path = new_path
                            photo.filename = os.path.basename(new_path)
                            # After move, break out of subfolder loop since we can only move once
                            success_count += 1
                            break
                        except Exception as e:
                            logging.error(f"Failed to move {old_path} to {new_path}: {e}")
                elif action == 'copy':
                    if os.path.abspath(old_path) != os.path.abspath(new_path):
                        try:
                            shutil.copy2(old_path, new_path)
                            # Create new DB record
                            new_photo_data = {c.name: getattr(photo, c.name) for c in photo.__table__.columns if c.name not in ['id', 'file_path', 'filename', 'created_at', 'updated_at']}
                            new_photo = Photo(
                                id=uuid.uuid4(),
                                file_path=new_path,
                                filename=os.path.basename(new_path),
                                **new_photo_data
                            )
                            db.add(new_photo)
                            worker.get_instance().add_task(db, TaskType.GENERATE_THUMBNAIL, {'photo_id': str(new_photo.id)})
                            success_count += 1
                        except Exception as e:
                            logging.error(f"Failed to copy {old_path} to {new_path}: {e}")
                            
            task.processed_items = i + 1
            if i % 50 == 0:
                db.commit()
                
        db.commit()
        return {"success_count": success_count, "total_processed": len(photos)}