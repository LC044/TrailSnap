import { Capacitor, registerPlugin, type PluginListenerHandle } from '@capacitor/core'

export interface NativeAppInfo {
  packageName: string
  versionName: string
  versionCode: number
  /** Android 8+ 是否已授予「安装未知应用」权限 */
  canRequestInstall: boolean
}

export interface ApkDownloadProgress {
  downloaded: number
  total: number
  percent: number
}

interface AppUpdaterNativePlugin {
  getAppInfo(): Promise<NativeAppInfo>
  /** 打开系统「安装未知应用」授权页；返回 granted 表示无需授权 */
  openInstallPermissionSettings(): Promise<{ granted: boolean }>
  downloadApk(options: { url: string; version: string; size: number }): Promise<{ path: string; size: number }>
  cancelDownload(): Promise<void>
  installApk(options: { path: string }): Promise<void>
  clearDownloads(): Promise<void>
  addListener(
    eventName: 'downloadProgress',
    listener: (progress: ApkDownloadProgress) => void,
  ): Promise<PluginListenerHandle>
}

export const appUpdaterNative = registerPlugin<AppUpdaterNativePlugin>('AppUpdater')

/** 只有 Android 原生壳能自下载安装包；iOS 必须走 App Store / TestFlight。 */
export const supportsAppUpdate = () =>
  Capacitor.isNativePlatform() && Capacitor.getPlatform() === 'android'
