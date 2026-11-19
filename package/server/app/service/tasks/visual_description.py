from app.service.tasks.photo_generator import generate_photo_tasks
from app.service.disk_budget import media_io
from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory
from app.db.models.task import TaskType, DEFAULT_PRIORITIES
import logging
import json
import base64
from contextlib import asynccontextmanager
import httpx
from typing import Dict, Any, List
from sqlalchemy.orm import Session
# langchain_openai 的导入链重达数秒，仅在 create_client 真正构建客户端时才加载。

from app.db.models import PhotoMetadata
from app.db.models.task import Task, TaskType
from app.db.models.photo import Photo, ImageType
from app.db.models.image_description import ImageDescription
from app.core.config_manager import config_manager
from app.service import storage
from app.utils.path import get_user_roots, compute_browse_path
from app.service.tasks.ci_limit import ci_task_limit_reached, ci_remaining_budget, CI_TASK_PHOTO_LIMIT
from app.service.tasks.ai_runtime import AIBatchSession

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
VISUAL_REQUEST_TIMEOUT_SECONDS = 300
VISUAL_TASK_TIMEOUT_SECONDS = 360
VISUAL_SINGLE_REQUEST_KEY = "visual_single_request"


def _batch_prompt(prompt: str, numbers) -> str:
    numbers = list(numbers)
    criteria, marker, example = prompt.rpartition("请严格只输出 JSON，格式如下：")
    if marker:
        try:
            # Preserve customized instructions if the final section contains more than an example.
            if isinstance(json.loads(example), dict):
                prompt = criteria.rstrip()
        except ValueError:
            pass
    sample = json.dumps(dict.fromkeys(numbers, json.loads(VISUAL_RESULT_SCHEMA)), ensure_ascii=False)
    return (
        "请按给定编号逐张独立分析。以下文字用于确定分析标准，输出格式统一按最后的多图结构。\n"
        f"{prompt}\n"
        "分数范围 0~100。禁止 Markdown、注释和额外文本。\n"
        f"本次共有 {len(numbers)} 张照片。"
        f"只输出一个 JSON 对象。顶层必须包含这些照片编号：{', '.join(numbers)}。"
        f"每个键只对应同编号照片。输出结构示例：\n{sample}"
    )


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

