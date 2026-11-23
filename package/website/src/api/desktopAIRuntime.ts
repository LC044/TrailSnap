import { invoke } from '@tauri-apps/api/core'

export type AIBackend = 'cpu' | 'cuda' | 'openvino'
export interface AIRuntimeProgress {
  backend: AIBackend
  phase: 'detecting' | 'checking' | 'downloading' | 'verifying' | 'installing' | 'switching' | 'ready' | 'error'
  downloaded: number
  size: number
  error: string | null
}
export interface AIRuntimeStatus {
  selected: AIBackend
  device: string
  error: string | null
  supported: boolean
  version: string
  packages: { backend: AIBackend; installed: boolean }[]
  progress: AIRuntimeProgress | null
  runtime: {
    backend: AIBackend | null
    deviceName: string
    error?: string | null
    devices?: { id: string; name: string }[]
    models?: Record<string, { providers: string[]; error: string | null }>
  }
}
export const getAIRuntimeStatus = () => invoke<AIRuntimeStatus>('desktop_ai_runtime_status')
export const downloadAIRuntime = (backend: AIBackend) => invoke<void>('desktop_ai_runtime_download', { backend })
export const autoSelectAIRuntime = () => invoke<void>('desktop_ai_runtime_auto')
export const selectAIRuntime = (backend: AIBackend, device: string) => invoke<void>('desktop_ai_runtime_select', { backend, device })
