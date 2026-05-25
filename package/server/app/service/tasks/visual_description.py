from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory
from app.db.models.task import TaskType, DEFAULT_PRIORITIES
from typing import List, Dict
import logging
import os
import json
import base64
import re
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from langchain_openai import ChatOpenAI

from app.db.models import PhotoMetadata
from app.db.models.task import Task, TaskType
from app.db.models.photo import Photo, FileType, ImageType
from app.db.models.image_description import ImageDescription
from app.core.config_manager import config_manager
from app.service import storage

logger = logging.getLogger(__name__)


def parse_json_response(content: str) -> Dict[str, Any]:
    text = (content or "").strip()
    if text.startswith("```"):
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if match:
            text = match.group(1).strip()

    candidates = [text]
    brace_index = text.find("{")
    if brace_index > 0:
        candidates.append(text[brace_index:])

    last_error = None
    decoder = json.JSONDecoder(strict=False)
    for candidate in candidates:
        if not candidate:
            continue
        try:
            result, _ = decoder.raw_decode(candidate.strip())
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError as e:
            last_error = e

    preview = text[:300].replace("\n", "\\n")
    raise ValueError(f"Failed to parse model JSON response: {preview}") from last_error


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def mark_visual_description_processed(photo: Photo, db: Session) -> None:
    tasks_status = dict(photo.processed_tasks or {})
    tasks_status['visual_description'] = True
    photo.processed_tasks = tasks_status
    db.commit()


@TaskStrategyFactory.register(TaskType.VISUAL_DESCRIPTION)
class VisualDescriptionStrategy(BaseTaskStrategy):
    @property
    def task_category(self) -> str:
        return 'AI'

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

        # 2. Call OpenAI-compatible API. Some providers reject
        # reasoning_effort="none"; disabling thinking through extra_body is
        # enough for Xiaomi Mimo while still working with LM Studio Qwen.
        client_kwargs = {
            "api_key": connection.api_key,
            "model": settings.analysis_model_name,
            "base_url": connection.api_base if connection.api_base else None,
            "timeout": 60,
            "extra_body": {
                "chat_template_kwargs": {"enable_thinking": False},
            },
        }
        if "xiaomimimo.com" not in (connection.api_base or ""):
            client_kwargs["reasoning_effort"] = "none"

        client = ChatOpenAI(**client_kwargs)
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

            eval_content = eval_response.content
            if "considered high risk" in (eval_content or "").lower():
                mark_visual_description_processed(photo, db)
                return {'status': 'skipped', 'reason': 'model rejected high risk image'}

            try:
                result_json = parse_json_response(eval_content)
            except (json.JSONDecodeError, ValueError) as e:
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
            mark_visual_description_processed(photo, db)
            return {
                'status': 'completed',
                'description': desc.description,
                'quality': desc.quality_score,
                'narrative': desc.narrative
            }
        except Exception as e:
            logger.error(f"Error processing visual description for photo {photo.id}: {e}")
            raise e
