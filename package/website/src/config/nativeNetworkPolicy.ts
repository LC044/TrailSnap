import { getServerUrl, isMobileApp } from './server'

let installed = false

function isAllowed(value: string | URL): boolean {
  const raw = value.toString()
  if (/^(?:data:|blob:|file:|content:|capacitor:)/i.test(raw)) return true
  let target: URL
  try {
    target = new URL(raw, window.location.href)
  } catch {
    return false
  }
  if (!['http:', 'https:', 'ws:', 'wss:'].includes(target.protocol)) return false
  if (target.hostname === 'localhost' || target.hostname === '127.0.0.1' || target.hostname === '[::1]') return true

  const configured = getServerUrl()
  // The connection screen must be able to test the address the user enters.
  // Once saved, the exact-origin rule below becomes mandatory.
  if (!configured) return true
  const server = new URL(configured, window.location.href)
  const targetProtocol = target.protocol.replace(/^ws/, 'http')
  return targetProtocol === server.protocol && target.host === server.host
}

function reject(kind: string, value: string | URL): never {
  console.warn(`[TrailSnap] blocked external ${kind}`)
  throw new TypeError('TrailSnap App 仅允许连接当前自部署 Server')
}

/** Browser-layer guard, primarily for iOS and WebSocket/sendBeacon coverage. */
export function installNativeNetworkPolicy(): void {
  if (!isMobileApp() || installed) return
  installed = true

  const originalFetch = window.fetch.bind(window)
  window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    const url = input instanceof Request ? input.url : input
    if (!isAllowed(url)) return Promise.reject(new TypeError('TrailSnap App 已阻止外部网络请求'))
    return originalFetch(input, init)
  }) as typeof window.fetch

  const originalOpen = XMLHttpRequest.prototype.open
  XMLHttpRequest.prototype.open = function(method: string, url: string | URL, ...rest: any[]) {
    if (!isAllowed(url)) reject('XMLHttpRequest', url)
    return originalOpen.call(this, method, url, ...rest as [boolean?, string?, string?])
  } as typeof XMLHttpRequest.prototype.open

  const NativeEventSource = window.EventSource
  window.EventSource = new Proxy(NativeEventSource, {
    construct(target, args, newTarget) {
      if (!isAllowed(args[0])) reject('EventSource', args[0])
      return Reflect.construct(target, args, newTarget)
    },
  })

  const NativeWebSocket = window.WebSocket
  window.WebSocket = new Proxy(NativeWebSocket, {
    construct(target, args, newTarget) {
      if (!isAllowed(args[0])) reject('WebSocket', args[0])
      return Reflect.construct(target, args, newTarget)
    },
  })

  const originalBeacon = navigator.sendBeacon?.bind(navigator)
  if (originalBeacon) {
    navigator.sendBeacon = ((url: string | URL, data?: BodyInit | null) =>
      isAllowed(url) ? originalBeacon(url, data) : false) as typeof navigator.sendBeacon
  }
}
