import { ref, onUnmounted, watch, type Ref } from 'vue';
import { buildNotificationsEventsUrl, notificationsApi, type AppNotification } from '@/api/notification';
import { tasksApi, type Task } from '@/api/tasks';

/**
 * Generic notification SSE channel. Subscribes to `/api/notifications/events`
 * — a single connection that carries:
 *  - `task.updated` / `task.created` / `task.retry` (bridged from TaskManager,
 *    live, not persisted),
 *  - `notification.created` / `notification.read` (persisted notifications).
 *
 * On 3 consecutive SSE failures we fall back to a 15s polling loop that
 * catches up via `tasksApi.fetchRecent` (task events) and
 * `notificationsApi.list` (notifications).
 */
export interface UseNotificationSSEOptions {
  token: Ref<string | null>;
  onEvent: (event: string, data: any) => void;
  enabled?: Ref<boolean>;
}

export interface UseNotificationSSEReturn {
  connected: Ref<boolean>;
  reconnecting: Ref<boolean>;
  lastEventAt: Ref<string | null>;
  forceReconnect: () => void;
}

export function useNotificationSSE(opts: UseNotificationSSEOptions): UseNotificationSSEReturn {
  const connected = ref(false);
  const reconnecting = ref(false);
  const lastEventAt = ref<string | null>(null);

  let source: EventSource | null = null;
  let reconnectTimer: number | null = null;
  let pollTimer: number | null = null;
  let consecutiveFailures = 0;
  let stopped = false;

  const enabled = opts.enabled ?? ref(true);

  const stop = () => {
    stopped = true;
    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (pollTimer !== null) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
    if (source) {
      try { source.close() } catch { /* ignore */ }
      source = null;
    }
    connected.value = false;
  };

  const startPollingFallback = () => {
    if (pollTimer !== null) return;
    // Last-resort polling after 3 consecutive SSE failures. Replays task
    // events via /tasks/recent and notifications via /notifications.
    pollTimer = window.setInterval(async () => {
      try {
        const since = lastEventAt.value ?? new Date(Date.now() - 15_000).toISOString();
        // task catch-up
        const tasks = await tasksApi.fetchRecent(since, 100, opts.token.value);
        if (Array.isArray(tasks)) {
          for (const t of tasks as Task[]) {
            opts.onEvent('task.updated', t);
            if (t.updated_at) lastEventAt.value = t.updated_at;
          }
        }
        // notification catch-up (unread only)
        const notifs = await notificationsApi.list({ unread: true, limit: 100 });
        if (Array.isArray(notifs)) {
          for (const n of notifs as AppNotification[]) {
            opts.onEvent('notification.created', n);
            if (n.created_at) lastEventAt.value = n.created_at;
          }
        }
      } catch {
        // swallow; will retry next tick
      }
    }, 15_000);
  };

  const connect = () => {
    if (stopped || !enabled.value || !opts.token.value) return;
    if (source) {
      try { source.close() } catch { /* ignore */ }
      source = null;
    }

    const url = buildNotificationsEventsUrl(opts.token.value);
    const es = new EventSource(url, { withCredentials: false });
    source = es;

    const onOpen = () => {
      connected.value = true;
      reconnecting.value = false;
      consecutiveFailures = 0;
    };

    const onError = () => {
      connected.value = false;
      es.close();
      source = null;
      consecutiveFailures += 1;
      if (consecutiveFailures >= 3) {
        startPollingFallback();
        return;
      }
      if (stopped) return;
      reconnecting.value = true;
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        connect();
      }, 3000);
    };

    const handle = (raw: MessageEvent) => {
      try {
        const data = JSON.parse(raw.data);
        if (data.updated_at) lastEventAt.value = data.updated_at;
        else if (data.created_at) lastEventAt.value = data.created_at;
        else if (data.ts) lastEventAt.value = data.ts;
        opts.onEvent(raw.type || 'notification.created', data);
      } catch {
        // Ignore malformed payloads (e.g. ping)
      }
    };

    es.addEventListener('open', onOpen);
    es.addEventListener('error', onError);
    es.addEventListener('hello', handle as EventListener);
    es.addEventListener('ping', handle as EventListener);
    es.addEventListener('task.updated', handle as EventListener);
    es.addEventListener('task.created', handle as EventListener);
    es.addEventListener('task.retry', handle as EventListener);
    es.addEventListener('notification.created', handle as EventListener);
    es.addEventListener('notification.read', handle as EventListener);
  };

  watch(
    () => [opts.token.value, enabled.value] as const,
    ([token, isEnabled]) => {
      if (!isEnabled || !token) {
        stop();
        return;
      }
      stopped = false;
      consecutiveFailures = 0;
      connect();
    },
    { immediate: true }
  );

  const forceReconnect = () => {
    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    consecutiveFailures = 0;
    if (pollTimer !== null) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
    if (source) {
      try { source.close() } catch { /* ignore */ }
      source = null;
    }
    connect();
  };

  onUnmounted(stop);

  return { connected, reconnecting, lastEventAt, forceReconnect };
}
