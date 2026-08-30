import { computed, readonly, ref } from 'vue'
import { Capacitor } from '@capacitor/core'
import { Preferences } from '@capacitor/preferences'
import { albumService } from '@/api/album'
import { getServerUrl } from '@/config/server'
import { useUserStore } from '@/stores/user'
import { galleryBackupNative, supportsGalleryBackup, type GalleryAsset, type GalleryCursor } from '@/native/galleryBackup'

export interface GalleryBackupSettings {
  enabled: boolean
  wifiOnly: boolean
  includeVideos: boolean
  folder: string
}

const DEFAULT_SETTINGS: GalleryBackupSettings = {
  enabled: false,
  wifiOnly: true,
  includeVideos: false,
  folder: '手机备份',
}
const EMPTY_CURSOR: GalleryCursor = { imageModified: 0, imageId: 0, videoModified: 0, videoId: 0 }
const settings = ref<GalleryBackupSettings>({ ...DEFAULT_SETTINGS })
const running = ref(false)
const status = ref<'idle' | 'scanning' | 'uploading' | 'paused' | 'error' | 'unsupported'>('idle')
const currentFile = ref('')
const backedUp = ref(0)
const skipped = ref(0)
const lastError = ref('')
const lastRunAt = ref<number | null>(null)
let initializedKey = ''

const namespace = () => {
  const user = useUserStore().userInfo?.id || 'anonymous'
  return `${getServerUrl()}|${user}`
}
const storageKey = (name: string) => `trailsnap_gallery_backup_${name}_${encodeURIComponent(namespace())}`

async function readJson<T>(key: string, fallback: T): Promise<T> {
  try {
    const value = (await Preferences.get({ key })).value
    return value ? { ...fallback, ...JSON.parse(value) } : fallback
  } catch {
    return fallback
  }
}

async function initialize() {
  const key = namespace()
  if (initializedKey === key) return
  initializedKey = key
  settings.value = await readJson(storageKey('settings'), { ...DEFAULT_SETTINGS })
  const last = await Preferences.get({ key: storageKey('last_run') })
  lastRunAt.value = last.value ? Number(last.value) : null
  if (!supportsGalleryBackup()) status.value = 'unsupported'
}

async function saveSettings(next: GalleryBackupSettings) {
  settings.value = { ...next, folder: next.folder.trim() || DEFAULT_SETTINGS.folder }
  await Preferences.set({ key: storageKey('settings'), value: JSON.stringify(settings.value) })
}

async function getCursor() {
  return readJson(storageKey('cursor'), { ...EMPTY_CURSOR })
}

async function saveCursor(cursor: GalleryCursor) {
  await Preferences.set({ key: storageKey('cursor'), value: JSON.stringify(cursor) })
}

async function uploadAsset(asset: GalleryAsset) {
  const exported = await galleryBackupNative.exportAsset({ uri: asset.uri, fileName: asset.name })
  try {
    const response = await fetch(Capacitor.convertFileSrc(exported.path))
    if (!response.ok) throw new Error(`读取临时文件失败 (${response.status})`)
    const blob = await response.blob()
    const file = new File([blob], asset.name, { type: asset.mimeType, lastModified: asset.modifiedMs })
    if (file.size > 5 * 1024 * 1024) {
      const uploadId = await albumService.initUpload()
      const chunkSize = 2 * 1024 * 1024
      for (let start = 0, index = 0; start < file.size; start += chunkSize, index++) {
        await albumService.uploadChunk(uploadId, index, file.slice(start, start + chunkSize))
      }
      await albumService.finishUpload(uploadId, file.name, undefined, settings.value.folder, asset.backupKey)
    } else {
      await albumService.uploadPhoto(file, undefined, settings.value.folder, asset.backupKey)
    }
  } finally {
    await galleryBackupNative.releaseAsset({ path: exported.path }).catch(() => undefined)
  }
}

async function runBackup(options: { manual?: boolean } = {}) {
  await initialize()
  if (running.value || !supportsGalleryBackup()) return
  if (!useUserStore().token) return
  if (!options.manual && !settings.value.enabled) return
  running.value = true
  backedUp.value = 0
  skipped.value = 0
  lastError.value = ''
  try {
    const network = await galleryBackupNative.getNetworkStatus()
    if (!network.connected || (settings.value.wifiOnly && !network.unmetered)) {
      status.value = 'paused'
      return
    }
    const permission = await galleryBackupNative.requestGalleryPermission()
    if (!permission.granted) throw new Error('请允许行影集访问照片和视频')

    status.value = 'scanning'
    const cursor = await getCursor()
    while (true) {
      const page = await galleryBackupNative.listAssets({
        ...cursor,
        limit: 40,
        includeVideos: settings.value.includeVideos,
      })
      if (!page.assets.length) break
      const existing = await albumService.checkBackupKeys(page.assets.map(asset => asset.backupKey))
      for (const asset of page.assets) {
        currentFile.value = asset.name
        if (existing.has(asset.backupKey)) {
          skipped.value++
        } else {
          status.value = 'uploading'
          await uploadAsset(asset)
          backedUp.value++
        }
        if (asset.kind === 'image') {
          cursor.imageModified = asset.modifiedMs
          cursor.imageId = asset.id
        } else {
          cursor.videoModified = asset.modifiedMs
          cursor.videoId = asset.id
        }
        await saveCursor(cursor)
      }
      status.value = 'scanning'
      if (!page.hasMore) break
    }
    lastRunAt.value = Date.now()
    await Preferences.set({ key: storageKey('last_run'), value: String(lastRunAt.value) })
    status.value = 'idle'
  } catch (error) {
    lastError.value = error instanceof Error ? error.message : String(error)
    status.value = 'error'
  } finally {
    currentFile.value = ''
    running.value = false
  }
}

async function resetCursor() {
  if (running.value) return
  await saveCursor({ ...EMPTY_CURSOR })
  lastRunAt.value = null
}

export function useGalleryBackup() {
  return {
    supported: computed(supportsGalleryBackup),
    settings,
    running: readonly(running),
    status: readonly(status),
    currentFile: readonly(currentFile),
    backedUp: readonly(backedUp),
    skipped: readonly(skipped),
    lastError: readonly(lastError),
    lastRunAt: readonly(lastRunAt),
    initialize,
    saveSettings,
    runBackup,
    resetCursor,
  }
}
