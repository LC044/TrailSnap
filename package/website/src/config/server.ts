import { Capacitor } from '@capacitor/core'
import { Preferences } from '@capacitor/preferences'

const SERVER_URL_KEY = 'trailsnap_server_url'
const LEGACY_STORAGE_KEY = 'trailsnap:server-url'

let configuredServerUrl = ''
let initialized = false

export const isTauriApp = () => '__TAURI_INTERNALS__' in window
export const isNativeApp = () => Capacitor.isNativePlatform() || isTauriApp()

export function normalizeServerUrl(value: string): string {
  let candidate = value.trim()
  if (!candidate) return ''
  if (!/^https?:\/\//i.test(candidate)) candidate = `http://${candidate}`

  const url = new URL(candidate)
  if (!['http:', 'https:'].includes(url.protocol)) {
    throw new Error('服务器地址仅支持 HTTP 或 HTTPS')
  }
  url.hash = ''
  url.search = ''
  url.pathname = url.pathname.replace(/\/(?:api)?\/?$/i, '') || ''
  return url.toString().replace(/\/+$/, '')
}

export async function initializeServerConfig(): Promise<void> {
  if (initialized) return
  if (isTauriApp()) {
    const { invoke } = await import('@tauri-apps/api/core')
    const deadline = Date.now() + 10_000
    while (Date.now() < deadline) {
      const status = await invoke<{ apiUrl: string }>('desktop_runtime_status')
      if (status.apiUrl) {
        configuredServerUrl = normalizeServerUrl(status.apiUrl)
        initialized = true
        return
      }
      await new Promise(resolve => window.setTimeout(resolve, 50))
    }
    throw new Error('Tauri 本地服务未能分配运行端口')
  }
  let saved = ''
  try {
    saved = (await Preferences.get({ key: SERVER_URL_KEY })).value || ''
  } catch {
    // Preferences uses localStorage on web; retain a fallback for upgrades.
  }
  saved ||= localStorage.getItem(LEGACY_STORAGE_KEY) || ''
  if (saved) {
    try {
      configuredServerUrl = normalizeServerUrl(saved)
    } catch {
      configuredServerUrl = ''
    }
  }
  initialized = true
}

export function getServerUrl(): string {
  if (configuredServerUrl) return configuredServerUrl
  return (import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '')
}

export function hasConfiguredServer(): boolean {
  return !!configuredServerUrl
}

export async function saveServerUrl(value: string): Promise<string> {
  const normalized = normalizeServerUrl(value)
  if (!normalized) throw new Error('请输入服务器地址')
  await Preferences.set({ key: SERVER_URL_KEY, value: normalized })
  localStorage.setItem(LEGACY_STORAGE_KEY, normalized)
  configuredServerUrl = normalized
  initialized = true
  return normalized
}

/** Convert web proxy paths (/api/...) into direct backend URLs on native. */
export function toServerUrl(path: string): string {
  if (/^(?:https?:|blob:|data:)/i.test(path)) return path
  const base = getServerUrl()
  if (!base) return path
  const backendPath = path.replace(/^\/api(?=\/|$)/, '')
  return `${base}${backendPath.startsWith('/') ? backendPath : `/${backendPath}`}`
}

export async function testServerConnection(value: string): Promise<string> {
  const normalized = normalizeServerUrl(value)
  if (!normalized) throw new Error('请输入服务器地址')
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 8000)
  try {
    const response = await fetch(`${normalized}/health-check`, {
      method: 'GET',
      signal: controller.signal,
      headers: { Accept: 'application/json' },
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    return normalized
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('连接超时，请检查地址和网络')
    }
    throw new Error(`无法连接 TrailSnap 服务：${error instanceof Error ? error.message : '未知错误'}`)
  } finally {
    window.clearTimeout(timeout)
  }
}
