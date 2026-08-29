import os
import asyncio
import logging
import concurrent.futures
import json
from re import S
from typing import List, Dict, Set, Any, Tuple
from uuid import UUID
from datetime import datetime, timedelta
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models.task import (
    Task,
    TaskType,
    TaskStatus,
    DEFAULT_PRIORITIES,
    INTERACTIVE_TASK_PRIORITY,
)
from app.db.models.system import SystemState
from app.core.system_config import system_config
from app.crud.task import DEFAULT_SCAN_STATUS
from app.crud import task as crud_task

from app.service.task_strategy import TaskStrategyFactory
from app.service.adaptive_limiter import AdaptiveResourceLimiter
# Import tasks to register strategies
from app.service.tasks import thumbnail, metadata, album, scan, face, ocr, classification, image_embedding, visual_description, basic, duplicate, similar, tickets, organize, rename, time_from_filename, emotion

class TaskQueueManager:
    def __init__(self):
        # Priority queue structure: (priority, counter, batch)
        # We use a counter to prevent comparing dicts when priorities are equal
        self.queues = {
            'CPU': asyncio.PriorityQueue(),
            'IO': asyncio.PriorityQueue(),
            'AI': asyncio.PriorityQueue()
        }
        import itertools
        self._counters = {
            'CPU': itertools.count(),
            'IO': itertools.count(),
            'AI': itertools.count()
        }
        self._item_counts = {category: 0 for category in self.queues}

    async def put_batch(self, category: str, batch: List[Dict], priority: int = 1):
        if category in self.queues:
            # priority is inverted because PriorityQueue retrieves lowest first
            count = next(self._counters[category])
            await self.queues[category].put((-priority, count, batch))
            self._item_counts[category] += len(batch)

    async def get_batch(self, category: str) -> List[Dict]:
        if category in self.queues:
            item = await self.queues[category].get()
            self._item_counts[category] = max(0, self._item_counts[category] - len(item[2]))
            return item[2]
        return []

    def qsize(self, category: str) -> int:
        if category in self.queues:
            return self.queues[category].qsize()
        return 0

    def item_count(self, category: str) -> int:
        return self._item_counts.get(category, 0)

    def get_lowest_priority(self, category: str) -> int:
        if category in self.queues and self.queues[category]._queue:
            try:
                # Elements are (-priority, count, batch)
                # max(-priority) gives the lowest priority
                return -max(item[0] for item in self.queues[category]._queue)
            except ValueError:
                pass
        return -9999

    def task_done(self, category: str):
        if category in self.queues:
            self.queues[category].task_done()


def get_chunk_size(task_type):
    level = system_config.config.task.concurrency_level
    chunk_size = 8 if level == 'high' else 4
    if task_type == TaskType.VISUAL_DESCRIPTION:
        chunk_size = 1
    elif task_type == TaskType.OCR or task_type == TaskType.RECOGNIZE_TICKET:
        chunk_size = 2 if level == 'high' else 1
    elif task_type == TaskType.RECOGNIZE_FACE:
        chunk_size = 4 if level == 'high' else 2
    elif task_type == TaskType.PROCESS_BASIC or task_type == TaskType.EXTRACT_METADATA:
        chunk_size = 16
    elif task_type == TaskType.CLASSIFY_IMAGE:
        chunk_size = 8
    elif task_type == TaskType.IMAGE_EMBEDDING:
        chunk_size = 8
    return chunk_size


