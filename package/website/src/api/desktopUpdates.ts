import { Channel, invoke } from '@tauri-apps/api/core'
import type { DownloadEvent } from '@tauri-apps/plugin-updater'

export interface PortableUpdate {
  version: string
  phase: string
  size: number
  downloaded: number
  error: string | null
}
export const checkPortableUpdate = () => invoke<PortableUpdate>('desktop_update_check')
export const downloadPortableUpdate = () => invoke<PortableUpdate>('desktop_update_download')
export const applyPortableUpdate = () => invoke<void>('desktop_update_apply')
export interface DesktopUpdateStatus {
  transaction: { phase: string; version: string; error: string | null } | null
  backupPath: string | null
}
export const getDesktopUpdateStatus = () => invoke<DesktopUpdateStatus>('desktop_update_status')
export const prepareInstalledUpdate = () => invoke<void>('desktop_prepare_update')
export async function checkInstalledUpdate() {
  const version = await invoke<string | null>('desktop_installed_update_check')
  if (!version) return null
  return {
    version,
    async download(onEvent: (event: DownloadEvent) => void) {
      const channel = new Channel<DownloadEvent>()
      channel.onmessage = onEvent
      await invoke<void>('desktop_installed_update_download', { onEvent: channel })
    },
    install: () => invoke<void>('desktop_installed_update_install'),
  }
}
