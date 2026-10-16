interface NetworkConnection extends EventTarget {
  saveData?: boolean
  effectiveType?: string
  type?: string
  downlink?: number
  rtt?: number
}

export function canPreloadPages(): boolean {
  const connection = (navigator as Navigator & { connection?: NetworkConnection }).connection
  if (!navigator.onLine || !connection || connection.saveData) return false
  if (connection.effectiveType && connection.effectiveType !== '4g') return false
  if (connection.effectiveType !== '4g' && !['wifi', 'ethernet'].includes(connection.type || '')) return false
  if (connection.downlink !== undefined && connection.downlink < 2) return false
  if (connection.rtt !== undefined && connection.rtt > 300) return false
  return true
}

// One import per idle slot; conditions are checked again before every import.
// Already-started imports cannot be cancelled. Failed preloads stay silent and
// are left for explicit navigation to retry.
export function schedulePagePreloads(loaders: Array<() => Promise<unknown>>, ready: () => boolean) {
  let stopped = false
  let index = 0
  let timer: ReturnType<typeof setTimeout> | undefined
  let idle: number | undefined
  const tick = () => {
    if (stopped || index >= loaders.length) return
    timer = setTimeout(() => {
      if (stopped) return
      if (!ready() || document.visibilityState !== 'visible' || !canPreloadPages()) {
        tick()
        return
      }
      if (!window.requestIdleCallback) return // No reliable idle signal: skip speculative work.
      idle = window.requestIdleCallback(async () => {
        if (stopped) return
        if (ready() && document.visibilityState === 'visible' && canPreloadPages()) {
          try { await loaders[index++]!() } catch { /* User navigation owns error feedback. */ }
        }
        tick()
      })
    }, 3000)
  }
  const start = () => tick()
  if (document.readyState === 'complete') start()
  else window.addEventListener('load', start, { once: true })
  return () => {
    stopped = true
    clearTimeout(timer)
    if (idle !== undefined) window.cancelIdleCallback(idle)
    window.removeEventListener('load', start)
  }
}
