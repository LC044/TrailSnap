from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory
from app.db.models.task import TaskType, DEFAULT_PRIORITIES
from typing import List, Dict
import logging
import os
import json
import base64
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from langchain_openai import ChatOpenAI

from app.db.models import PhotoMetadata
from app.db.models.task import Task, TaskType
from app.db.models.photo import Photo, FileType, ImageType
from app.db.models.image_description import ImageDescription
from app.core.config_manager import config_manager
from app.service import storage
from app.utils.path import get_user_roots, compute_browse_path

logger = logging.getLogger(__name__)


import io
from PIL import Image

def encode_image(image_path, max_size=672):
    with Image.open(image_path) as img:
        # 缩放：长边缩放到 max_size(896)，保持比例
        width, height = img.size
        if max(width, height) > max_size:
            # 计算缩放比例
            ratio = max_size / max(width, height)
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            # 高质量缩放
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # 处理 WEBP / PNG 透明图
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # 保存到内存并转 JPEG（进一步降低体积）
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        base64_str = base64.b64encode(buffer.getvalue()).decode('utf-8')

    return base64_str


@TaskStrategyFactory.register(TaskType.VISUAL_DESCRIPTION)
class VisualDescriptionStrategy(BaseTaskStrategy):
    @property
    def task_category(self) -> str:
        return 'IO'

    def create_client(self, settings):
        if not settings.analysis_connection_id or not settings.analysis_model_name:
            logger.error(
                "Visual Model not configured, please check settings. connection_id: %s, model_name: %s",
                settings.analysis_connection_id, settings.analysis_model_name
            )
            raise ValueError("Visual Model not configured, please check settings in Basic Settings.")

        connection = next((c for c in settings.connections if c.id == settings.analysis_connection_id), None)
        if not connection:
            logger.error("Visual Model connection not found: %s", settings.analysis_connection_id)
            raise ValueError(f"Visual Model connection not found: {settings.analysis_connection_id}")

        if not connection.enable:
            logger.error("Visual Model connection is disabled: %s", settings.analysis_connection_id)
            raise ValueError(f"Visual Model connection is disabled: {settings.analysis_connection_id}")

        if not connection.api_key:
            logger.error("Visual Model connection has no api_key: %s", settings.analysis_connection_id)
            raise ValueError(f"Visual Model connection has no api_key: {settings.analysis_connection_id}")

        # 2. Call OpenAI API
        client = ChatOpenAI(
            api_key=connection.api_key,
            model= settings.analysis_model_name,
            base_url=connection.api_base if connection.api_base else None,
            timeout=60,
            max_completion_tokens=4096,
            extra_body={
                "chat_template_kwargs": {"enable_thinking": False},
            },
            reasoning_effort="none",
        )
        return client

    async def process(self, worker, task: Task, db: Session) -> Dict[str, Any]:
        """
        Handle Visual Description task
        """
        try:
            # Check configuration
            settings = config_manager.get_user_config(task.owner_id, db).ai

            if not settings.analysis_connection_id or not settings.analysis_model_name:
                logger.error("Visual Model not configured, please check settings. connection_id: %s, model_name: %s", settings.analysis_connection_id, settings.analysis_model_name)
                raise ValueError("Visual Model not configured, please check settings in Basic Settings.")

            connection = next((c for c in settings.connections if c.id == settings.analysis_connection_id), None)
            if not connection:
                logger.error("Visual Model connection not found: %s", settings.analysis_connection_id)
                raise ValueError(f"Visual Model connection not found: {settings.analysis_connection_id}")

            if not connection.enable:
                logger.error("Visual Model connection is disabled: %s", settings.analysis_connection_id)
                raise ValueError(f"Visual Model connection is disabled: {settings.analysis_connection_id}")

            if not connection.api_key:
                logger.error("Visual Model connection has no api_key: %s", settings.analysis_connection_id)
                raise ValueError(f"Visual Model connection has no api_key: {settings.analysis_connection_id}")

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
                    if tasks_status.get('visual_description'):
                         return {'status': 'skipped', 'reason': 'already processed'}

                return await self.process_single_photo(worker, photo, db, settings)

            # 2. Generator Mode (Scan all)
            photos_to_process = []
            batch_size = 1000
            offset = 0

            generated_count = 0

            while True:
                query = db.query(Photo).filter(Photo.file_type != FileType.video, Photo.image_type != ImageType.SCREENSHOT)
                if task.owner_id:
                    query = query.filter(Photo.owner_id == task.owner_id)

                batch = query.offset(offset).limit(batch_size).all()
                if not batch:
                    break

                tasks_to_create = []
                for p in batch:
                    should_process = False
                    if force:
                        should_process = True
                    else:
                        tasks_status = p.processed_tasks or {}
                        if not tasks_status.get('visual_description'):
                            should_process = True

                    if should_process:
                        tasks_to_create.append({
                            'type': TaskType.VISUAL_DESCRIPTION,
                            'payload': {'photo_id': str(p.id), 'force': force, 'file_path': p.file_path},
                            'priority': DEFAULT_PRIORITIES[TaskType.VISUAL_DESCRIPTION],
                            'owner_id': p.owner_id
                        })

                if tasks_to_create:
                    worker.add_tasks(db, tasks_to_create)
                    generated_count += len(tasks_to_create)

                offset += batch_size

            return {
                'processed': 0,
                'generated_tasks': generated_count,
                'message': f'Generated {generated_count} Visual Description tasks'
            }

        except Exception as e:
            logger.error(f"Visual Description task failed: {e}")
            raise e

    async def process_single_photo(self, worker, photo: Photo, db: Session, settings) -> Dict[str, Any]:
        try:
            if photo.image_type == ImageType.SCREENSHOT:
                return {'status': 'skipped', 'reason': 'screenshot not supported'}
            user_config = config_manager.get_user_config(photo.owner_id, db)
            settings = user_config.ai
            client =self.create_client(settings)
 
            target_path = storage.get_preview_path(photo.owner_id, photo.id)
            if not target_path or not os.path.exists(target_path):
                target_path = photo.file_path
                if not target_path or not os.path.exists(target_path):
                    return {'status': 'failed', 'error': 'file not found'}

            eval_prompt = user_config.ai.visual_evaluation_prompt
            narrative_prompt = user_config.ai.visual_narrative_prompt
            base64_image = encode_image(target_path)
            image_info = f"照片时间：{photo.photo_time}\n"
            metadata = db.query(PhotoMetadata).filter(PhotoMetadata.photo_id == photo.id).first()
            if metadata:
                image_info += f"照片位置：{metadata.address}\n"
            # 注入文件名与所在文件夹相对路径，帮助模型推断事件/场景（Issue #78）
            try:
                roots = get_user_roots(photo.owner_id, db)
                folder, fname = compute_browse_path(photo.file_path, roots)
                if fname:
                    image_info += f"文件名：{fname}\n"
                if folder:
                    image_info += f"所在文件夹：{folder}\n"
            except Exception as e:
                logger.warning(f"compute relative path failed for photo {photo.id}: {e}")
            # print(target_path, base64_image)
            # Step A: Evaluation
            eval_response = client.invoke([
                    {"role": "system", "content": eval_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "下面是照片的内容，请结合图像本身完成上述任务。\n**不要输出任何多余文字，不要加注释，禁止思考。** /no_think\n照片信息：\n" + image_info},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                },
                            },
                        ],
                    }
                ]
            )

            eval_content = eval_response.content.strip().strip('`').strip().strip('json')
            print(eval_content)
            # Clean up code blocks if present
            if eval_content.startswith("```"):
                eval_content = eval_content.strip("`")
                if eval_content.startswith("json"):
                    eval_content = eval_content[4:]
            try:
                result_json = json.loads(eval_content.strip())
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse evaluation JSON for photo {photo.id}: {eval_content}")
                raise e

            # 3. Save to DB
            # Remove existing if any
            existing = db.query(ImageDescription).filter(ImageDescription.photo_id == photo.id).first()
            if existing:
                db.delete(existing)
                db.flush()

            desc = ImageDescription(
                photo_id=photo.id,
                description=result_json.get("description"),
                memory_score=result_json.get("memory_score"),
                # Map beauty_score from prompt to quality_score in DB
                quality_score=result_json.get("beauty_score") if "beauty_score" in result_json else result_json.get("quality_score"),
                tags=result_json.get("tags", []),
                reason=result_json.get("reason"),
                narrative=result_json.get('narrative', "").strip()
            )
            db.add(desc)
            # Update photo processed status
            tasks_status = dict(photo.processed_tasks or {})
            tasks_status['visual_description'] = True
            photo.processed_tasks = tasks_status
            db.commit()
            return {
                'status': 'completed',
                'description': desc.description,
                'quality': desc.quality_score,
                'narrative': desc.narrative
            }
        except Exception as e:
            logger.error(f"Error processing visual description for photo {photo.id}: {e}")
            raise e
