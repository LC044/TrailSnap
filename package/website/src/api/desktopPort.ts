import { invoke } from '@tauri-apps/api/core'

export interface DesktopPortConfig {
  port: number | null
  fixed: boolean
  activePort: number | null
  error: string | null
  notice: string | null
}

export const getDesktopPortConfig = () => invoke<DesktopPortConfig>('desktop_port_config')
export const setDesktopPort = (port: number | null) => invoke<void>('desktop_set_port', { port })
export const restartForDesktopPort = () => invoke<void>('desktop_restart_for_port')
