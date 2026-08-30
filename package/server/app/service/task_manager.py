import asyncio
import logging
import json
import multiprocessing
import threading
import time
from typing import List, Dict, Set, Any, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import or_, cast, String

from app.db.session import SessionLocal
from app.db.models.task import Task, TaskType, TaskStatus
from app.db.models.system import SystemState
from app.crud import task as crud_task
from app.worker import run_worker

class TaskManager:
    """
    Task Producer / Manager (Runs in API process)
    Responsible for:
    1. Creating tasks
    2. Querying task status
    3. Managing pause/resume state via DB
    4. Managing the background worker process
    """
    _instance = None
    
    def __init__(self):
        self.paused_categories: Set[str] = set()
        self.worker_process = None
        # SSE subscribers (one asyncio.Queue per connected client)
        self._subscribers: List[asyncio.Queue] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock = threading.Lock()
        # Worker lifecycle: a watchdog restarts the worker process if it dies
        # while there is still unfinished work in the DB.
        self._watchdog_thread = None
        self._watchdog_running = False
        self._stopping = False
        self._worker_lock = threading.Lock()
        self._worker_stop_event = None
        self._restart_thread = None
        self._restart_requested = False

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = TaskManager()
        return cls._instance

    def start_worker_if_needed(self):
        """安全地启动后台工作进程。

        若确实（重新）启动了 worker，说明有待处理任务即将运行——典型场景是
        用户重试/恢复任务时触发的冷启动。此时立即把当前活跃任务快照推给
        前端，避免界面停留在旧状态（worker 真正开始处理并发出 task.updated
        之前可能有一段延迟）。
        """
        with self._worker_lock:
            self._stopping = False
            started = self._start_worker_locked()
        if started:
            self._publish_active_tasks_snapshot()

    def start_worker_for_pending_tasks(self) -> bool:
        """Start the expensive worker process only when persisted work exists.

        A fresh desktop launch normally has no queued work. Spawning a second
        frozen Python process in that case adds several seconds to the time
        before FastAPI can report ready, while every task creation/retry path
        already starts the worker lazily.
        """
        db = SessionLocal()
        try:
            paused_types = set(self._load_system_state('paused_categories', []) or [])
            should_start = crud_task.count_dispatchable_tasks(db, paused_types) > 0
        finally:
            db.close()
        if should_start:
            self.start_worker_if_needed()
        return should_start

    def _start_worker_locked(self) -> bool:
        """启动后台工作进程（调用方需持有 _worker_lock）。

        返回 True 表示本次实际启动了新的 worker 进程；False 表示进程已存活，
        无需启动。"""
        # 1. 如果进程存在且活着 → 不处理
        if self.worker_process is not None:
            if self.worker_process.is_alive():
                return False
            else:
                # 进程已死，必须 join 清理僵尸进程
                try:
                    self.worker_process.join(timeout=1)
                except:
                    pass
                self.worker_process = None

        # 2. 启动新进程
        logging.info("Starting background task worker process...")
        # 用 multiprocessing.Queue 把 worker 的状态变更事件回传给 API 进程，
        # 由 API 进程派发到所有 SSE 订阅者。
        self._event_queue = multiprocessing.Queue(maxsize=4096)
        self._worker_stop_event = multiprocessing.Event()
        self._reader_thread = threading.Thread(
            target=self._event_queue_reader,
            daemon=True,
            name='TaskEventReader',
        )
        self._reader_thread.start()
        self.worker_process = multiprocessing.Process(
            target=run_worker,
            args=(self._event_queue, self._worker_stop_event),
            daemon=True,
            name="TaskWorker"
        )
        self.worker_process.start()
        logging.info(f"Worker process started with PID: {self.worker_process.pid}")
        return True

    def _event_queue_reader(self):
        """Drain events pushed by the worker subprocess and forward them to
        every connected SSE subscriber. Runs as a daemon thread in the API
        process."""
        q = self._event_queue
        if q is None:
            return
        while True:
            try:
                msg = q.get()
            except (EOFError, OSError):
                # Queue closed during shutdown
                return
            except Exception as e:
                logging.debug(f'event_queue_reader error: {e}')
                continue
            if not isinstance(msg, dict):
                if msg is None:
                    return
                continue
            event = msg.get('event') or 'task.updated'
            data = msg.get('data') or {}
            try:
                self.publish_event(event, data)
            except Exception as e:
                logging.debug(f'publish_event error: {e}')

    def stop_worker(self):
        """Stops the background worker process gracefully."""
        with self._worker_lock:
            self._stopping = True
            self._restart_requested = False
            if self.worker_process and self.worker_process.is_alive():
                logging.info("Terminating worker process...")
                self.worker_process.terminate()
                self.worker_process.join(timeout=5)
                if self.worker_process.is_alive():
                    logging.warning("Worker process did not terminate gracefully, killing...")
                    self.worker_process.kill()
                logging.info("Worker process stopped")
            self.worker_process = None
            self._worker_stop_event = None

    def restart_worker(self, *, graceful: bool = False) -> dict[str, str]:
        """Restart the worker, optionally draining accepted work first."""
        if not graceful:
            self.stop_worker()
            self.start_worker_if_needed()
            return {"status": "applied"}

        with self._worker_lock:
            process = self.worker_process
            stop_event = self._worker_stop_event
            if not process or not process.is_alive() or stop_event is None:
                apply_now = True
            elif self._restart_thread and self._restart_thread.is_alive():
                return {"status": "draining"}
            else:
                apply_now = False
                self._stopping = True
                self._restart_requested = True
                stop_event.set()
                self._restart_thread = threading.Thread(
                    target=self._finish_graceful_restart,
                    args=(process,),
                    daemon=True,
                    name="TaskWorkerConfigReload",
                )
                self._restart_thread.start()

        if apply_now:
            self.stop_worker()
            self.start_worker_if_needed()
            return {"status": "applied"}
        self.publish_event("task.worker", {"status": "draining"})
        return {"status": "draining"}

    def _finish_graceful_restart(self, process) -> None:
        process.join(timeout=180)
        if process.is_alive():
            logging.warning("Worker drain timed out; terminating it to apply settings")
            process.terminate()
            process.join(timeout=5)
            if process.is_alive():
                process.kill()
        with self._worker_lock:
            if self.worker_process is process:
                self.worker_process = None
                self._worker_stop_event = None
            should_restart = self._restart_requested
            self._restart_requested = False
            self._stopping = not should_restart
            started = self._start_worker_locked() if should_restart else False
        self.publish_event("task.worker", {"status": "applied"})
        if started:
            self._publish_active_tasks_snapshot()

    def start_watchdog(self):
        """Starts a daemon thread that restarts the worker if it dies while
        there is still unfinished work in the DB."""
        if not self._watchdog_running:
            self._watchdog_running = True
            self._watchdog_thread = threading.Thread(
                target=self._watchdog_loop, daemon=True, name="WorkerWatchdog"
            )
            self._watchdog_thread.start()
            logging.info("Started worker watchdog thread.")

    def stop_watchdog(self):
        """Stops the worker watchdog thread."""
        self._watchdog_running = False
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            self._watchdog_thread.join(timeout=2)
            logging.info("Stopped worker watchdog thread.")

    def _watchdog_loop(self):
        """Periodically check the worker process. If it is dead and there are
        pending/processing tasks in the DB, restart it so the recovery path
        (which resets stuck PROCESSING tasks back to PENDING) can run.

        Intentional idle-exits (no unfinished work) are NOT restarted here —
        the worker will be lazily started on the next add_task/retry/resume.
        """
        while self._watchdog_running:
            for _ in range(15):
                if not self._watchdog_running:
                    return
                time.sleep(1)
            try:
                if self._stopping:
                    continue
                wp = self.worker_process
                if wp is not None and wp.is_alive():
                    continue
                # Worker is dead (or never started). Only restart if there is
                # dispatchable unfinished work; otherwise respect the idle-exit.
                # Tasks belonging to paused categories are intentionally not
                # processed, so they must not trigger a restart — otherwise the
                # worker would idle-exit and be yanked back forever.
                db = SessionLocal()
                try:
                    paused_types = set(self._load_system_state('paused_categories', []) or [])
                    dispatchable = crud_task.count_dispatchable_tasks(db, paused_types)
                    pending = crud_task.count_tasks_by_status(db, TaskStatus.PENDING)
                    processing = crud_task.count_tasks_by_status(db, TaskStatus.PROCESSING)
                finally:
                    db.close()
                if dispatchable > 0:
                    logging.warning(
                        f"Worker process dead with {pending} pending + {processing} processing "
                        f"tasks ({dispatchable} dispatchable, {pending + processing - dispatchable} paused); "
                        f"restarting to recover."
                    )
                    self.start_worker_if_needed()
            except Exception as e:
                logging.error(f"Watchdog error: {e}")

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

    def get_status(self):
        """Get global scan status from DB"""
        return {
            'fast_mode': self._load_system_state('fast_mode', False)
        }

    def get_grouped_status(self, db: Session):
        """Get task counts grouped by category"""
        # Always refresh paused categories from DB
        paused_list = self._load_system_state('paused_categories', [])
        self.paused_categories = set(paused_list)

        return crud_task.get_grouped_status(db, self.paused_categories)

    def pause_category(self, category: str):
        # Refresh first
        paused_list = self._load_system_state('paused_categories', [])
        self.paused_categories = set(paused_list)

        self.paused_categories.add(category)
        self._save_system_state('paused_categories', list(self.paused_categories))
        logging.info(f"Paused task category: {category}")

    def resume_category(self, category: str):
        # Refresh first
        paused_list = self._load_system_state('paused_categories', [])
        self.paused_categories = set(paused_list)

        if category in self.paused_categories:
            self.paused_categories.remove(category)
            self._save_system_state('paused_categories', list(self.paused_categories))
            self.start_worker_if_needed()
            logging.info(f"Resumed task category: {category}")

    def set_fast_mode(self, enabled: bool):
        self._save_system_state('fast_mode', enabled)
        logging.info(f"Fast Mode set to {enabled} via TaskManager")

    def retry_task(self, db: Session, task: Task):
        """Retry a failed task"""
        task = crud_task.retry_task(db, task)
        self.start_worker_if_needed()
        try:
            self.publish_task_update(task, event='task.retry')
        except Exception as e:
            logging.debug(f'publish_task_update failed: {e}')
        return task

    def retry_all_failed_tasks(self, db: Session, types: Optional[List[str]] = None):
        """Retry all failed tasks. Optionally filter by task types."""
        # 先记录待重试的失败任务 id，重试后逐条推送 task.retry，让前端立即把
        # 这些任务从「失败」列表移走——即便 worker 已经在运行、不会冷启动，
        # 也能即时反馈重试结果。
        failed_q = db.query(Task).filter(Task.status == TaskStatus.FAILED)
        if types:
            failed_q = failed_q.filter(Task.type.in_(types))
        failed_ids = [row.id for row in failed_q.order_by(Task.created_at.desc()).limit(500).all()]

        result = crud_task.retry_all_failed_tasks(db, types=types)
        if result > 0:
            self.start_worker_if_needed()
            if failed_ids:
                retried = crud_task.get_tasks_by_ids(db, failed_ids)
                for task in retried:
                    try:
                        self.publish_task_update(task, event='task.retry')
                    except Exception as e:
                        logging.debug(f'publish task.retry failed: {e}')
        return {"message": f"Retried {result} failed tasks", "count": result}

    def add_task(self, db: Session, type: str, payload: dict, priority: Optional[int] = None, owner_id: UUID = None):
        # 防重复入队：SCAN_FOLDER 是幂等的全量扫描任务，若已有 PENDING/PROCESSING
        # 的同类任务，则直接复用，避免并发扫描导致同一文件被入库多次。。
        if type == TaskType.SCAN_FOLDER or type == TaskType.SCAN_FOLDER.value:
            try:
                target_user_id = None
                if payload and isinstance(payload, dict):
                    target_user_id = payload.get('user_id')
                if not target_user_id and owner_id is not None:
                    target_user_id = str(owner_id)

                query = db.query(Task).filter(
                    Task.type == TaskType.SCAN_FOLDER,
                    Task.status.in_([TaskStatus.PENDING, TaskStatus.PROCESSING])
                )
                if target_user_id:
                    # 兼容两种情况：payload 里带 user_id，或 owner_id 列匹配
                    query = query.filter(or_(
                        cast(Task.owner_id, String) == str(target_user_id),
                        Task.payload['user_id'].as_string() == str(target_user_id),
                    ))
                existing_scan = query.order_by(Task.created_at.desc()).first()
                if existing_scan:
                    logging.info(
                        f"SCAN_FOLDER already {existing_scan.status} for user={target_user_id}, "
                        f"skip creating duplicate. Reusing task={existing_scan.id}"
                    )
                    return existing_scan
            except Exception as e:
                logging.warning(f"SCAN_FOLDER dedup check failed, falling back to create: {e}")

        task = crud_task.add_task(db, type, payload, priority, owner_id)
        logging.info(f"Added task: {task.type} with priority {task.priority}")
        self.start_worker_if_needed()
        try:
            self.publish_task_update(task, event='task.created')
        except Exception as e:
            logging.debug(f'publish_task_update failed: {e}')
        return task

    # ------------------------------------------------------------------
    # SSE publish / subscribe helpers
    # ------------------------------------------------------------------
    def attach_loop(self, loop: asyncio.AbstractEventLoop):
        """Called from the API process event loop so cross-thread publishes
        can be scheduled on the right loop via `call_soon_threadsafe`."""
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        with self._lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    def publish_event(self, event: str, data: Dict[str, Any]):
        """Push an SSE event to every connected subscriber. Safe to call from
        the worker subprocess reader thread or any FastAPI handler thread.

        ``asyncio.Queue`` is NOT thread-safe, so the actual ``put_nowait`` must
        run on the event loop thread. When a loop is attached we schedule
        ``_do_publish`` via ``call_soon_threadsafe``; this is a no-op overhead
        when already on the loop thread and correct when called cross-thread.
        """
        loop = self._loop
        if loop is not None:
            try:
                loop.call_soon_threadsafe(self._do_publish, event, data)
                return
            except RuntimeError:
                # Loop closed during shutdown — fall through and drop directly.
                return
        # No loop attached: best-effort direct publish.
        self._do_publish(event, data)

    def _do_publish(self, event: str, data: Dict[str, Any]):
        for q in list(self._subscribers):
            try:
                if q.full():
                    try:
                        q.get_nowait()
                    except Exception:
                        pass
                q.put_nowait({'event': event, 'data': data})
            except Exception:
                # Subscriber went away mid-flight; ignore.
                pass
        # 桥接到通用通知通道（按 owner_id 路由，纯内存转发，不落库）。
        # 前端只需订阅 /notifications/events 一条 SSE 即可同时收到
        # task.* live 事件与 notification.* 落库通知。
        try:
            from app.service.notification_manager import NotificationManager
            NotificationManager.get_instance().publish_to_user(
                data.get('owner_id') if isinstance(data, dict) else None,
                event,
                data,
            )
        except Exception as e:
            logging.debug(f'bridge task event to NotificationManager failed: {e}')

    def publish_task_update(self, task: Task, event: str = 'task.updated'):
        payload = {
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
            'attempt_count': getattr(task, 'attempt_count', 0) or 0,
            'next_retry_at': (
                task.next_retry_at.isoformat()
                if getattr(task, 'next_retry_at', None)
                else None
            ),
        }
        self.publish_event(event, payload)

    def _publish_active_tasks_snapshot(self):
        """Worker（重新）启动时，把当前 PENDING / PROCESSING 任务快照推给前端。

        覆盖「用户重试/恢复任务 → worker 冷启动」的场景：此时 worker 尚未发出
        自身的 PENDING→PROCESSING 事件，前端界面可能仍停留在旧状态。逐条推送
        task.updated 让侧栏/铃铛立即刷新（前端按 id 去重 upsert，重复无害）。
        """
        try:
            db = SessionLocal()
            try:
                tasks = (
                    db.query(Task)
                    .filter(Task.status.in_([TaskStatus.PENDING, TaskStatus.PROCESSING]))
                    .order_by(Task.created_at.desc())
                    .limit(200)
                    .all()
                )
                for task in tasks:
                    try:
                        self.publish_task_update(task, event='task.updated')
                    except Exception as e:
                        logging.debug(f'snapshot publish failed for task {task.id}: {e}')
            finally:
                db.close()
        except Exception as e:
            logging.debug(f'_publish_active_tasks_snapshot failed: {e}')

    def add_tasks(self, db: Session, tasks_data: List[Dict], owner_id: UUID = None):
        """Batch add tasks"""
        crud_task.add_tasks(db, tasks_data, owner_id)
        self.start_worker_if_needed()
        try:
            for t in tasks_data or []:
                self.publish_event('task.created', {
                    'type': t.get('type'),
                    'status': TaskStatus.PENDING.value,
                    'priority': t.get('priority', 0),
                    'owner_id': str(t.get('owner_id') or owner_id) if (t.get('owner_id') or owner_id) else None,
                    'payload': t.get('payload', {}),
                })
        except Exception as e:
            logging.debug(f'add_tasks publish failed: {e}')
