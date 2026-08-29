from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory
from app.db.models.task import TaskType
from typing import List, Dict
import logging
import aiohttp
from aiohttp import FormData
import json
from sqlalchemy.orm import Session
from app.db.models.task import Task, TaskType
from app.db.models.photo import Photo, FileType
from app.db.models.ocr import OCR
from typing import Dict, Any, List
from app.crud import ocr as crud_ocr
from app.core.config_manager import config_manager
from PIL import Image

from app.schemas.ocr import OCRCreate
from app.service.tasks.ci_limit import is_ci, ci_task_limit_reached, ci_remaining_budget, CI_TASK_PHOTO_LIMIT

logger = logging.getLogger(__name__)


@TaskStrategyFactory.register(TaskType.OCR)
class OcrStrategy(BaseTaskStrategy):
    @property
    def task_category(self) -> str:
        return 'AI'

    @property
    def resource_key(self) -> str:
        return 'ocr'

    async def process(self, worker, task: Task, db: Session) -> Dict[str, Any]:
        """
        Handle OCR task
        """
        try:
            force = task.payload.get('force', False)
            
            # 1. Single Photo Mode
            if task.payload and 'photo_id' in task.payload:
                photo_id = task.payload['photo_id']
                photo = db.query(Photo).filter(Photo.id == photo_id).first()
                if not photo:
                    return {'status': 'skipped', 'reason': 'photo not found'}
                
                # Check if already processed (unless force)
                if not force:
                    tasks_status = photo.processed_tasks or {}
                    if tasks_status.get('ocr'):
                         return {'status': 'skipped', 'reason': 'already processed'}

                # CI 限速：最多处理 5 张照片，已达上限直接跳过
                if ci_task_limit_reached(db, OCR):
                    return {'status': 'skipped', 'reason': f'CI ocr limit reached ({CI_TASK_PHOTO_LIMIT} photos)'}

                return await self.process_single_photo(worker, photo, db)

            # 2. Generator Mode (Scan all)
            photos_to_process = []
            batch_size = 1000
            offset = 0
            
            generated_count = 0
            # CI 限速：只生成到上限为止的子任务，避免入队大量会被跳过的任务
            remaining = ci_remaining_budget(db, OCR)

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
                        if not tasks_status.get('ocr'):
                            should_process = True
                    
                    if should_process:
                        if remaining is not None and generated_count >= remaining:
                            break
                        tasks_to_create.append({
                            'type': TaskType.OCR,
                            'payload': {'photo_id': str(p.id), 'force': force, 'file_path': p.file_path},
                            'priority': 1,
                            'owner_id': p.owner_id
                        })

                if tasks_to_create:
                    worker.add_tasks(db, tasks_to_create)
                    generated_count += len(tasks_to_create)

                offset += batch_size

                if remaining is not None and generated_count >= remaining:
                    break

            return {
                'processed': 0,
                'generated_tasks': generated_count,
                'message': f'Generated {generated_count} OCR tasks'
            }

        except Exception as e:
            logger.error(f"OCR task failed: {e}")
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
        from app.service import storage
        for owner_id, owner_tasks in tasks_by_owner.items():
            try:
                photo_ids = [t.payload['photo_id'] for t in owner_tasks]
                photos = db.query(Photo).filter(Photo.id.in_(photo_ids)).all()
                photo_map = {str(p.id): p for p in photos}
                
                valid_tasks = []
                b64_images = []
                valid_photos = []
                dimensions = []
                
                for task in owner_tasks:
                    photo_id = str(task.payload['photo_id'])
                    photo = photo_map.get(photo_id)
                    force = task.payload.get('force', False)
                    
                    if not photo:
                        results.append({'task_id': task.id, 'task_type': task.type, 'status': 'completed', 'result': {'status': 'skipped', 'reason': 'photo not found'}})
                        continue
                        
                    if not force:
                        tasks_status = photo.processed_tasks or {}
                        if tasks_status.get('ocr'):
                            results.append({'task_id': task.id, 'task_type': task.type, 'status': 'completed', 'result': {'status': 'skipped', 'reason': 'already processed'}})
                            continue

                    # CI 限速：最多处理 5 张照片，已达上限直接跳过（不调 AI 服务）
                    if ci_task_limit_reached(db, OCR):
                        results.append({'task_id': task.id, 'task_type': task.type, 'status': 'completed', 'result': {'status': 'skipped', 'reason': f'CI ocr limit reached ({CI_TASK_PHOTO_LIMIT} photos)'}})
                        continue

                    target_path = storage.get_available_photo_path(photo.owner_id, photo.id, photo.file_path)
                    if not target_path:
                        results.append({'task_id': task.id, 'task_type': task.type, 'status': 'failed', 'error': 'file not found'})
                        continue
                        
                    try:
                        with Image.open(target_path) as img:
                            width, height = img.size
                        with open(target_path, 'rb') as f_img:
                            b64_data = base64.b64encode(f_img.read()).decode('utf-8')
                        b64_images.append(b64_data)
                        valid_tasks.append(task)
                        valid_photos.append(photo)
                        dimensions.append((width, height))
                    except Exception as e:
                        results.append({'task_id': task.id, 'task_type': task.type, 'status': 'failed', 'error': f'read file error: {e}'})

                if not valid_tasks:
                    continue

                api_url = f"{config_manager.get_user_config(owner_id, db).ai.ai_api_url}/ocr/predict"
                async with aiohttp.ClientSession() as session:
                    async with session.post(api_url, json={"images": b64_images}, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                        if resp.status == 200:
                            result_data = await resp.json()
                            # AI 返回 {"results": [{"ocrResults": [...], "dataInfo": [], "error"?: ...}, ...]}
                            ai_results = result_data.get('results', [])

                            for idx, task in enumerate(valid_tasks):
                                photo = valid_photos[idx]
                                width, height = dimensions[idx]
                                res_item = ai_results[idx] if idx < len(ai_results) else {}

                                # 单张图片在 AI 服务侧处理失败：标记任务失败，跳过该照片
                                if res_item.get('error'):
                                    results.append({
                                        'task_id': task.id,
                                        'task_type': task.type,
                                        'status': 'failed',
                                        'error': res_item.get('error')
                                    })
                                    continue

                                # ocrResults 是 list（detect_text 返回单元素列表），取第一个
                                ocr_list = res_item.get('ocrResults', [])
                                ocr_item = ocr_list[0] if ocr_list else {}
                                pruned_result = ocr_item.get('prunedResult', {})
                                rec_texts = pruned_result.get('rec_texts', [])
                                rec_scores = pruned_result.get('rec_scores', [])
                                rec_polys = pruned_result.get('rec_polys', [])

                                crud_ocr.delete_ocr_by_photo_id(db, photo.id)
                                count = 0
                                
                                for i, text in enumerate(rec_texts):
                                    score = rec_scores[i] if i < len(rec_scores) else 0.0
                                    poly = rec_polys[i] if i < len(rec_polys) else []
                                    norm_poly = []
                                    if width and height and width > 0 and height > 0:
                                        for point in poly:
                                            norm_poly.append([
                                                point[0] / width,
                                                point[1] / height
                                            ])
                                    else:
                                        norm_poly = poly
                                        
                                    crud_ocr.create_ocr(
                                        db,
                                        OCRCreate(
                                            photo_id=photo.id,
                                            text=text,
                                            text_score=score,
                                            polygon=norm_poly
                                        )
                                    )
                                    count += 1
                                tasks_status = dict(photo.processed_tasks or {})
                                tasks_status['ocr'] = True
                                photo.processed_tasks = tasks_status
                                db.add(photo)
                                db.commit()

                                results.append({
                                    'task_id': task.id,
                                    'task_type': task.type,
                                    'status': 'completed',
                                    'result': {'status': 'success', 'texts_found': count}
                                })
                        else:
                            err_msg = f"AI Service error: {resp.status}"
                            for task in valid_tasks:
                                results.append({'task_id': task.id, 'task_type': task.type, 'status': 'failed', 'error': err_msg})

            except Exception as e:
                logger.error(f"Error in OCR processing batch for owner {owner_id}: {e}")
                for task in owner_tasks:
                    if not any(r['task_id'] == task.id for r in results):
                        results.append({'task_id': task.id, 'task_type': task.type, 'status': 'failed', 'error': str(e)})

        return results
    async def process_single_photo(self, worker, photo: Photo, db: Session) -> Dict[str, Any]:
        from app.service import storage

        try:
            # 1. Resolve file path
            target_path = storage.get_available_photo_path(photo.owner_id, photo.id, photo.file_path)
            if not target_path:
                return {'status': 'failed', 'error': 'file not found'}

            # 读取图片实际宽高
            with Image.open(target_path) as img:
                width, height = img.size

            async with aiohttp.ClientSession() as session:
                # 1. Read file
                with open(target_path, 'rb') as f:
                    file_data = f.read()

                import base64
                b64_data = base64.b64encode(file_data).decode('utf-8')
                json_data = {"images": [b64_data]}

                # 3. Call AI Service
                # Assuming AI service has /ocr/predict endpoint
                api_url = f"{config_manager.get_user_config(photo.owner_id, db).ai.ai_api_url}/ocr/predict"
                async with session.post(
                    api_url,
                    json=json_data,
                    timeout=aiohttp.ClientTimeout(total=60) # OCR might be slow
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        # Response structure:
                        # {
                        #   "results": [
                        #     {"ocrResults": [{"prunedResult": {...}}], "dataInfo": [], "error"?: ...}
                        #   ]
                        # }
                        results_arr = result.get('results', [])
                        res_item = results_arr[0] if results_arr else {}

                        # 单张图片在 AI 服务侧处理失败：直接返回失败，避免写入空结果
                        if res_item.get('error'):
                            return {'status': 'failed', 'error': res_item.get('error')}

                        ocr_list = res_item.get('ocrResults', [])
                        ocr_results = ocr_list[0] if ocr_list else {}
                        pruned_result = ocr_results.get('prunedResult', {})
                        rec_texts = pruned_result.get('rec_texts', [])
                        rec_scores = pruned_result.get('rec_scores', [])
                        rec_polys = pruned_result.get('rec_polys', [])

                        # Clean up old OCR results for this photo
                        crud_ocr.delete_ocr_by_photo_id(db, photo.id)

                        count = 0

                        for i, text in enumerate(rec_texts):
                            score = rec_scores[i] if i < len(rec_scores) else 0.0
                            poly = rec_polys[i] if i < len(rec_polys) else []
                            # Normalize polygon
                            norm_poly = []
                            if width and height and width > 0 and height > 0:
                                for point in poly:
                                    norm_poly.append([
                                        point[0] / width,
                                        point[1] / height
                                    ])
                            else:
                                # If no dimensions, store absolute or 0?
                                # User requested relative coordinates.
                                # We'll skip normalization if dimensions are missing,
                                # but frontend might expect 0-1.
                                # Let's hope dimensions are there.
                                norm_poly = poly

                            ocr_record = crud_ocr.create_ocr(
                                db,
                                OCRCreate(
                                    photo_id=photo.id,
                                    text=text,
                                    text_score=score,
                                    polygon=norm_poly
                                )
                            )
                            count += 1

                        # Update Status
                        tasks_status = dict(photo.processed_tasks or {})
                        tasks_status['ocr'] = True
                        photo.processed_tasks = tasks_status
                        db.add(photo)
                        db.commit()
                        # Use a separate counter or just log
                        # worker.scan_status['processed_files'] += 1
                        return {'status': 'success', 'texts_found': count}
                    else:
                        return {'status': 'failed', 'error': f"AI Service error: {resp.status}"}
        except Exception as e:
            logger.error(f"Error processing OCR for photo {photo.id}: {e}")
            tasks_status = dict(photo.processed_tasks or {})
            tasks_status['ocr'] = False
            photo.processed_tasks = tasks_status
            db.add(photo)
            db.commit()
            raise e

    def release_resources(self) -> None:
        pass
