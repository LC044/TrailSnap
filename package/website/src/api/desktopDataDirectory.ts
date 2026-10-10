import { invoke } from '@tauri-apps/api/core'

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