@media_io('image_path')
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

    @property
    def timeout(self) -> int:
        # Keep the worker deadline above the HTTP deadline so the client can
        # close the request cleanly and the task-level retry policy remains the
        # single owner of transient retries.
        return VISUAL_TASK_TIMEOUT_SECONDS

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
        # 显式传独立的 http_async_client：langchain_openai 默认走 lru_cache 缓存的
        # 共享 httpx.AsyncClient（_client_utils._get_default_async_httpx_client），
        # 相同 (base_url, timeout) 的 ChatOpenAI 实例会共用同一条 keep-alive 连接。
        # 本任务的批次在 batch_pool 线程里以每批 asyncio.run() 的新事件循环执行，
        # 共享连接会在不同线程的 loop 间复用，触发
        # "Event loop is closed" / "bound to a different event loop"，表现为约 50%
        # 间歇性 APIConnectionError（Issue #451）。每实例独享连接池即可隔离。
        from langchain_openai import ChatOpenAI
        client = ChatOpenAI(
            api_key=connection.api_key,
            model= settings.analysis_model_name,
            base_url=connection.api_base if connection.api_base else None,
            timeout=VISUAL_REQUEST_TIMEOUT_SECONDS,
            max_retries=0,
            max_completion_tokens=4096,
            http_async_client=httpx.AsyncClient(
                timeout=VISUAL_REQUEST_TIMEOUT_SECONDS,
            ),
            extra_body={
                "chat_template_kwargs": {"enable_thinking": getattr(settings, "analysis_reasoning_effort", "none") != "none"},
            },
            reasoning_effort=getattr(settings, "analysis_reasoning_effort", "none"),
        )
        return client

    @asynccontextmanager
    async def _client(self, settings, owner_id):
        from app.service.llm_usage import LLMUsageCallback

        client = self.create_client(settings)
        client.callbacks = [LLMUsageCallback(
            owner_id, "visual_analysis", settings.analysis_connection_id, settings.analysis_model_name
        )]
        try:
            yield client
        finally:
            if isinstance(getattr(client, 'http_async_client', None), httpx.AsyncClient):
                await client.http_async_client.aclose()

    def _task_photo(self, task, db):
        filters = [Photo.id == task.payload['photo_id']]
        if task.owner_id is not None:
            filters.append(Photo.owner_id == task.owner_id)
        photo = db.query(Photo).filter(*filters).first()
        if not photo:
            return None, {'status': 'skipped', 'reason': 'photo not found'}

        # Album-doctor tasks heal stale processed markers.
        if task.payload.get('only_if_missing'):
            existing_description = db.query(ImageDescription.id).filter(
                ImageDescription.photo_id == photo.id,
                ImageDescription.description.isnot(None),
                ImageDescription.description != '',
            ).first()
            if existing_description:
                return None, {'status': 'skipped', 'reason': 'already processed'}
        elif not task.payload.get('force') and (photo.processed_tasks or {}).get('visual_description'):
            return None, {'status': 'skipped', 'reason': 'already processed'}
        return photo, None

    async def process_batch(self, worker, tasks: List[Task], db: Session) -> List[Dict]:
        if len(tasks) < 2 or not all(
            task.owner_id == tasks[0].owner_id and (task.payload or {}).get('photo_id')
            for task in tasks
        ):
            return await super().process_batch(worker, tasks, db)

        owner_id = tasks[0].owner_id
        settings = config_manager.get_user_config(owner_id, db).ai
        if settings.analysis_connection_id in ('', 'builtin'):
            return await super().process_batch(worker, tasks, db)

        results = {}
        pending = {}
        content = []

        def record(task_id, result, *, retry_as_single=False):
            results[task_id] = {
                'task_id': task_id, 'task_type': TaskType.VISUAL_DESCRIPTION,
                'status': 'failed' if result['status'] == 'failed' else 'completed',
                'result': result, 'error': result.get('error'),
                'retry_as_single': retry_as_single,
            }

        task_ids = [task.id for task in tasks]
        for task in tasks:
            try:
                photo, skipped = self._task_photo(task, db)
                if skipped:
                    record(task.id, skipped)
                    continue
                if photo.image_type == ImageType.SCREENSHOT:
                    record(task.id, {'status': 'skipped', 'reason': 'screenshot not supported'})
                    continue
                parts = self._image_content(photo, db, batch=True)
                if parts is None:
                    record(task.id, {'status': 'failed', 'error': 'file not found'})
                    continue
                number = str(len(pending) + 1)
                parts[0]["text"] = f"照片编号：{number}\n" + parts[0]["text"]
                content.extend(parts)
                pending[number] = (task.id, photo.id, task.payload)
            except Exception as exc:
                record(task.id, {'status': 'failed', 'error': str(exc)})
                db.rollback()

        if pending:
            # Release the read transaction while waiting on the provider.
            db.rollback()
            try:
                async with self._client(settings, owner_id) as client:
                    response = await client.ainvoke([
                        {"role": "system", "content": _batch_prompt(settings.visual_evaluation_prompt, pending)},
                        {"role": "user", "content": content},
                    ], max_completion_tokens=max(4096, 1024 * len(pending)))
                raw = _response_content_to_text(response.content)
                start = raw.find("{")
                if start < 0:
                    raise VisualDescriptionFormatError("模型未返回批量 JSON 结果")
                decoded, _ = json.JSONDecoder().raw_decode(raw[start:])
                if not isinstance(decoded, dict):
                    raise VisualDescriptionFormatError("批量结果必须是 JSON 对象")
            except Exception as exc:
                for task_id, _, _ in pending.values():
                    record(task_id, {'status': 'failed', 'error': str(exc)},
                           retry_as_single=isinstance(exc, (json.JSONDecodeError, VisualDescriptionFormatError)))
            else:
                for number, (task_id, photo_id, payload) in pending.items():
                    try:
                        if number not in decoded:
                            raise VisualDescriptionFormatError(f"模型未返回照片 {number} 的结果")
                        result = _validate_visual_result(decoded[number])
                        record(task_id, self._save_result(db, photo_id, result, payload))
                    except VisualDescriptionFormatError as exc:
                        record(task_id, {'status': 'failed', 'error': str(exc)}, retry_as_single=True)
                    except Exception as exc:
                        db.rollback()
                        record(task_id, {'status': 'failed', 'error': str(exc)})

        return [results[task_id] for task_id in task_ids]

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

            # 1. Single Photo Mode
            if task.payload and 'photo_id' in task.payload:
                photo, skipped = self._task_photo(task, db)
                if skipped:
                    return skipped

                # CI 限速：最多处理 5 张照片，已达上限直接跳过
                if ci_task_limit_reached(db, ImageDescription):
                    return {'status': 'skipped', 'reason': f'CI visual_description limit reached ({CI_TASK_PHOTO_LIMIT} photos)'}

                if task.owner_id is None:
                    settings = config_manager.get_user_config(photo.owner_id, db).ai
                return await self.process_single_photo(worker, photo, db, settings, task.payload)

            remaining = ci_remaining_budget(db, ImageDescription)
            generated_count = generate_photo_tasks(
                db, worker, task, task_type=TaskType.VISUAL_DESCRIPTION,
                status_key='visual_description', priority=DEFAULT_PRIORITIES[TaskType.VISUAL_DESCRIPTION],
                budget=remaining, eligible=lambda photo: photo.image_type != ImageType.SCREENSHOT,
            )

            return {
                'processed': 0,
                'generated_tasks': generated_count,
                'message': f'Generated {generated_count} Visual Description tasks'
            }

        except Exception as e:
            logger.error(f"Visual Description task failed: {e}")
            raise e

    def _image_content(self, photo: Photo, db: Session, *, batch=False):
        target_path = storage.get_available_photo_path(photo.owner_id, photo.id, photo.file_path)
        if not target_path:
            return None

        base64_image = encode_image(target_path)
        image_info = f"照片时间：{photo.photo_time}\n"
        metadata = db.query(PhotoMetadata).filter(PhotoMetadata.photo_id == photo.id).first()
        if metadata:
            image_info += f"照片位置：{metadata.address}\n"
        try:
            roots = get_user_roots(photo.owner_id, db)
            folder, fname = compute_browse_path(photo.file_path, roots)
            if fname:
                image_info += f"文件名：{fname}\n"
            if folder:
                image_info += f"所在文件夹：{folder}\n"
        except Exception as exc:
            logger.warning("compute relative path failed for photo %s: %s", photo.id, exc)

        if not batch:
            image_info = "请结合图像本身分析照片。只输出 JSON。/no_think\n照片信息：\n" + image_info
        return [
            {"type": "text", "text": image_info},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
        ]

    def _save_result(self, db, photo_id, result, payload=None, photo=None):
        if isinstance(db, AIBatchSession):
            db.begin_write()
            photo = db.query(Photo).filter(Photo.id == photo_id).populate_existing().with_for_update().first()
        elif photo is None:
            photo = db.query(Photo).filter(Photo.id == photo_id).first()

        if photo is None:
            db.rollback()
            return {'status': 'skipped', 'reason': 'photo not found'}

        existing = db.query(ImageDescription).filter(ImageDescription.photo_id == photo.id).first()
        if payload is not None:
            if payload.get('only_if_missing'):
                already_processed = existing is not None and bool(existing.description)
            else:
                already_processed = not payload.get('force') and (photo.processed_tasks or {}).get('visual_description')
            if already_processed:
                db.rollback()
                return {'status': 'skipped', 'reason': 'already processed'}

        if existing:
            db.delete(existing)
            db.flush()

        desc = ImageDescription(
            photo_id=photo.id,
            description=result["description"],
            memory_score=result["memory_score"],
            quality_score=result["beauty_score"],
            tags=result["tags"],
            reason=result["reason"],
            narrative=result["narrative"].strip(),
        )
        db.add(desc)
        tasks_status = dict(photo.processed_tasks or {})
        tasks_status['visual_description'] = True
        photo.processed_tasks = tasks_status
        db.commit()
        return {
            'status': 'completed',
            'description': desc.description,
            'quality': desc.quality_score,
            'narrative': desc.narrative,
        }

    async def process_single_photo(self, worker, photo: Photo, db: Session, settings, payload=None) -> Dict[str, Any]:
        if photo.image_type == ImageType.SCREENSHOT:
            return {'status': 'skipped', 'reason': 'screenshot not supported'}

        photo_id = photo.id
        owner_id = photo.owner_id
        content = self._image_content(photo, db)
        if content is None:
            return {'status': 'failed', 'error': 'file not found'}
        if isinstance(db, AIBatchSession):
            db.rollback()

        try:
            async with self._client(settings, owner_id) as client:
                response = await client.ainvoke([
                    {"role": "system", "content": settings.visual_evaluation_prompt + VISUAL_OUTPUT_CONSTRAINT},
                    {"role": "user", "content": content},
                ])
                result = await parse_visual_result_with_repair(client, response.content, photo_id)
            return self._save_result(db, photo_id, result, payload, photo)
        except Exception:
            db.rollback()
            logger.exception("Error processing visual description for photo %s", photo_id)
            raise
