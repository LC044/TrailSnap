export const TASK_REFRESH_INTERVAL = 4000

// Leading + trailing throttle: new events never postpone a scheduled refresh.
export function createTaskRefresh(refresh: () => void) {
  let lastRun = -Infinity
  let timer: ReturnType<typeof setTimeout> | undefined
  const run = () => {
    timer = undefined
    lastRun = Date.now()
    refresh()
  }
  return {
    schedule() {
      if (timer !== undefined) return
      const delay = Math.max(0, TASK_REFRESH_INTERVAL - (Date.now() - lastRun))
      if (delay === 0) run()
      else timer = setTimeout(run, delay)
    },
    cancel() {
      if (timer !== undefined) clearTimeout(timer)
      timer = undefined
    },
  }
}

// One entry, scoped to server and credentials; stale requests cannot replace it.
export function createTaskStatusCache<T>() {
  let entry: { scope: string; at: number; pending: boolean; promise: Promise<T> } | undefined
  return (scope: string, load: () => Promise<T>) => {
    if (entry?.scope === scope && (entry.pending || Date.now() - entry.at < 3000)) return entry.promise
    const current = { scope, at: Date.now(), pending: true, promise: Promise.resolve().then(load) }
    entry = current
    current.promise.then(
      () => { current.pending = false },
      () => { if (entry === current) entry = undefined },
    )
    return current.promise
  }
}
