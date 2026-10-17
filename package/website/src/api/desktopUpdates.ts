import { invoke } from '@tauri-apps/api/core'

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
  const { check } = await import('@tauri-apps/plugin-updater')
  return check({ timeout: 30_000 })
}
