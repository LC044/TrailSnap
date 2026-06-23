"""DEPRECATED: 色彩提取已合并到 PROCESS_BASIC 任务中，不再作为独立任务。

色彩提取逻辑已移至 app/utils/color.py，在 basic.py 的 process_basic_cpu_job 中调用。
此文件仅保留以防旧任务残留。
"""

from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory
from app.db.models.task import TaskType
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


@TaskStrategyFactory.register(TaskType.EXTRACT_EMOTION)
class ExtractEmotionStrategy(BaseTaskStrategy):
    """色彩提取已合并到 PROCESS_BASIC，此策略仅处理残留的旧任务。"""

    @property
    def task_category(self) -> str:
        return 'CPU'

    async def process(self, worker, task, db) -> Dict[str, Any]:
        logger.warning(f"EXTRACT_EMOTION task {task.id} is deprecated, skipping. Color extraction is now done in PROCESS_BASIC.")
        return {'processed': 0, 'message': 'Deprecated task, skipped'}

    async def process_batch(self, worker, tasks: List, db) -> List[Dict]:
        results = []
        for task in tasks:
            results.append({
                'task_id': task.id,
                'task_type': task.type,
                'status': 'completed',
                'result': {'status': 'skipped', 'reason': 'deprecated - color extraction is now done in PROCESS_BASIC'}
            })
        return results
