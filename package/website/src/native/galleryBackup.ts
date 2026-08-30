import { Capacitor, registerPlugin, type PluginListenerHandle } from '@capacitor/core'

export interface GalleryAsset {
  id: number
  kind: 'image' | 'video'
  name: string
  mimeType: string
  size: number
  modifiedMs: number
  uri: string
  backupKey: string
}

export interface GalleryCursor {
  imageModified: number
  imageId: number
  videoModified: number
  videoId: number
}

interface GalleryBackupNativePlugin {
  requestGalleryPermission(): Promise<{ granted: boolean }>
  listAssets(options: GalleryCursor & { limit: number; includeVideos: boolean }): Promise<GalleryCursor & { assets: GalleryAsset[]; hasMore: boolean }>
  exportAsset(options: { uri: string; fileName: string }): Promise<{ path: string }>
  releaseAsset(options: { path: string }): Promise<void>
  getNetworkStatus(): Promise<{ connected: boolean; wifi: boolean; unmetered: boolean }>
  countAssets(options: GalleryCursor & { includeVideos: boolean }): Promise<{ count: number; bytes: number }>
  requestNotificationPermission(): Promise<{ granted: boolean }>
  updateBackupNotification(options: {
    state: 'running' | 'paused' | 'completed' | 'error'
    processed: number
    total: number
    percent: number
    speed: string
    currentFile: string
  }): Promise<void>
  cancelBackupNotification(): Promise<void>
  consumeNotificationAction(): Promise<{ action: 'pause' | 'resume' | '' }>
  addListener(eventName: 'notificationAction', listener: (event: { action: 'pause' | 'resume' }) => void): Promise<PluginListenerHandle>
}

export const galleryBackupNative = registerPlugin<GalleryBackupNativePlugin>('GalleryBackup')
export const supportsGalleryBackup = () => Capacitor.isNativePlatform() && Capacitor.getPlatform() === 'android'
