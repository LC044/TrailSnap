import logging
from abc import ABC, abstractmethod
import traceback
from typing import List, Dict, Any, Type
from sqlalchemy.orm import Session
from app.db.models.task import Task, TaskType

class BaseTaskStrategy(ABC):
    """
    Base strategy class for processing background tasks.
    Each specific task type should implement its own strategy inheriting from this class.
    """

    @property
    def task_category(self) -> str:
        """
        Return the category of the task: 'CPU', 'IO', or 'AI'.
        """
        return 'IO'

    @property
    def resource_key(self) -> str:
        """Fine-grained resource used for admission control inside a category."""
        return self.task_category.lower()

    @property
    def max_attempts(self) -> int:
        """Maximum automatic attempts for transient failures."""
        return 3

    @property
    def timeout(self) -> int:
        """
        Return the timeout in seconds for this task type.
        """
        return 60 * 5  # 5 minutes timeout

    @abstractmethod
    async def process(self, worker, task: Task, db: Session) -> Any:
        """
        Process a single task. This method should handle the actual execution of the task.
        It should return a result dictionary, or raise an exception on failure.
        """
        pass

    async def process_batch(self, worker, tasks: List[Task], db: Session) -> List[Dict]:
        """
        Process a batch of tasks. By default, it processes them sequentially
        using the single-task process method. Subclasses should override this
        to implement true batch processing.
        """
        results = []
        for task in tasks:
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
                logging.error(f"Error processing task {task.id}: {e}", exc_info=True)
                results.append({
                    'task_id': task.id,
                    'task_type': task.type,
                    'status': 'failed',
                    'error': f'{str(e)}\n{traceback.format_exc()}'
                })
        return results

    async def handle_completion(self, worker, items: List[Dict], db: Session) -> None:
        """
        Callback triggered when a batch of tasks of this type has completed.
        Can be used to process successful results, create subsequent tasks, update stats, etc.
        `items` contains a list of dictionaries with keys: 'task_id', 'task_type', 'status', 'result', 'error'.
        """
        pass

    def release_resources(self) -> None:
        """
        Release any resources (like memory, loaded models) specific to this task type.
        Called when the task type has been idle for a period of time.
        """
        pass

class TaskStrategyFactory:
    """
    Factory for managing and retrieving task strategies.
    """
    _strategies: Dict[TaskType, BaseTaskStrategy] = {}

    @classmethod
    def register(cls, task_type: TaskType):
        """
        Decorator to register a strategy class for a specific task type.
        """
        def wrapper(strategy_cls: Type[BaseTaskStrategy]):
            cls._strategies[task_type] = strategy_cls()
            return strategy_cls
        return wrapper

    @classmethod
    def get_strategy(cls, task_type: TaskType) -> BaseTaskStrategy:
        """
        Retrieve the strategy instance for a given task type.
        """
        return cls._strategies.get(task_type)

    @classmethod
    def get_tasks_by_category(cls, category: str) -> List[TaskType]:
        """
        Retrieve a list of task types belonging to the specified category.
        """
        return [task_type for task_type, strategy in cls._strategies.items() if strategy.task_category == category]

    @classmethod
    def release_idle_resources(cls, idle_task_types: List[TaskType]):
        """
        Release resources for the specified idle task types.
        """
        for task_type in idle_task_types:
            strategy = cls.get_strategy(task_type)
            if strategy:
                try:
                    strategy.release_resources()
                except Exception as e:
                    logging.error(f"Error releasing resources for {task_type}: {e}")

    @classmethod
    def release_all_resources(cls):
        """
        Release resources for all registered strategies.
        """
        for strategy in cls._strategies.values():
            try:
                strategy.release_resources()
            except Exception as e:
                logging.error(f"Error releasing resources for strategy: {e}")
