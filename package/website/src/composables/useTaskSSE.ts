import { ref, onUnmounted, watch, type Ref } from 'vue'
import { buildTaskEventsUrl, tasksApi, type Task } from '@/api/tasks'

export interface UseTaskSSEOptions {
  token: Ref<string | null>
  onEvent: (event: string, data: Task) => void
  enabled?: Ref<boolean>
}

export interface UseTaskSSEReturn {
  connected: Ref<boolean>
  reconnecting: Ref<boolean>
  lastEventAt: Ref<string | null>
  forceReconnect: () => void
}

/**
 * Subscribe to /api/tasks/events. The native EventSource does not support
 * custom headers, so we authenticate with a `?token=` query param. On
 * disconnect we wait 3s, then re-open. After every successful connection
 * we replay the events that happened while we were away via the
 * /api/tasks/recent endpoint.
 */
export function useTaskSSE(opts: UseTaskSSEOptions): UseTaskSSEReturn {
  const connected = ref(false)
  const reconnecting = ref(false)
  const lastEventAt = ref<string | null>(null)

  let source: EventSource | null = null
  let reconnectTimer: number | null = null
  let pollTimer: number | null = null
  let consecutiveFailures = 0
  let stopped = false

  const enabled = opts.enabled ?? ref(true)

  const stop = () => {
    stopped = true
    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (pollTimer !== null) {
      window.clearInterval(pollTimer)
      pollTimer = null
    }
    if (source) {
      try { source.close() } catch { /* ignore */ }
      source = null
    }
    connected.value = false
  }

  const startPollingFallback = () => {
    if (pollTimer !== null) return
    // Last-resort polling path used after 3 consecutive SSE failures.
    pollTimer = window.setInterval(async () => {
      try {
        const since = lastEventAt.value ?? new Date(Date.now() - 15_000).toISOString()
        const items = await tasksApi.fetchRecent(since, 100, opts.token.value)
        if (Array.isArray(items)) {
          for (const item of items) {
            opts.onEvent('task.updated', item)
            if (item.updated_at) lastEventAt.value = item.updated_at
          }
        }
      } catch (e) {
        // swallow; will retry next tick
      }
    }, 15_000)
  }

  const connect = () => {
    if (stopped || !enabled.value || !opts.token.value) return
    if (source) {
      try { source.close() } catch { /* ignore */ }
      source = null
    }

    const url = buildTaskEventsUrl(opts.token.value)
    const es = new EventSource(url, { withCredentials: false })
    source = es

    const onOpen = () => {
      connected.value = true
      reconnecting.value = false
      consecutiveFailures = 0
    }

    const onError = () => {
      connected.value = false
      es.close()
      source = null
      consecutiveFailures += 1
      if (consecutiveFailures >= 3) {
        // Stop trying SSE; rely on the polling fallback.
        startPollingFallback()
        return
      }
      if (stopped) return
      reconnecting.value = true
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null
        connect()
      }, 3000)
    }

    const handle = (raw: MessageEvent) => {
      try {
        const data = JSON.parse(raw.data) as Task & { ts?: string }
        if (data.updated_at) lastEventAt.value = data.updated_at
        else if (data.ts) lastEventAt.value = data.ts
        opts.onEvent(raw.type || 'task.updated', data)
      } catch (e) {
        // Ignore malformed payloads (e.g. ping)
      }
    }

    es.addEventListener('open', onOpen)
    es.addEventListener('error', onError)
    es.addEventListener('hello', handle as EventListener)
    es.addEventListener('ping', handle as EventListener)
    es.addEventListener('task.updated', handle as EventListener)
    es.addEventListener('task.created', handle as EventListener)
    es.addEventListener('task.retry', handle as EventListener)
  }

  // React to token / enabled changes
  watch(
    () => [opts.token.value, enabled.value] as const,
    ([token, isEnabled]) => {
      if (!isEnabled || !token) {
        stop()
        return
      }
      stopped = false
      consecutiveFailures = 0
      connect()
    },
    { immediate: true }
  )

  const forceReconnect = () => {
    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    consecutiveFailures = 0
    if (pollTimer !== null) {
      window.clearInterval(pollTimer)
      pollTimer = null
    }
    if (source) {
      try { source.close() } catch { /* ignore */ }
      source = null
    }
    connect()
  }

  onUnmounted(stop)

  return { connected, reconnecting, lastEventAt, forceReconnect }
}