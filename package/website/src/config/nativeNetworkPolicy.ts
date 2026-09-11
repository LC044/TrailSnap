import { Capacitor, registerPlugin } from '@capacitor/core'

let installed = false
let getConfiguredServerUrl: () => string = () => ''
const temporaryServerOrigins = new Map<string, number>()

interface NativeNetworkPolicyPlugin {
  allowTemporaryOrigin(options: { origin: string; ttlMs: number }): Promise<void>
  revokeTemporaryOrigin(options: { origin: string }): Promise<void>
}

const NativeNetworkPolicy = registerPlugin<NativeNetworkPolicyPlugin>('NativeNetworkPolicy')

function requestOrigin(value: string | URL): string {
  const url = new URL(value.toString(), window.location.href)
  if (url.protocol === 'ws:') url.protocol = 'http:'
  if (url.protocol === 'wss:') url.protocol = 'https:'
  return url.origin
}

/**
 * Mirror a candidate origin into the native WebView boundary
 * (OfflineOnlyWebViewClient). Android intercepts requests below the JS layer;
 * without this sync the same-origin rule there rejects the health check with
 * a CORS-less 403, which surfaces as "Failed to fetch". Older Apps and
 * browser/e2e runtimes have no native plugin — the call rejects there and is
 * fine to ignore.
 */
async function syncTemporaryOriginToNative(origin: string, allowed: boolean): Promise<void> {
  if (!Capacitor.isNativePlatform()) return
  try {
    if (allowed) await NativeNetworkPolicy.allowTemporaryOrigin({ origin, ttlMs: 30_000 })
    else await NativeNetworkPolicy.revokeTemporaryOrigin({ origin })
  } catch {
    // Plugin missing (web runtime or pre-plugin build) — JS guard still applies.
  }
}

/** Temporarily allow one candidate Server while its health endpoint is verified. */
export async function withTemporaryServerAccess<T>(
  serverUrl: string,
  operation: () => Promise<T>,
): Promise<T> {
  const origin = requestOrigin(serverUrl)
  const first = !temporaryServerOrigins.has(origin)
  temporaryServerOrigins.set(origin, (temporaryServerOrigins.get(origin) || 0) + 1)
  // The native boundary must be open before the first request goes out; the
  // revoke below must only run after the last concurrent operation finished.
  if (first) await syncTemporaryOriginToNative(origin, true)
  try {
    return await operation()
  } finally {
    const remaining = (temporaryServerOrigins.get(origin) || 1) - 1
    if (remaining > 0) temporaryServerOrigins.set(origin, remaining)
    else {
      temporaryServerOrigins.delete(origin)
      if (first) void syncTemporaryOriginToNative(origin, false)
    }
  }
}

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
  if (temporaryServerOrigins.has(requestOrigin(target))) return true

  const configured = getConfiguredServerUrl()
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
export function installNativeNetworkPolicy(serverUrlProvider: () => string): void {
  if (!Capacitor.isNativePlatform() || installed) return
  installed = true
  getConfiguredServerUrl = serverUrlProvider

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