class TaskWorker:
    """
    Task Consumer / Worker (Runs in Background Process)
    Responsible for:
    1. Monitoring task queue
    2. Executing tasks
    3. Managing resources (pools)
    4. Updating system status
    """
    _instance = None

    @property
    def CPU_TASKS(self):
        return TaskStrategyFactory.get_tasks_by_category('CPU')

    @property
    def IO_TASKS(self):
        return TaskStrategyFactory.get_tasks_by_category('IO')

    @property
    def AI_TASKS(self):
        return TaskStrategyFactory.get_tasks_by_category('AI')

    def __init__(self):
        self.running = False
        self.worker_task = None
        self.result_task = None
        self.cpu_consumer_task = None
        self.io_consumer_task = None
        self.ai_consumer_task = None
        self.process_pool = None
        self.thread_pool = None
        self.result_queue = asyncio.Queue()
        self.queue_manager = TaskQueueManager()
        self.scan_status = DEFAULT_SCAN_STATUS.copy()

        # Will be initialized in _sync_system_state_if_needed
        self.paused_categories = set()
        self.fast_mode = False

        # Maintain a map of Future/Task -> TaskType to track running tasks
        self.active_task_map: Dict[asyncio.Future, TaskType] = {}
        self.last_active_time: Dict[TaskType, datetime] = {}
        # Multiprocessing queue back to the API process for SSE events
        self.event_queue = None
        # Rows remain PENDING while prefetched. This in-memory reservation set
        # prevents the producer from selecting the same row twice.
        self.reserved_task_ids: Set[UUID] = set()
        self.resource_limiters: Dict[str, AdaptiveResourceLimiter] = {}
        self.adaptive_limits: Dict[str, int] = {}
        self.pressure_task = None
        self.system_pressure = {"cpu": 0.0, "memory": 0.0}

    def set_event_queue(self, queue):
        self.event_queue = queue

    def _publish(self, event: str, data: Dict[str, Any]):
        if self.event_queue is None:
            return
        try:
            self.event_queue.put_nowait({'event': event, 'data': data})
        except Exception:
            # Queue full or closed; drop the event silently.
            pass

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = TaskWorker()
        return cls._instance

    def _save_system_state(self, key: str, value: Any):
        db = SessionLocal()
        try:
            state = db.query(SystemState).filter(SystemState.key == key).first()
            if not state:
                state = SystemState(key=key)
                db.add(state)

            if isinstance(value, (set, list, dict)):
                state.value = json.dumps(value, default=str)
            else:
                state.value = str(value)
            db.commit()
        except Exception as e:
            logging.error(f"Failed to save system state {key}: {e}")
        finally:
            db.close()

    def _load_system_state(self, key: str, default: Any = None):
        db = SessionLocal()
        try:
            state = db.query(SystemState).filter(SystemState.key == key).first()
            if state:
                try:
                    return json.loads(state.value)
                except:
                    return state.value
            return default
        except Exception as e:
            # logging.error(f"Failed to load system state {key}: {e}")
            return default
        finally:
            db.close()

    def _get_concurrency_settings(self):
        level = system_config.config.task.concurrency_level
        cpu_count = os.cpu_count() or 4
        if level == "high":
            return {
                # Keep at least one logical core available to the API process.
                "process_pool": max(1, cpu_count - 1),
                "thread_pool": 16,
                "cpu_consumer": max(1, cpu_count - 1),
                "io_consumer": 8,
                "ai_consumer": 8
            }
        elif level == "low":
            return {
                "process_pool": max(1, cpu_count // 4),
                "thread_pool": 4,
                "cpu_consumer": max(1, cpu_count // 4),
                "io_consumer": 2,
                "ai_consumer": 2
            }
        else: # medium
            return {
                "process_pool": max(1, cpu_count // 2),
                "thread_pool": 8,
                "cpu_consumer": max(1, cpu_count // 2),
                "io_consumer": 4,
                "ai_consumer": 5
            }

    def _get_resource_limits(self) -> Dict[str, int]:
        level = system_config.config.task.concurrency_level
        limits = {
            "classification": 1,
            "ocr": 1,
            "face": 1,
            "embedding": 1,
            "tickets": 1,
            "visual_llm": 1,
            "local_llm": 1,
            "cpu": self._get_concurrency_settings()["cpu_consumer"],
            "io": self._get_concurrency_settings()["io_consumer"],
        }
        if level == "medium":
            limits.update({"face": 2, "embedding": 2, "visual_llm": 2})
        elif level == "high":
            limits.update({
                "classification": 2,
                "ocr": 2,
                "face": 2,
                "embedding": 2,
                "tickets": 2,
                "visual_llm": 4,
            })
        return limits

    def _resource_limiter(self, resource_key: str) -> AdaptiveResourceLimiter:
        limiter = self.resource_limiters.get(resource_key)
        if limiter is None:
            ceiling = self._get_resource_limits().get(resource_key, 1)
            limiter = self._make_resource_limiter(resource_key, ceiling, None)
            self.resource_limiters[resource_key] = limiter
        return limiter

    def _make_resource_limiter(
        self, resource_key: str, ceiling: int, persisted: Any
    ) -> AdaptiveResourceLimiter:
        task_config = system_config.config.task
        default_initial = max(1, (ceiling + 1) // 2)
        try:
            initial = int(persisted)
        except (TypeError, ValueError):
            initial = default_initial
        if not task_config.adaptive_concurrency:
            initial = ceiling
        return AdaptiveResourceLimiter(
            resource_key,
            initial_limit=initial,
            max_limit=ceiling,
            success_threshold=task_config.aimd_success_threshold,
            cooldown_seconds=task_config.aimd_cooldown_seconds,
            on_change=self._on_resource_limit_change,
        )

    def _on_resource_limit_change(
        self, resource_key: str, limit: int, reason: str
    ) -> None:
        self.adaptive_limits[resource_key] = limit
        self._save_system_state("adaptive_resource_limits", self.adaptive_limits)
        self._publish("task.concurrency", {
            "resource_key": resource_key,
            "limit": limit,
            "reason": reason,
        })
        logging.info(
            "Adaptive concurrency changed: resource=%s limit=%s reason=%s",
            resource_key, limit, reason,
        )

    def _is_system_overloaded(self) -> bool:
        config = system_config.config.task
        return (
            self.system_pressure["cpu"] >= config.cpu_high_watermark
            or self.system_pressure["memory"] >= config.memory_high_watermark
        )

    async def _pressure_monitor_loop(self) -> None:
        try:
            import psutil

            psutil.cpu_percent(interval=None)
            while self.running:
                await asyncio.sleep(2)
                cpu = float(psutil.cpu_percent(interval=None))
                memory = float(psutil.virtual_memory().percent)
                # A short EMA avoids reacting to one noisy scheduler sample.
                self.system_pressure["cpu"] = (
                    self.system_pressure["cpu"] * 0.6 + cpu * 0.4
                )
                self.system_pressure["memory"] = (
                    self.system_pressure["memory"] * 0.6 + memory * 0.4
                )
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logging.warning("System pressure monitor stopped: %s", exc)

    def _prefetch_limit(self, category: str) -> int:
        settings = self._get_concurrency_settings()
        concurrency = settings[f"{category.lower()}_consumer"]
        # At most two small waves wait in memory. Rows are still PENDING in DB.
        return max(2, concurrency * 2)

    def start(self):
        if self.running:
            return
        self.running = True
        self._recover_unfinished_tasks()

        # Load fast_mode state
        self.fast_mode = self._load_system_state('fast_mode', False)
        settings = self._get_concurrency_settings()
        persisted_limits = self._load_system_state('adaptive_resource_limits', {})
        if not isinstance(persisted_limits, dict):
            persisted_limits = {}
        self.adaptive_limits = {}
        self.resource_limiters = {
            key: self._make_resource_limiter(
                key, limit, persisted_limits.get(key)
            )
            for key, limit in self._get_resource_limits().items()
        }
        self.adaptive_limits = {
            key: limiter.current_limit
            for key, limiter in self.resource_limiters.items()
        }
        self.process_pool = concurrent.futures.ProcessPoolExecutor(max_workers=settings['process_pool'])
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=settings['thread_pool']) # More threads for IO

        self.worker_task = asyncio.create_task(self.worker_loop())
        self.result_task = asyncio.create_task(self.result_loop())
        self.cpu_consumer_task = asyncio.create_task(self.consumer_loop('CPU'))
        self.io_consumer_task = asyncio.create_task(self.consumer_loop('IO'))
        self.ai_consumer_task = asyncio.create_task(self.consumer_loop('AI'))
        self.pressure_task = asyncio.create_task(self._pressure_monitor_loop())
        logging.info(f"TaskWorker started. Fast Mode: {self.fast_mode}")

    def stop(self):
        self.running = False
        if self.worker_task:
            self.worker_task.cancel()
        if self.result_task:
            self.result_task.cancel()
        if self.cpu_consumer_task:
            self.cpu_consumer_task.cancel()
        if self.io_consumer_task:
            self.io_consumer_task.cancel()
        if self.ai_consumer_task:
            self.ai_consumer_task.cancel()
        if getattr(self, 'pressure_task', None):
            self.pressure_task.cancel()
        if self.process_pool:
            self.process_pool.shutdown(wait=False)
            self.process_pool = None
        if self.thread_pool:
            self.thread_pool.shutdown(wait=False)
            self.thread_pool = None

        # Save final status
        self.scan_status['fast_mode'] = self.fast_mode
        self._save_system_state('scan_status', self.scan_status)
        logging.info("TaskWorker stopped")

    def release_resources(self):
        """Release all resources"""
        if self.process_pool:
            logging.info("Shutting down process pool to release resources")
            self.process_pool.shutdown(wait=False)
            self.process_pool = None
        if self.thread_pool:
            logging.info("Shutting down thread pool to release resources")
            self.thread_pool.shutdown(wait=False)
            self.thread_pool = None
        TaskStrategyFactory.release_all_resources()

    def check_task_for_release(self):
        # Check for Module Resources
        idle_types = []
        for task_type in TaskType:
            if task_type not in self.last_active_time:
                continue

            last_run = self.last_active_time[task_type]
            if (datetime.now() - last_run).total_seconds() > 300:
                idle_types.append(task_type)
                
        if idle_types:
            TaskStrategyFactory.release_idle_resources(idle_types)
            for t in idle_types:
                del self.last_active_time[t]

    def _sync_system_state_if_needed(self) -> None:
        now = datetime.now()
        if not hasattr(self, '_last_sync'):
            self._last_sync = datetime.min
        if (now - self._last_sync).total_seconds() > 5:
            self._save_system_state('scan_status', self.scan_status)
            paused_list = self._load_system_state('paused_categories', [])
            self.paused_categories = set(paused_list)
            self.fast_mode = self._load_system_state('fast_mode', False)
            self._last_sync = now

    def _manage_pool_lifecycle(self):
        active_count = len(self.active_task_map)
        # Check for CPU Pool
        active_cpu_count = sum(1 for t in self.active_task_map.values() if TaskStrategyFactory.get_strategy(t).task_category == 'CPU')
        if active_cpu_count == 0 and self.process_pool:
            # CPU tasks run in process pool currently, but we are migrating to thread pool for simplification if needed
            # For now keep as is. We need to check all CPU tasks.
            cpu_tasks = [t for t in TaskType if TaskStrategyFactory.get_strategy(t).task_category == 'CPU']
            last_cpu_run = max([self.last_active_time.get(t, datetime.min) for t in cpu_tasks], default=datetime.min)
            if (datetime.now() - last_cpu_run).total_seconds() > 300:
                self.process_pool.shutdown(wait=False)
                self.process_pool = None

        # Check for IO Pool
        active_io_count = sum(1 for t in self.active_task_map.values() if TaskStrategyFactory.get_strategy(t).task_category == 'IO')
        if active_io_count == 0 and self.thread_pool:
            io_tasks = [t for t in TaskType if TaskStrategyFactory.get_strategy(t).task_category == 'IO']
            last_io_run = max([self.last_active_time.get(t, datetime.min) for t in io_tasks], default=datetime.min)
            if (datetime.now() - last_io_run).total_seconds() > 300:
                self.thread_pool.shutdown(wait=False)
                self.thread_pool = None

        self.check_task_for_release()

        # Ensure pools exist
        if active_count > 0:
            settings = self._get_concurrency_settings()
            if active_cpu_count > 0 and self.process_pool is None:
                logging.info(f"Restarting process pool")
                self.process_pool = concurrent.futures.ProcessPoolExecutor(max_workers=settings['process_pool'])
            if self.thread_pool is None and active_io_count > 0:
                logging.info(f"Restarting thread pool")
                self.thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=settings['thread_pool'])

    def _calculate_allowed_task_types(self) -> List[str]:
        allowed_types = []
        # In queue architecture, active_count is the number of active task *batches* running
        # We should rely more on queue depth rather than active count to fetch tasks
        # But we still check system limits to avoid flooding DB
        if self.fast_mode:
            allowed_types.extend([t for t in TaskType if TaskStrategyFactory.get_strategy(t).task_category == 'CPU'])
            allowed_types.extend([t for t in TaskType if TaskStrategyFactory.get_strategy(t).task_category == 'IO'])
            allowed_types.extend([t for t in TaskType if TaskStrategyFactory.get_strategy(t).task_category == 'AI'])
            other_types = [t for t in TaskType if TaskStrategyFactory.get_strategy(t).task_category not in ['CPU', 'IO', 'AI']]
            allowed_types.extend(other_types)
        else:
            allowed_types = [t for t in TaskType]
        # Filter out paused categories
        allowed_types = [t for t in allowed_types if t.value not in self.paused_categories]
        return allowed_types

    def _fetch_tasks_to_queues_sync(self, allowed_types: List[str], current_item_counts: Dict[str, int], lowest_priorities: Dict[str, int] = None, reserved_task_ids: Set[UUID] = None) -> List[Tuple[str, List[Dict]]]:
        from app.core.config_manager import config_manager
        db = SessionLocal()
        if lowest_priorities is None:
            lowest_priorities = {'CPU': -9999, 'IO': -9999, 'AI': -9999}
        reserved_task_ids = reserved_task_ids or set()
        try:
            # 每个 category 的内存队列一次只放入「一种」任务类型的任务。
            # 取最高优先级且尚有 PENDING 任务的类型，把它取完后再取下一优先级，
            # 避免不同类型在同一队列中交替、导致模型/资源反复加载卸载。
            FETCH_BATCH_SIZE = 48

            chunked_batches = []
            for cat in ['CPU', 'IO', 'AI']:
                cat_types = [t for t in allowed_types if TaskStrategyFactory.get_strategy(t) and TaskStrategyFactory.get_strategy(t).task_category == cat]
                # A category pause disables automatic pipeline work, not an
                # operation the user explicitly started from the lightbox.
                # Include paused types as candidates here; the SQL eligibility
                # filter below admits only their interactive-priority rows.
                cat_types.extend([
                    t for t in TaskType
                    if t.value in self.paused_categories
                    and TaskStrategyFactory.get_strategy(t)
                    and TaskStrategyFactory.get_strategy(t).task_category == cat
                ])
                if not cat_types:
                    continue

                queued_items = current_item_counts.get(cat, 0)
                prefetch_limit = self._prefetch_limit(cat)
                if queued_items >= prefetch_limit:
                    continue
                candidate_types = cat_types

                if not candidate_types:
                    continue

                # 选出候选类型中优先级最高、且尚有 PENDING 任务的那一种
                top = (db.query(Task.type, Task.priority)
                         .filter(Task.status == TaskStatus.PENDING)
                         .filter(or_(Task.next_retry_at.is_(None), Task.next_retry_at <= datetime.now()))
                         .filter(Task.type.in_(candidate_types))
                         .filter(or_(
                             Task.type.notin_(list(self.paused_categories)),
                             Task.priority >= INTERACTIVE_TASK_PRIORITY,
                         ))
                         .order_by(Task.priority.desc(), Task.created_at.asc())
                         .first())
                if not top:
                    continue
                chosen_type = top[0]
                top_priority = top[1]

                # 只取这一种类型的任务，按创建时间顺序最多取 FETCH_BATCH_SIZE 条
                query = (db.query(Task)
                           .filter(Task.status == TaskStatus.PENDING)
                           .filter(Task.type == chosen_type)
                           .filter(or_(Task.next_retry_at.is_(None), Task.next_retry_at <= datetime.now()))
                           .filter(or_(
                               Task.type.notin_(list(self.paused_categories)),
                               Task.priority >= INTERACTIVE_TASK_PRIORITY,
                           )))
                if reserved_task_ids:
                    query = query.filter(Task.id.notin_(list(reserved_task_ids)))
                fetch_limit = min(FETCH_BATCH_SIZE, prefetch_limit - queued_items)
                tasks = (query.order_by(Task.priority.desc(), Task.created_at.asc())
                              .limit(fetch_limit)
                              .all())
                if not tasks:
                    continue

                # 按 (任务类型, 实际目标 category) 分组，保留 AI->IO 的重定向语义
                tasks_by_cat: Dict[str, List[Dict]] = {}
                for task in tasks:
                    actual_cat = cat
                    strategy = TaskStrategyFactory.get_strategy(task.type)
                    resource_key = strategy.resource_key
                    if task.type == TaskType.VISUAL_DESCRIPTION and task.owner_id:
                        user_config = config_manager.get_user_config(task.owner_id, db)
                        if user_config.ai.analysis_connection_id == 'builtin':
                            resource_key = 'local_llm'
                    tasks_by_cat.setdefault(actual_cat, []).append(
                        {
                            'id': task.id,
                            'type': task.type,
                            'priority': task.priority,
                            'resource_key': resource_key,
                        }
                    )

                # 拆分成更小的批次放入对应 category 的队列
                for actual_cat, task_list in tasks_by_cat.items():
                    # Keep interactive work in one-item batches. Besides giving
                    # the viewer a prompt response, this prevents seven older
                    # background photos of the same type from hitching a ride in
                    # the high-priority batch.
                    interactive = [t for t in task_list if t['priority'] >= INTERACTIVE_TASK_PRIORITY]
                    background = [t for t in task_list if t['priority'] < INTERACTIVE_TASK_PRIORITY]
                    for task_info in interactive:
                        chunked_batches.append((actual_cat, [task_info]))

                    chunk_size = get_chunk_size(chosen_type)
                    for i in range(0, len(background), chunk_size):
                        chunk = background[i:i + chunk_size]
                        chunked_batches.append((actual_cat, chunk))
            return chunked_batches
        except Exception as e:
            logging.error(f"Error fetching tasks: {e}")
            return []
        finally:
            db.close()

    async def consumer_loop(self, category: str):
        logging.info(f"TaskWorker {category} consumer loop started")

        # Configure max concurrency per consumer category based on system settings
        # or Fast Mode. Using Semaphores to allow multiple batches to run concurrently.
        settings = self._get_concurrency_settings()
        max_concurrency = 1
        if category == 'CPU':
            max_concurrency = settings['cpu_consumer']
        elif category == 'IO':
            max_concurrency = settings['io_consumer']
        elif category == 'AI':
            max_concurrency = settings['ai_consumer']

        semaphore = asyncio.Semaphore(max_concurrency)

        while self.running:
            try:
                # 必须先获取 semaphore 才能从队列拿任务，防止由于并发超限导致高优先级任务被取出后隐藏在内存中
                await semaphore.acquire()

                # 为了防止被无限期阻塞导致无法响应停止信号（self.running=False）
                # 我们使用 wait_for，并设置一个较短的超时时间
                try:
                    batch = await asyncio.wait_for(self.queue_manager.get_batch(category), timeout=1.0)
                    # logging.error(f'{category} {batch}')
                except asyncio.TimeoutError:
                    semaphore.release()
                    continue

                if not batch:
                    semaphore.release()
                    continue

                async def wrapper(b):
                    try:
                        future = asyncio.create_task(self.execute_batch_task_wrapper(b, category))
                        self.active_task_map[future] = b[0]['type']
                        await future
                    except Exception as e:
                        logging.error(f"Error executing batch in {category}: {e}")
                    finally:
                        self.queue_manager.task_done(category)
                        semaphore.release()

                # 放开后台任务执行
                asyncio.create_task(wrapper(batch))
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Unexpected error in {category} consumer loop: {e}", exc_info=True)
                # Ensure semaphore is released on unexpected errors if we had acquired it
                try:
                    semaphore.release()
                except ValueError:
                    pass
                await asyncio.sleep(1)

    async def execute_batch_task_wrapper(self, task_infos: List[Dict], category: str):
        if not task_infos:
            return

        task_type = task_infos[0]['type']
        task_ids = [t['id'] for t in task_infos]
        resource_key = task_infos[0].get('resource_key', category.lower())
        resource_limiter = self._resource_limiter(resource_key)
        await resource_limiter.acquire()
        db = None
        batch_outcome = None
        try:
            db = SessionLocal()
            db.expire_on_commit = False  # Prevent lazy loading issues after intermediate commits
            tasks = crud_task.get_tasks_by_ids(db, task_ids)
            if not tasks:
                return
            strategy = TaskStrategyFactory.get_strategy(task_type)
            if not strategy:
                raise ValueError(f"Strategy not found for task type: {task_type}")
            if (
                task_type in self.paused_categories
                and not all(t.priority >= INTERACTIVE_TASK_PRIORITY for t in tasks)
            ):
                for t in tasks:
                    t.status = TaskStatus.PENDING
                db.commit()
                return
            # A task becomes PROCESSING only after both category and resource
            # admission have succeeded. Prefetched rows remain PENDING.
            for task in tasks:
                task.status = TaskStatus.PROCESSING
                task.error = None
                task.next_retry_at = None
                self.last_active_time[task.type] = datetime.now()
            db.commit()
            for task in tasks:
                self._publish_task_row(task)
            try:
                results = await asyncio.wait_for(strategy.process_batch(self, tasks, db), timeout=strategy.timeout)
                batch_outcome = "success"
                task_map = {task.id: task for task in tasks}
                for res in results:
                    task = task_map.get(res.get('task_id'))
                    is_failed = res.get('status') == TaskStatus.FAILED
                    is_retryable = is_failed and self._is_retryable_error(res.get('error'))
                    if is_retryable:
                        batch_outcome = (
                            "waiting_for_model"
                            if self._is_model_preparing_error(res.get('error'))
                            else "overload"
                        )
                    elif is_failed and batch_outcome != "overload":
                        batch_outcome = None
                    if (
                        task is not None
                        and is_retryable
                        and self._schedule_retry(db, task, res.get('error'), strategy.max_attempts)
                    ):
                        continue
                    if task is not None and res.get('status') == TaskStatus.FAILED:
                        task.attempt_count = (task.attempt_count or 0) + 1
                        db.commit()
                    await self.result_queue.put(res)
            except asyncio.TimeoutError:
                batch_outcome = "overload"
                logging.error(f"Task batch {task_type} timed out after {strategy.timeout} seconds")
                error = f"AI service timeout after {strategy.timeout} seconds"
                for task in tasks:
                    if not self._schedule_retry(db, task, error, strategy.max_attempts):
                        await self.result_queue.put({
                            'task_id': task.id,
                            'task_type': task_type,
                            'status': TaskStatus.FAILED,
                            'error': error,
                        })
            except Exception as e:
                if self._is_model_preparing_error(e):
                    batch_outcome = "waiting_for_model"
                elif self._is_retryable_error(e):
                    batch_outcome = "overload"
                logging.error(f"Task batch {task_type} failed: {e}", exc_info=True)
                for task in tasks:
                    if self._is_retryable_error(e) and self._schedule_retry(
                        db, task, e, strategy.max_attempts
                    ):
                        continue
                    task.attempt_count = (task.attempt_count or 0) + 1
                    db.commit()
                    await self.result_queue.put({
                        'task_id': task.id,
                        'task_type': task_type,
                        'status': TaskStatus.FAILED,
                        'error': str(e),
                    })
        except Exception as e:
            logging.error(f"Error in task batch wrapper for {task_type}: {e}")
        finally:
            if db is not None:
                db.close()
            await resource_limiter.release()
            if system_config.config.task.adaptive_concurrency:
                if batch_outcome == "overload":
                    await resource_limiter.record_overload("transient_failure")
                elif batch_outcome == "success" and self._is_system_overloaded():
                    await resource_limiter.record_overload("system_pressure")
                elif batch_outcome == "success":
                    await resource_limiter.record_success()
            self.reserved_task_ids.difference_update(task_ids)

    def _publish_task_row(self, task: Task) -> None:
        self._publish('task.updated', {
            'id': str(task.id),
            'type': task.type,
            'status': task.status,
            'priority': task.priority,
            'total_items': task.total_items or 0,
            'processed_items': task.processed_items or 0,
            'error': task.error,
            'owner_id': str(task.owner_id) if task.owner_id else None,
            'created_at': task.created_at.isoformat() if task.created_at else None,
            'updated_at': task.updated_at.isoformat() if task.updated_at else None,
            'payload': task.payload or {},
            'attempt_count': task.attempt_count or 0,
            'next_retry_at': task.next_retry_at.isoformat() if task.next_retry_at else None,
        })

    @staticmethod
    def _is_retryable_error(error: Any) -> bool:
        text = str(error or '').lower()
        markers = (
            'timeout', 'timed out', '429', '503', '502', 'connection',
            'temporarily unavailable', 'server disconnected', 'service busy',
            '服务繁忙', 'try again later',
        )
        return any(marker in text for marker in markers)

    @staticmethod
    def _is_model_preparing_error(error: Any) -> bool:
        text = str(error or '').lower()
        return (
            'model_status=downloading' in text
            or 'model_status=pending' in text
        )

    def _schedule_retry(self, db: Session, task: Task, error: Any, max_attempts: int) -> bool:
        if self._is_model_preparing_error(error):
            delay = 60
            task.status = TaskStatus.PENDING
            # Model downloads can take many minutes. Waiting for readiness is
            # not an inference attempt and must not exhaust max_attempts.
            task.next_retry_at = datetime.now() + timedelta(seconds=delay)
            task.error = "AI 大模型正在下载，下载完成后将自动继续"
            db.commit()
            self._publish_task_row(task)
            logging.info(
                "Task %s waiting %ss for the selected AI model to become ready",
                task.id, delay,
            )
            return True

        attempt = (task.attempt_count or 0) + 1
        if attempt >= max_attempts:
            task.attempt_count = attempt
            db.commit()
            return False
        jitter = hash(str(task.id)) % 5
        delay = min(120, 5 * (3 ** (attempt - 1)) + jitter)
        task.status = TaskStatus.PENDING
        task.attempt_count = attempt
        task.next_retry_at = datetime.now() + timedelta(seconds=delay)
        task.error = f"设备繁忙，将在 {delay} 秒后自动重试（{attempt}/{max_attempts}）"
        db.commit()
        self._publish_task_row(task)
        logging.warning(
            "Task %s scheduled for retry in %ss after transient error: %s",
            task.id, delay, error,
        )
        return True

    async def worker_loop(self):
        logging.info("TaskWorker producer loop started")
        self._idle_start_time = None
        self._backoff_delay = 1.0

        while self.running:
            try:
                done_futures = [f for f in self.active_task_map.keys() if f.done()]
                active_count = len(self.active_task_map)
                for f in done_futures:
                    del self.active_task_map[f]

                self._sync_system_state_if_needed()
                self._manage_pool_lifecycle()

                # logging.info(f"Active task count: {active_count}")
                if active_count > 0:
                    self.scan_status['running'] = True
                    self._idle_start_time = None
                    self._backoff_delay = 1.0
                else:
                    if self._idle_start_time is None:
                        self._idle_start_time = datetime.now()
                        self.scan_status['running'] = False
                        self.scan_status['message'] = "Idle"
                        self._save_system_state('scan_status', self.scan_status)

                allowed_types = self._calculate_allowed_task_types()

                current_item_counts = {
                    'CPU': self.queue_manager.item_count('CPU'),
                    'IO': self.queue_manager.item_count('IO'),
                    'AI': self.queue_manager.item_count('AI')
                }
                lowest_priorities = {
                    'CPU': self.queue_manager.get_lowest_priority('CPU'),
                    'IO': self.queue_manager.get_lowest_priority('IO'),
                    'AI': self.queue_manager.get_lowest_priority('AI')
                }

                chunked_batches = await asyncio.to_thread(
                    self._fetch_tasks_to_queues_sync,
                    allowed_types,
                    current_item_counts,
                    lowest_priorities,
                    set(self.reserved_task_ids),
                )
                dispatched_count = 0

                for cat, chunk in chunked_batches:
                    if chunk:
                        priority = max(task['priority'] for task in chunk)
                        await self.queue_manager.put_batch(cat, chunk, priority=priority)
                        self.reserved_task_ids.update(task['id'] for task in chunk)
                        dispatched_count += len(chunk)

                if dispatched_count == 0:
                    if active_count == 0 and self._idle_start_time:
                        idle_duration = (datetime.now() - self._idle_start_time).total_seconds()
                        if idle_duration > 300: # 5 minutes
                            logging.info("Worker idle for 5 minutes, exiting to release resources...")
                            self.running = False
                            import sys
                            sys.exit(0)
                    await asyncio.sleep(self._backoff_delay)
                    self._backoff_delay = min(self._backoff_delay * 1.5, 10.0)
                else:
                    self._backoff_delay = 1.0

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Unexpected error in worker loop: {e}")
                await asyncio.sleep(1)

    async def result_loop(self):
        logging.info("TaskWorker result loop started")
        pending_items = []
        last_flush = datetime.now()
        while self.running:
            try:
                try:
                    # Collect items with short timeout
                    item = await asyncio.wait_for(self.result_queue.get(), timeout=0.5)
                    pending_items.append(item)
                except asyncio.TimeoutError:
                    pass
                now = datetime.now()
                should_flush = len(pending_items) >= 50 or ((now - last_flush).total_seconds() > 1 and pending_items)
                if should_flush:
                    # logging.info(f"Flushing {len(pending_items)} results {pending_items}")
                    await self._flush_results(pending_items)
                    pending_items = []
                    last_flush = now
                    # Update status in DB
                    self._save_system_state('scan_status', self.scan_status)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error in result loop: {e}")
                await asyncio.sleep(1)

    def _recover_unfinished_tasks(self):
        """启动时恢复未完成的任务：重置PROCESSING为PENDING，统计未完成任务数"""
        db = SessionLocal()
        try:
            # 1. 统计未完成任务（PENDING + PROCESSING）
            pending_tasks = crud_task.count_tasks_by_status(db, TaskStatus.PENDING)
            processing_tasks = crud_task.count_tasks_by_status(db, TaskStatus.PROCESSING)
            total_unfinished = pending_tasks + processing_tasks

            if total_unfinished == 0:
                logging.info("No unfinished tasks to recover")
                return

            # 2. 重置PROCESSING任务为PENDING（服务重启后，PROCESSING的任务已中断）
            if processing_tasks > 0:
                # 获取所有PROCESSING状态的任务
                processing_task_list = crud_task.get_tasks_by_status(db, TaskStatus.PROCESSING)
                for task in processing_task_list:
                    # 检查payload中是否包含force=True
                    if task.payload and task.payload.get('force') is True:
                        # 如果是强制任务，重置时移除force标记，避免无限循环重复处理
                        new_payload = task.payload.copy()
                        new_payload['force'] = False
                        task.payload = new_payload
                        logging.info(f"Reset task {task.id} payload: removed force=True")
                    task.status = TaskStatus.PENDING
                db.commit()
                logging.info(f"Reset {processing_tasks} PROCESSING tasks to PENDING (recovered)")

            # 3. 初始化扫描状态（标记有未完成任务，更新统计）
            self.scan_status['running'] = True
            self.scan_status['message'] = f"Recovered {total_unfinished} unfinished tasks"
            self.scan_status['total_files'] = max(self.scan_status['total_files'], total_unfinished)
            logging.info(f"Recovered total {total_unfinished} unfinished tasks (pending: {pending_tasks}, processing: {processing_tasks})")
            self._save_system_state('scan_status', self.scan_status)
            paused_list = self._load_system_state('paused_categories', [])
            self.paused_categories = set(paused_list)

        except Exception as e:
            logging.error(f"Failed to recover unfinished tasks: {e}", exc_info=True)
            db.rollback()
        finally:
            db.close()

    async def _flush_results(self, items: List[Dict]):
        db = SessionLocal()
        try:
            # Group items by task_type
            items_by_type = {}
            for item in items:
                t_type = item['task_type']
                if t_type not in items_by_type:
                    items_by_type[t_type] = []
                items_by_type[t_type].append(item)

            # Call handle_completion for each strategy
            for t_type, type_items in items_by_type.items():
                strategy = TaskStrategyFactory.get_strategy(t_type)
                if strategy:
                    await strategy.handle_completion(self, type_items, db)

            task_ids_completed = []
            task_ids_failed = []
            completed_task_events = {}

            # Tasks that should be preserved in DB after completion.
            # Only reference real TaskType members here — a non-existent
            # member raises AttributeError and crashes completion cleanup.
            PRESERVED_TASK_TYPES = set()

            for item in items:
                if item['status'] == TaskStatus.COMPLETED:
                    # Only delete if not in preserved types
                    if item['task_type'] not in PRESERVED_TASK_TYPES:
                        task_ids_completed.append(item['task_id'])
                    else:
                        logging.info(f"Preserving completed task {item['task_id']} of type {item['task_type']}")
                else:
                    task_ids_failed.append(item['task_id'])

            # Completion events are emitted after the rows are deleted. Keep a
            # snapshot first so consumers still receive the task target (for
            # example SCAN_ALBUM's album_id) and can invalidate the right UI.
            if task_ids_completed:
                completed_rows = db.query(Task).filter(Task.id.in_(task_ids_completed)).all()
                completed_task_events = {
                    row.id: {
                        'id': str(row.id),
                        'type': row.type,
                        'status': TaskStatus.COMPLETED.value,
                        'priority': row.priority,
                        'total_items': row.total_items or 0,
                        'processed_items': row.processed_items or 0,
                        'error': None,
                        'owner_id': str(row.owner_id) if row.owner_id else None,
                        'created_at': row.created_at.isoformat() if row.created_at else None,
                        'updated_at': datetime.now().isoformat(),
                        'payload': row.payload or {},
                    }
                    for row in completed_rows
                }

            if task_ids_completed:
                crud_task.delete_tasks_by_ids(db, task_ids_completed)

            if task_ids_failed:
                # Update failed tasks
                failed_mappings = []
                for item in items:
                    if item['status'] == TaskStatus.FAILED:
                         failed_mappings.append({
                             'id': item['task_id'],
                             'status': TaskStatus.FAILED,
                             'error': item.get('error')
                         })
                if failed_mappings:
                    db.bulk_update_mappings(Task, failed_mappings)
                    # Re-read to capture updated_at and notify SSE subscribers.
                    failed_rows = db.query(Task).filter(Task.id.in_(task_ids_failed)).all()
                    for row in failed_rows:
                        self._publish('task.updated', {
                            'id': str(row.id),
                            'type': row.type,
                            'status': row.status,
                            'priority': row.priority,
                            'total_items': row.total_items or 0,
                            'processed_items': row.processed_items or 0,
                            'error': row.error,
                            'owner_id': str(row.owner_id) if row.owner_id else None,
                            'created_at': row.created_at.isoformat() if row.created_at else None,
                            'updated_at': row.updated_at.isoformat() if row.updated_at else None,
                            'payload': row.payload or {},
                        })
            # Publish COMPLETED events BEFORE deletion so subscribers see the
            # terminal state (the row will be removed from the DB right after).
            for item in items:
                if item.get('status') == TaskStatus.COMPLETED:
                    event_data = completed_task_events.get(item['task_id'], {
                        'id': str(item['task_id']),
                        'type': item.get('task_type'),
                        'status': TaskStatus.COMPLETED.value,
                        'priority': 0,
                        'total_items': 0,
                        'processed_items': 0,
                        'error': None,
                        'owner_id': None,
                        'created_at': None,
                        'updated_at': datetime.now().isoformat(),
                        'payload': {},
                    })
                    self._publish('task.updated', event_data)
            db.commit()
        except Exception as e:
            logging.error(f"Failed to flush results: {e}", exc_info=True)
            db.rollback()
        finally:
            db.close()

    def add_task(self, db: Session, type: str, payload: dict, priority: int = None, owner_id: UUID = None):
        return crud_task.add_task(db, type, payload, priority, owner_id)

    def add_tasks(self, db: Session, tasks_data: List[Dict], owner_id: UUID = None):
        """Batch add tasks"""
        crud_task.add_tasks(db, tasks_data, owner_id)
