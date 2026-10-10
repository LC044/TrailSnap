import { invoke } from '@tauri-apps/api/core'
import request from '@/utils/request'

export interface DesktopDataDirectory {
  root: string
  defaultRoot: string
  pendingRoot: string | null
  previousRoot: string | null
  migrationError: string | null
}

export const getDesktopDataDirectory = () => invoke<DesktopDataDirectory>('desktop_data_directory')
export const setDesktopDataDirectory = (path: string | null) =>
  invoke<void>('desktop_set_data_directory', { path })
export const openDesktopDataDirectory = () => invoke<void>('desktop_open_data_directory')
export const prepareDesktopMigration = () => invoke<void>('desktop_prepare_migration')
export const revealDesktopPhoto = (path: string) => invoke<void>('desktop_reveal_photo', { path })
export async function getDesktopNetwork() {
  const { data } = await request.get<{ port: number; urls: string[] }>('/api/system/desktop/network')
  return data
}
