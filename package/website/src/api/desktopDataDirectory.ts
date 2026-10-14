import { invoke } from '@tauri-apps/api/core'
import request from '@/utils/request'

export interface DesktopDataDirectory {
  root: string
  defaultRoot: string
  pendingRoot: string | null
  previousRoot: string | null
  migrationError: string | null
  mode: 'portable' | 'legacy-installed'
  instanceRoot: string | null
  portableSupported: boolean
}

export interface PortablePreview {
  source: string
  bytes: number
  counts: Record<string, number>
  externalRoots: Array<{ ownerId: string; path: string; available: boolean }>
  unregisteredPhotos: number
}

export const getDesktopDataDirectory = () => invoke<DesktopDataDirectory>('desktop_data_directory')
export const setDesktopDataDirectory = (path: string | null) =>
  invoke<void>('desktop_set_data_directory', { path })
export const openDesktopDataDirectory = () => invoke<void>('desktop_open_data_directory')
export const prepareDesktopMigration = () => invoke<void>('desktop_prepare_migration')
export const openDesktopInstanceDirectory = () => invoke<void>('desktop_open_instance_directory')
export const previewPortableMigration = (sourcePath?: string) => invoke<PortablePreview>('desktop_migration_preview', { sourcePath: sourcePath || null })
export const convertPortableInstance = (path: string, copyExternal: boolean, sourcePath?: string) => invoke<void>('desktop_convert_portable', { path, copyExternal, sourcePath: sourcePath || null })
export const safeExitDesktop = () => invoke<void>('desktop_safe_exit')
export const restartDesktop = () => invoke<void>('desktop_restart')
export const revealDesktopPhoto = (path: string) => invoke<void>('desktop_reveal_photo', { path })
export async function getDesktopNetwork() {
  const { data } = await request.get<{ port: number; urls: string[] }>('/api/system/desktop/network')
  return data
}
