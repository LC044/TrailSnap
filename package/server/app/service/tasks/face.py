from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory
from app.db.models.task import TaskType
from typing import List, Dict
import logging
import os
import aiohttp
from aiohttp import FormData
from sqlalchemy.orm import Session
from app.db.models.task import Task, TaskType
from app.db.models.photo import Photo, FileType
from app.db.models.face import Face
from app.service.face_cluster import FaceClusterService, crud_face
from typing import Dict, Any, List
from app.core.config_manager import config_manager
from app.service import storage

logger = logging.getLogger(__name__)

@TaskStrategyFactory.register(TaskType.RECOGNIZE_FACE)
class RecognizeFaceStrategy(BaseTaskStrategy):
    @property
    def task_category(self) -> str:
        return 'IO'

    async def process(self, worker, task: Task, db: Session) -> Dict[str, Any]:
        try:
            force = task.payload.get('force', False)
            
            if task.payload and 'photo_id' in task.payload:
                photo_id = task.payload['photo_id']
                photo = db.query(Photo).filter(Photo.id == photo_id).first()
                if not photo:
                    return {'status': 'skipped', 'reason': 'photo not found'}
                
                if not force:
                    tasks_status = photo.processed_tasks or {}
                    if tasks_status.get('face'):
                         return {'status': 'skipped', 'reason': 'already processed'}

                return await self.process_single_photo(worker, photo, db)

            # Generator Mode
            batch_size = 1000
            offset = 0
            generated_count = 0
            
            while True:
                batch = db.query(Photo).offset(offset).limit(batch_size).all()
                if not batch:
                    break

                tasks_to_create = []
                for p in batch:
                    if p.file_type == FileType.video:
                        continue
                    
                    should_process = False
                    if force:
                        should_process = True
                    else:
                        tasks_status = p.processed_tasks or {}
                        if not tasks_status.get('face'):
                            should_process = True
                    
                    if should_process:
                        tasks_to_create.append({
                            'type': TaskType.RECOGNIZE_FACE,
                            'payload': {'photo_id': str(p.id), 'force': force, 'file_path': p.file_path},
                            'priority': 2,
                            'owner_id': p.owner_id
                        })

                if tasks_to_create:
                    worker.add_tasks(db, tasks_to_create)
                    generated_count += len(tasks_to_create)

                offset += batch_size

            return {
                'processed': 0,
                'generated_tasks': generated_count,
                'message': f'Generated {generated_count} face recognition tasks'
            }

        except Exception as e:
            logger.error(f"Face task failed: {e}")
            raise e


    async def process_batch(self, worker, tasks: List[Task], db: Session) -> List[Dict]:
        results = []
        generator_tasks = []
        photo_tasks = []

        for task in tasks:
            if task.payload and 'photo_id' in task.payload:
                photo_tasks.append(task)
            else:
                generator_tasks.append(task)

        # Process generator tasks normally
        for task in generator_tasks:
            try:
                res = await self.process(worker, task, db)
                results.append({
                    'task_id': task.id,
                    'task_type': task.type,
                    'status': 'failed' if res and isinstance(res, dict) and res.get('status') == 'failed' else 'completed',
                    'result': res,
                    'error': res.get('error') if res and isinstance(res, dict) else None
                })
            except Exception as e:
                logger.error(f"Error processing generator task {task.id}: {e}")
                results.append({
                    'task_id': task.id,
                    'task_type': task.type,
                    'status': 'failed',
                    'error': str(e)
                })

        if not photo_tasks:
            return results

        # Group photo tasks by owner_id
        tasks_by_owner = {}
        for task in photo_tasks:
            owner_id = task.owner_id
            if owner_id not in tasks_by_owner:
                tasks_by_owner[owner_id] = []
            tasks_by_owner[owner_id].append(task)

        import base64
        for owner_id, owner_tasks in tasks_by_owner.items():
            try:
                photo_ids = [t.payload['photo_id'] for t in owner_tasks]
                photos = db.query(Photo).filter(Photo.id.in_(photo_ids)).all()
                photo_map = {str(p.id): p for p in photos}
                
                # Filter out already processed if not force
                valid_tasks = []
                b64_images = []
                valid_photos = []

                for task in owner_tasks:
                    photo_id = str(task.payload['photo_id'])
                    photo = photo_map.get(photo_id)
                    force = task.payload.get('force', False)

                    if not photo:
                        results.append({'task_id': task.id, 'task_type': task.type, 'status': 'completed', 'result': {'status': 'skipped', 'reason': 'photo not found'}})
                        continue

                    if not force:
                        tasks_status = photo.processed_tasks or {}
                        if tasks_status.get('face'):
                            results.append({'task_id': task.id, 'task_type': task.type, 'status': 'completed', 'result': {'status': 'skipped', 'reason': 'already processed'}})
                            continue

                    target_path = storage.get_preview_path(photo.owner_id, photo.id)
                    if not os.path.exists(target_path):
                        target_path = photo.file_path

                    if not target_path or not os.path.exists(target_path):
                        results.append({'task_id': task.id, 'task_type': task.type, 'status': 'failed', 'error': 'file not found'})
                        continue

                    try:
                        with open(target_path, 'rb') as f_img:
                            b64_data = base64.b64encode(f_img.read()).decode('utf-8')
                        b64_images.append(b64_data)
                        valid_tasks.append(task)
                        valid_photos.append(photo)
                    except Exception as e:
                        results.append({'task_id': task.id, 'task_type': task.type, 'status': 'failed', 'error': f'read file error: {e}'})

                if not valid_tasks:
                    continue

                # Batch AI request
                api_url = f"{config_manager.get_user_config(owner_id, db).ai.ai_api_url}/face/face-recognition"
                async with aiohttp.ClientSession() as session:
                    async with session.post(api_url, json={"images": b64_images}) as resp:
                        if resp.status == 200:
                            result_data = await resp.json()
                            ai_results = result_data.get('results', [])

                            cluster_service = FaceClusterService(db, owner_id)
                            threshold = config_manager.get_user_config(owner_id, db).ai.face_recognition_threshold

                            for idx, task in enumerate(valid_tasks):
                                photo = valid_photos[idx]
                                ai_result = ai_results[idx] if idx < len(ai_results) else {}

                                # 单张图片在 AI 服务侧处理失败：标记任务失败，跳过该照片
                                if ai_result.get('error'):
                                    results.append({
                                        'task_id': task.id,
                                        'task_type': task.type,
                                        'status': 'failed',
                                        'error': ai_result.get('error')
                                    })
                                    continue

                                faces_data = ai_result.get('faces', [])
                                crud_face.delete_faces_by_photo(db, photo.id)

                                count = 0
                                has_unassigned = False

                                for face_data in faces_data:
                                    if face_data.get('det_score') < threshold:
                                        continue

                                    bbox = face_data.get('bbox')
                                    face = Face(
                                        photo_id=photo.id,
                                        face_feature=face_data.get('embedding'),
                                        face_rect=bbox,
                                        face_confidence=face_data.get('det_score'),
                                        recognize_confidence=0.0
                                    )
                                    db.add(face)
                                    db.flush()
                                    count += 1
                                    if face.face_feature:
                                        try:
                                            assigned_id = cluster_service.assign_face_to_identity(face.id, face.face_feature)
                                            if not assigned_id:
                                                has_unassigned = True
                                        except Exception as ce:
                                            logger.error(f"Clustering failed for face {face.id}: {ce}")
                                if has_unassigned:
                                    db.commit()
                                    try:
                                        cluster_service.process_unassigned_faces(owner_id)
                                    except Exception as ce:
                                        logger.error(f"Batch clustering failed: {ce}")
                                        
                                tasks_status = dict(photo.processed_tasks or {})
                                tasks_status['face'] = True
                                photo.processed_tasks = tasks_status
                                db.add(photo)
                                db.commit()
                                
                                if photo.owner_id:
                                    from app.crud.album import trigger_conditional_albums_update
                                    trigger_conditional_albums_update(db, photo.owner_id, [photo.id])
                                    
                                results.append({
                                    'task_id': task.id,
                                    'task_type': task.type,
                                    'status': 'completed',
                                    'result': {'status': 'success', 'faces_found': count}
                                })
                        else:
                            err_msg = f"AI Service error: {resp.status}"
                            for task in valid_tasks:
                                results.append({'task_id': task.id, 'task_type': task.type, 'status': 'failed', 'error': err_msg})
                                
            except Exception as e:
                logger.error(f"Error in Face Recognition processing batch for owner {owner_id}: {e}")
                for task in owner_tasks:
                    if not any(r['task_id'] == task.id for r in results):
                        results.append({'task_id': task.id, 'task_type': task.type, 'status': 'failed', 'error': str(e)})

        return results
    async def process_single_photo(self, worker, photo: Photo, db: Session) -> Dict[str, Any]:
        try:
            cluster_service = FaceClusterService(db, photo.owner_id)
            target_path = storage.get_preview_path(photo.owner_id, photo.id)
            if not os.path.exists(target_path):
                target_path = photo.file_path
                if not target_path or not os.path.exists(target_path):
                    return {'status': 'failed', 'error': 'file not found'}

            async with aiohttp.ClientSession() as session:
                with open(target_path, 'rb') as f:
                    file_data = f.read()
                width, height, _ = storage.get_image_dimensions(target_path)

                import base64
                b64_data = base64.b64encode(file_data).decode('utf-8')
                json_data = {"images": [b64_data]}

                api_url = f"{config_manager.get_user_config(photo.owner_id, db).ai.ai_api_url}/face/face-recognition"
                async with session.post(api_url, json=json_data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        results = result.get('results', [])
                        ai_result = results[0] if results else {}

                        # 单张图片在 AI 服务侧处理失败：直接返回失败，避免被当成 0 人脸成功
                        if ai_result.get('error'):
                            return {'status': 'failed', 'error': ai_result.get('error')}

                        faces = ai_result.get('faces', [])

                        # Clean up old faces
                        crud_face.delete_faces_by_photo(db, photo.id)

                        count = 0
                        has_unassigned = False
                        for face_data in faces:
                            if face_data.get('det_score') < config_manager.get_user_config(photo.owner_id, db).ai.face_recognition_threshold:
                                continue

                            # Normalize face_rect (bbox) to 0-1 relative coordinates
                            bbox = face_data.get('bbox')
                            face = Face(
                                photo_id=photo.id,
                                face_feature=face_data.get('embedding'),
                                face_rect=bbox,
                                face_confidence=face_data.get('det_score'),
                                recognize_confidence=0.0 # Placeholder
                            )
                            db.add(face)
                            # Flush to get ID
                            db.flush()

                            count += 1
                            if face.face_feature:
                                try:
                                    assigned_id = cluster_service.assign_face_to_identity(face.id, face.face_feature)
                                    if not assigned_id:
                                        has_unassigned = True
                                except Exception as ce:
                                    logging.error(f"Clustering failed for face {face.id}: {ce}")

                        if has_unassigned:
                             # Commit faces first to ensure they exist for clustering
                             db.commit()
                             try:
                                 cluster_service.process_unassigned_faces(photo.owner_id)
                             except Exception as ce:
                                 logging.error(f"Batch clustering failed: {ce}")

                        tasks_status = dict(photo.processed_tasks or {})
                        tasks_status['face'] = True
                        photo.processed_tasks = tasks_status
                        db.add(photo)
                        db.commit()
                        
                        if photo.owner_id:
                            from app.crud.album import trigger_conditional_albums_update
                            trigger_conditional_albums_update(db, photo.owner_id, [photo.id])
                            
                        return {'status': 'success', 'faces_found': count}
                    else:
                        return {'status': 'failed', 'error': f"AI Service error: {resp.status}"}
        except Exception as e:
            logger.error(f"Error processing Face for photo {photo.id}: {e}")
            tasks_status = dict(photo.processed_tasks or {})
            tasks_status['face'] = False
            photo.processed_tasks = tasks_status
            db.add(photo)
            db.commit()
            raise e

    def release_resources(self) -> None:
        pass
