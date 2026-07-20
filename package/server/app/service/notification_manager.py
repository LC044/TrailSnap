"""通用通知 pub/sub 单例。

照抄 `TaskManager` 的 SSE pub/sub 结构，但订阅按 user_id 路由：
- `subscribe(user_id)` 把队列与 user_id 绑定；
- `publish_to_user(user_id, event, data)` 只投递给该用户的队列，
  `user_id is None` 时广播给所有订阅者。

task.* 事件由 `TaskManager._do_publish` 转发进来（纯内存，不落库）；
UPDATE/SYSTEM 等离散通知由 `app/api/notification.py` 落库后调用本管理器推送。
"""
import asyncio
import threading
from typing import Any, Dict, List, Optional, Tuple
import logging

logger = logging.getLogger("app.service.notification_manager")


class NotificationManager:
    _instance: Optional["NotificationManager"] = None

    def __init__(self):
        # 每个订阅者：(user_id, queue)。user_id 可能为 None（兼容旧广播）。
        self._subscribers: List[Tuple[Any, asyncio.Queue]] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "NotificationManager":
        if cls._instance is None:
            cls._instance = NotificationManager()
        return cls._instance

    # ------------------------------------------------------------------
    # loop binding
    # ------------------------------------------------------------------
    def attach_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    # ------------------------------------------------------------------
    # subscribe / unsubscribe
    # ------------------------------------------------------------------
    def subscribe(self, user_id: Any) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        with self._lock:
            self._subscribers.append((user_id, q))
        return q

    def unsubscribe(self, q: asyncio.Queue):
        with self._lock:
            self._subscribers = [(uid, sub) for (uid, sub) in self._subscribers if sub is not q]

    # ------------------------------------------------------------------
    # publish
    # ------------------------------------------------------------------
    def publish_to_user(self, user_id: Any, event: str, data: Dict[str, Any]):
        """Push an event to subscribers of the given user.

        ``user_id is None`` broadcasts to every subscriber. Safe to call
        from any thread (the actual ``put_nowait`` runs on the loop thread
        via ``call_soon_threadsafe``).
        """
        loop = self._loop
        if loop is not None:
            try:
                loop.call_soon_threadsafe(self._do_publish, user_id, event, data)
                return
            except RuntimeError:
                # Loop closed during shutdown — drop.
                return
        self._do_publish(user_id, event, data)

    def _do_publish(self, user_id: Any, event: str, data: Dict[str, Any]):
        for (uid, q) in list(self._subscribers):
            # user_id is None => 广播；否则只投给匹配用户。
            if user_id is not None and uid is not None and str(uid) != str(user_id):
                continue
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
