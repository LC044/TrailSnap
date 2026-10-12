import { isTauriApp } from '@/config/server'

export interface ExtensionJob {
  id: string
  status: 'downloading' | 'paused' | 'failed' | 'verifying' | 'draining' | 'installing' | 'installed'
  received: number
  total?: number
  progress: number
  error?: string
}
export interface AIExtension {
  id: string
  name: string
  version: string
  description: string
  capabilities: string[]
  requirements: { diskMB?: number; memoryMB?: number }
  available: boolean
  downloadSize?: number
  installed?: { version: string; capabilities: string[] }
  job?: ExtensionJob
  compatibility: 'unknown' | 'compatible' | 'required_update' | 'not_installed'
  compatibilityReason?: string
  updateVersion?: string
  requiredUpdate: boolean
  downloadUrl?: string
  downloadFilename?: string
  releasePageUrl?: string
}
export interface ExtensionSnapshot {
  platform: string
  clientVersion: string
  serverVersion?: string
  minimumAIExtensionVersion?: string
  catalogError?: string
  operationBusy: boolean
  releasePageUrl: string
  extensions: AIExtension[]
  gateway: { running: boolean }
}
export type ExtensionAction = 'install' | 'pause' | 'retry' | 'uninstall'

export async function desktopExtensionRequest<T = ExtensionSnapshot>(path: string, options?: RequestInit): Promise<T> {
  if (isTauriApp()) {
    const { invoke } = await import('@tauri-apps/api/core')
    if (!path) return invoke<T>('ai_extension_list')
    if (path === '/refresh') return invoke<T>('ai_extension_refresh')
    const match = path.match(/^\/([^/]+)\/(install|pause|retry|uninstall)$/)
    if (!match) throw new Error(`未知桌面扩展操作：${path}`)
    return invoke<T>(`ai_extension_${match[2]}`, { id: decodeURIComponent(match[1]) })
  }
  const response = await fetch(`/desktop-api/ai/extensions${path}`, {
    ...options,
    headers: { 'content-type': 'application/json', ...(options?.headers || {}) },
  })
  const data = await response.json()
  if (!response.ok) throw new Error(data.message || data.msg || `HTTP ${response.status}`)
  return data
}

export async function importDesktopAIExtension(): Promise<{ canceled?: boolean }> {
  if (!isTauriApp()) {
    return desktopExtensionRequest('/import', { method: 'POST', body: '{}' })
  }
  const [{ invoke }, { open }] = await Promise.all([
    import('@tauri-apps/api/core'), import('@tauri-apps/plugin-dialog'),
  ])
  const selected = await open({ multiple: false, directory: false,
    filters: [{ name: 'TrailSnap AI 扩展包', extensions: ['gz', 'tgz'] }] })
  if (!selected) return { canceled: true }
  return invoke('ai_extension_import', { path: selected })
}

export const extensionIsBusy = (extension: AIExtension) =>
  ['downloading', 'verifying', 'draining', 'installing'].includes(extension.job?.status || '')
