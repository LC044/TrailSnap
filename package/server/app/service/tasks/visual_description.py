from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory
from app.db.models.task import TaskType, DEFAULT_PRIORITIES
import logging
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
from app.service.tasks.ci_limit import ci_task_limit_reached, ci_remaining_budget, CI_TASK_PHOTO_LIMIT

logger = logging.getLogger(__name__)

VISUAL_RESULT_SCHEMA = """{
  "description": "80~200字的中文照片描述",
  "tags": ["人物", "旅行"],
  "memory_score": 0.0,
  "beauty_score": 0.0,
  "reason": "不超过40字的中文原因",
  "narrative": "8~30字的一句中文旁白"
}"""

VISUAL_OUTPUT_CONSTRAINT = f"""

【机器可读输出约束】
你的回答会被程序直接解析，必须严格遵守：
1. 只输出一个 JSON 对象，禁止 Markdown 代码块、解释、前后缀和注释。
2. 必须包含以下全部字段，字段名不得修改或遗漏：
{VISUAL_RESULT_SCHEMA}
3. memory_score 和 beauty_score 必须是 0~100 的数字；tags 必须是字符串数组；其余字段必须是字符串。
4. JSON 字符串中的换行、引号和反斜杠必须正确转义，禁止尾随逗号。
"""

VISUAL_JSON_REPAIR_ATTEMPTS = 2


class VisualDescriptionFormatError(ValueError):
    """Raised when a vision model response cannot satisfy the result schema."""


def _response_content_to_text(content: Any) -> str:
    """Normalize common LangChain response content shapes to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return str(content or "")


def _validate_visual_result(result: Any) -> Dict[str, Any]:
    if not isinstance(result, dict):
        raise VisualDescriptionFormatError("顶层内容必须是 JSON 对象")

    required_string_fields = ("description", "reason", "narrative")
    missing = [
        field
        for field in (*required_string_fields, "tags", "memory_score", "beauty_score")
        if field not in result
    ]
    if missing:
        raise VisualDescriptionFormatError(f"缺少字段: {', '.join(missing)}")

    for field in required_string_fields:
        if not isinstance(result[field], str):
            raise VisualDescriptionFormatError(f"字段 {field} 必须是字符串")

    tags = result["tags"]
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        raise VisualDescriptionFormatError("字段 tags 必须是字符串数组")

    for field in ("memory_score", "beauty_score"):
        value = result[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise VisualDescriptionFormatError(f"字段 {field} 必须是数字")
        if not 0 <= value <= 100:
            raise VisualDescriptionFormatError(f"字段 {field} 必须在 0~100 之间")

    return result


def parse_visual_result(content: Any) -> Dict[str, Any]:
    """Parse JSON even when a model adds a code fence or short prose wrapper."""
    text = _response_content_to_text(content).strip()
    if not text:
        raise VisualDescriptionFormatError("模型返回了空内容")

    candidates = [text]
    if text.startswith("```") and text.endswith("```"):
        fenced = text[3:-3].strip()
        if fenced.lower().startswith("json"):
            fenced = fenced[4:].lstrip()
        candidates.insert(0, fenced)

    first_brace = text.find("{")
    if first_brace >= 0:
        try:
            value, _ = json.JSONDecoder().raw_decode(text[first_brace:])
            return _validate_visual_result(value)
        except (json.JSONDecodeError, VisualDescriptionFormatError):
            pass

    last_error = None
    for candidate in candidates:
        try:
            return _validate_visual_result(json.loads(candidate))
        except (json.JSONDecodeError, VisualDescriptionFormatError) as exc:
            last_error = exc

    raise VisualDescriptionFormatError(f"JSON 解析或结构校验失败: {last_error}") from last_error


async def parse_visual_result_with_repair(client, content: Any, photo_id: Any) -> Dict[str, Any]:
    """Ask the model to repair only its text response, avoiding repeat image inference."""
    current_content = _response_content_to_text(content)
    last_error = None

    for repair_attempt in range(VISUAL_JSON_REPAIR_ATTEMPTS + 1):
        try:
            return parse_visual_result(current_content)
        except VisualDescriptionFormatError as exc:
            last_error = exc
            if repair_attempt >= VISUAL_JSON_REPAIR_ATTEMPTS:
                break

            logger.warning(
                "Invalid visual model output for photo %s; requesting JSON repair (%s/%s): %s",
                photo_id,
                repair_attempt + 1,
                VISUAL_JSON_REPAIR_ATTEMPTS,
                exc,
            )
            repair_response = await client.ainvoke([
                {
                    "role": "system",
                    "content": (
                        "你是 JSON 格式修复器。只能修复给定内容的格式和字段，"
                        "不得重新分析图片、添加解释或改变原有语义。只输出合法 JSON。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"目标结构：\n{VISUAL_RESULT_SCHEMA}\n\n"
                        f"校验错误：{exc}\n\n"
                        "请修复以下模型输出：\n<model_output>\n"
                        f"{current_content[:12000]}\n</model_output>"
                    ),
                },
            ])
            current_content = _response_content_to_text(repair_response.content)

    raise VisualDescriptionFormatError(
        f"视觉模型输出经过 {VISUAL_JSON_REPAIR_ATTEMPTS} 次修复后仍不符合 JSON 格式: {last_error}"
    ) from last_error


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
        return 'AI'

    @property
    def resource_key(self) -> str:
        return 'visual_llm'

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

                # CI 限速：最多处理 5 张照片，已达上限直接跳过
                if ci_task_limit_reached(db, ImageDescription):
                    return {'status': 'skipped', 'reason': f'CI visual_description limit reached ({CI_TASK_PHOTO_LIMIT} photos)'}

                return await self.process_single_photo(worker, photo, db, settings)

            # 2. Generator Mode (Scan all)
            photos_to_process = []
            batch_size = 1000
            offset = 0

            generated_count = 0
            # CI 限速：只生成到上限为止的子任务
            remaining = ci_remaining_budget(db, ImageDescription)

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
                        if remaining is not None and generated_count >= remaining:
                            break
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

                if remaining is not None and generated_count >= remaining:
                    break

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
 
            target_path = storage.get_available_photo_path(photo.owner_id, photo.id, photo.file_path)
            if not target_path:
                return {'status': 'failed', 'error': 'file not found'}

            eval_prompt = user_config.ai.visual_evaluation_prompt
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
            eval_response = await client.ainvoke([
                    {"role": "system", "content": eval_prompt + VISUAL_OUTPUT_CONSTRAINT},
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
            result_json = await parse_visual_result_with_repair(
                client, eval_response.content, photo.id
            )

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
