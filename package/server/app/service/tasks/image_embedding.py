from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory
from app.db.models.task import TaskType
from typing import List, Dict
import logging
import aiohttp
from sqlalchemy.orm import Session
from app.db.models.task import Task, TaskType
from app.db.models.photo import Photo, FileType
from app.db.models.image_vector import ImageVector
from typing import Dict, Any, List
from app.core.config_manager import config_manager
from app.service import storage

logger = logging.getLogger(__name__)

@TaskStrategyFactory.register(TaskType.IMAGE_EMBEDDING)
class ImageEmbeddingStrategy(BaseTaskStrategy):
    @property
    def task_category(self) -> str:
        return 'AI'

    @property
    def resource_key(self) -> str:
        return 'embedding'

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
                    if tasks_status.get('image_embedding'):
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
                        if not tasks_status.get('image_embedding'):
                            should_process = True
                    
                    if should_process:
                        tasks_to_create.append({
                            'type': TaskType.IMAGE_EMBEDDING,
                            'payload': {'photo_id': str(p.id), 'force': force},
                            'priority': 3,
                            'owner_id': p.owner_id
                        })

                if tasks_to_create:
                    worker.add_tasks(db, tasks_to_create)
                    generated_count += len(tasks_to_create)

                offset += batch_size

            return {
                'processed': 0,
                'generated_tasks': generated_count,
                'message': f'Generated {generated_count} image embedding tasks'
            }

        except Exception as e:
            logger.error(f"Image embedding task failed: {e}")
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
                    target_path = storage.get_available_photo_path(photo.owner_id, photo.id, photo.file_path)
                    if not target_path:
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

                api_url = f"{config_manager.get_user_config(owner_id, db).ai.ai_api_url}/embedding/image"
                async with aiohttp.ClientSession() as session:
                    async with session.post(api_url, json={"images": b64_images}) as resp:
                        if resp.status == 200:
                            ai_results = await resp.json() # List[List[float]]
                            
                            for idx, task in enumerate(valid_tasks):
                                photo = valid_photos[idx]
                                embedding = ai_results[idx] if idx < len(ai_results) else []
                                
                                if embedding:
                                    vector = db.query(ImageVector).filter(ImageVector.photo_id == photo.id).first()
                                    if not vector:
                                        vector = ImageVector(photo_id=photo.id)
                                        db.add(vector)
                                    vector.embedding = embedding
                                    
                                    tasks_status = dict(photo.processed_tasks or {})
                                    tasks_status['image_embedding'] = True
                                    photo.processed_tasks = tasks_status
                                    db.add(photo)
                                    db.commit()
                                    
                                    results.append({
                                        'task_id': task.id,
                                        'task_type': task.type,
                                        'status': 'completed',
                                        'result': {'status': 'success', 'embedding_size': len(embedding)}
                                    })
                                else:
                                    results.append({
                                        'task_id': task.id,
                                        'task_type': task.type,
                                        'status': 'failed',
                                        'error': 'No embedding returned'
                                    })
                        else:
                            err_msg = f"AI Service error: {resp.status} {await resp.text()}"
                            for task in valid_tasks:
                                results.append({'task_id': task.id, 'task_type': task.type, 'status': 'failed', 'error': err_msg})
                                
            except Exception as e:
                logger.error(f"Error in Image Embedding processing batch for owner {owner_id}: {e}")
                for task in owner_tasks:
                    if not any(r['task_id'] == task.id for r in results):
                        results.append({'task_id': task.id, 'task_type': task.type, 'status': 'failed', 'error': str(e)})

        return results

    async def process_single_photo(self, worker, photo: Photo, db: Session) -> Dict[str, Any]:
        try:
            target_path = storage.get_available_photo_path(photo.owner_id, photo.id, photo.file_path)
            if not target_path:
                return {'status': 'failed', 'error': 'file not found'}

            async with aiohttp.ClientSession() as session:
                with open(target_path, 'rb') as f:
                    file_data = f.read()

                import base64
                b64_data = base64.b64encode(file_data).decode('utf-8')
                json_data = {"images": [b64_data]}

                api_url = f"{config_manager.get_user_config(photo.owner_id, db).ai.ai_api_url}/embedding/image"
                async with session.post(api_url, json=json_data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        # Response is List[List[float]]
                        if result and len(result) > 0:
                            embedding = result[0]
                            
                            # Save Embedding
                            vector = db.query(ImageVector).filter(ImageVector.photo_id == photo.id).first()
                            if not vector:
                                vector = ImageVector(photo_id=photo.id)
                                db.add(vector)
                            vector.embedding = embedding

                            tasks_status = dict(photo.processed_tasks or {})
                            tasks_status['image_embedding'] = True
                            photo.processed_tasks = tasks_status
                            db.add(photo)
                            db.commit()
                            return {'status': 'success', 'embedding_size': len(embedding)}
                        else:
                            return {'status': 'failed', 'error': 'No embedding returned'}
                    else:
                        text = await resp.text()
                        logger.error(f"AI Service error: {resp.status} {text}")
                        return {'status': 'failed', 'error': f"AI Service error: {resp.status}"}
        except Exception as e:
            logger.error(f"Error processing Image Embedding for photo {photo.id}: {e}")
            tasks_status = dict(photo.processed_tasks or {})
            tasks_status['image_embedding'] = False
            photo.processed_tasks = tasks_status
            db.add(photo)
            db.commit()
            raise e

    def release_resources(self) -> None:
        pass
