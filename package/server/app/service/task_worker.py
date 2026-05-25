import os
import asyncio
import logging
import concurrent.futures
import json
from re import S
from typing import List, Dict, Set, Any
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models.task import Task, TaskType, TaskStatus, DEFAULT_PRIORITIES
from app.db.models.system import SystemState
from app.core.system_config import system_config
from app.crud.task import DEFAULT_SCAN_STATUS
from app.crud import task as crud_task

from app.service.task_strategy import TaskStrategyFactory
# Import tasks to register strategies
from app.service.tasks import thumbnail, metadata, scan, face, ocr, classification, image_embedding, visual_description, basic, duplicate, similar, tickets

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

    async def put_batch(self, category: str, batch: List[Dict], priority: int = 1):
        if category in self.queues:
            # priority is inverted because PriorityQueue retrieves lowest first
            count = next(self._counters[category])
            await self.queues[category].put((-priority, count, batch))

    async def get_batch(self, category: str) -> List[Dict]:
        if category in self.queues:
            item = await self.queues[category].get()
            return item[2]
        return []

    def qsize(self, category: str) -> int:
        if category in self.queues:
            return self.queues[category].qsize()
        return 0

    def task_done(self, category: str):
        if category in self.queues:
            self.queues[category].task_done()


def get_chunk_size(task_type):
    chunk_size = 8
    if task_type == TaskType.PROCESS_BASIC:
        chunk_size = 1
    if task_type == TaskType.VISUAL_DESCRIPTION:
        chunk_size = 2
    elif task_type == TaskType.OCR:
        chunk_size = 4
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

    def start(self):
        if self.running:
            return
        self.running = True
        self._recover_unfinished_tasks()

        # Load fast_mode state
        self.fast_mode = self._load_system_state('fast_mode', False)
        max_workers = system_config.config.task.max_concurrent_tasks
        self.process_pool = concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count())
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers * 2) # More threads for IO

        self.worker_task = asyncio.create_task(self.worker_loop())
        self.result_task = asyncio.create_task(self.result_loop())
        self.cpu_consumer_task = asyncio.create_task(self.consumer_loop('CPU'))
        self.io_consumer_task = asyncio.create_task(self.consumer_loop('IO'))
        self.ai_consumer_task = asyncio.create_task(self.consumer_loop('AI'))
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

    def _sync_system_state_if_needed(self):
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
            if active_cpu_count > 0 and self.process_pool is None:
                logging.info(f"Restarting process pool")
                max_workers = max(1, system_config.config.task.max_concurrent_tasks)
                self.process_pool = concurrent.futures.ProcessPoolExecutor(max_workers=max_workers)
            if self.thread_pool is None and active_io_count > 0:
                max_workers = system_config.config.task.max_concurrent_tasks
                logging.info(f"Restarting thread pool")
                self.thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers * 2)

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

    def _fetch_tasks_to_queues_sync(self, allowed_types: List[str], current_qsizes: Dict[str, int]) -> Dict[str, List[Dict]]:
        db = SessionLocal()
        tasks_by_type = {}
        try:
            # We will fetch up to max_batch_size per category if its queue is below threshold
            # Keep the local Docker setup gentle. The original queue sizes can
            # mark hundreds of tasks as PROCESSING before they actually run,
            # which is painful when NAS IO or Docker Desktop storage stalls.
            max_tasks = max(1, system_config.config.task.max_concurrent_tasks)
            QUEUE_THRESHOLD = max_tasks
            FETCH_BATCH_SIZE = max_tasks

            # Filter allowed types based on current queue size, then fetch per
            # category. A single global priority query lets PROCESS_BASIC fill
            # every fetch window and starve AI work such as VISUAL_DESCRIPTION.
            types_by_category = {}
            for t in allowed_types:
                task_Factory = TaskStrategyFactory.get_strategy(t)
                if not task_Factory: continue
                cat = task_Factory.task_category
                if cat and current_qsizes.get(cat, 0) < QUEUE_THRESHOLD:
                    types_by_category.setdefault(cat, []).append(t)

            if not types_by_category:
                return {}

            for category, types_to_fetch in types_by_category.items():
                tasks = (
                    db.query(Task)
                    .filter(Task.status == TaskStatus.PENDING)
                    .filter(Task.type.in_(types_to_fetch))
                    .order_by(Task.priority.desc(), Task.created_at.asc())
                    .limit(FETCH_BATCH_SIZE)
                    .all()
                )
                for task in tasks:
                    if task.type not in tasks_by_type:
                        tasks_by_type[task.type] = []

                    task.status = TaskStatus.PROCESSING
                    self.last_active_time[task.type] = datetime.now()
                    tasks_by_type[task.type].append({'id': task.id, 'type': task.type, 'priority': task.priority})

            if tasks_by_type:
                db.commit()

            # Split tasks into smaller batches of max 8 items

            split_tasks_by_type = {}
            for task_type, task_list in tasks_by_type.items():
                split_tasks_by_type[task_type] = []
                chunk_size = get_chunk_size(task_type)
                for i in range(0, len(task_list), chunk_size):
                    chunk = task_list[i:i + chunk_size]
                    split_tasks_by_type[task_type].append(chunk)
            return split_tasks_by_type
        except Exception as e:
            logging.error(f"Error fetching tasks: {e}")
            return {}
        finally:
            db.close()

    async def consumer_loop(self, category: str):
        logging.info(f"TaskWorker {category} consumer loop started")

        # Configure max concurrency per consumer category based on system settings
        # or Fast Mode. Using Semaphores to allow multiple batches to run concurrently.
        max_concurrency = 1
        configured_workers = max(1, system_config.config.task.max_concurrent_tasks)
        if category == 'CPU':
            max_concurrency = configured_workers
        elif category == 'IO':
            max_concurrency = configured_workers
        elif category == 'AI':
            max_concurrency = configured_workers

        semaphore = asyncio.Semaphore(max_concurrency)

        while self.running:
            try:
                # 必须先获取 semaphore 才能从队列拿任务，防止由于并发超限导致高优先级任务被取出后隐藏在内存中
                await semaphore.acquire()

                # 为了防止被无限期阻塞导致无法响应停止信号（self.running=False）
                # 我们使用 wait_for，并设置一个较短的超时时间
                try:
                    batch = await asyncio.wait_for(self.queue_manager.get_batch(category), timeout=1.0)
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
        db = SessionLocal()
        db.expire_on_commit = False  # Prevent lazy loading issues after intermediate commits
        try:
            tasks = crud_task.get_tasks_by_ids(db, task_ids)
            if not tasks:
                return
            if task_type in self.paused_categories:
                for t in tasks:
                    t.status = TaskStatus.PENDING
                db.commit()
                return
            try:
                # Use strategy's category for timeout logic
                strategy = TaskStrategyFactory.get_strategy(task_type)
                if not strategy:
                    raise ValueError(f"Strategy not found for task type: {task_type}")
                results = await asyncio.wait_for(strategy.process_batch(self, tasks, db), timeout=strategy.timeout)
                for res in results:
                    await self.result_queue.put(res)
            except asyncio.TimeoutError:
                logging.error(f"Task batch {task_type} timed out after {strategy.timeout} seconds")
                for task_id in task_ids:
                    await self.result_queue.put({
                        'task_id': task_id,
                        'task_type': task_type,
                        'status': TaskStatus.FAILED,
                        'error': f"Task batch timed out after {strategy.timeout} seconds"
                    })
            except Exception as e:
                logging.error(f"Task batch {task_type} failed: {e}", exc_info=True)
                for task_id in task_ids:
                    await self.result_queue.put({
                        'task_id': task_id,
                        'task_type': task_type,
                        'status': TaskStatus.FAILED,
                        'error': str(e)
                    })
        except Exception as e:
            logging.error(f"Error in task batch wrapper for {task_type}: {e}")
        finally:
            db.close()

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
                if not allowed_types:
                    await asyncio.sleep(0.1)
                    continue

                current_qsizes = {
                    'CPU': self.queue_manager.qsize('CPU'),
                    'IO': self.queue_manager.qsize('IO'),
                    'AI': self.queue_manager.qsize('AI')
                }

                tasks_by_type = await asyncio.to_thread(self._fetch_tasks_to_queues_sync, allowed_types, current_qsizes)
                dispatched_count = 0

                for task_type, chunked_lists in tasks_by_type.items():
                    task_factory = TaskStrategyFactory.get_strategy(task_type)
                    if not task_factory:
                        continue
                    category = task_factory.task_category

                    if category:
                        for chunk in chunked_lists:
                            # Using the priority of the first task in the batch for the queue
                            priority = DEFAULT_PRIORITIES.get(task_type, 1)
                            await self.queue_manager.put_batch(category, chunk, priority=priority)
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
                    logging.info(f"Flushing {len(pending_items)} results")
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

            # Tasks that should be preserved in DB after completion
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
            db.commit()
        except Exception as e:
            logging.error(f"Failed to flush results: {e}", exc_info=True)
            db.rollback()
        finally:
            db.close()

    def add_task(self, db: Session, type: str, payload: dict, priority: int = 0, owner_id: UUID = None):
        return crud_task.add_task(db, type, payload, priority, owner_id)

    def add_tasks(self, db: Session, tasks_data: List[Dict], owner_id: UUID = None):
        """Batch add tasks"""
        crud_task.add_tasks(db, tasks_data, owner_id)
