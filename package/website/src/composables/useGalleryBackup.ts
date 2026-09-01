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
  sourcePaths: string[]
  organizeMode: BackupOrganizeMode
}

export type BackupOrganizeMode = 'year_month' | 'flat' | 'preserve'
export type BackupQueueStatus = 'pending' | 'uploading' | 'uploaded' | 'skipped' | 'error'
export interface BackupQueueItem {
  backupKey: string
  name: string
  size: number
  relativePath: string
  status: BackupQueueStatus
}

type BackupStatus = 'idle' | 'scanning' | 'uploading' | 'pausing' | 'paused' | 'error' | 'unsupported'
type PauseReason = 'user' | 'network' | null

const DEFAULT_SETTINGS: GalleryBackupSettings = {
  enabled: false,
  wifiOnly: true,
  includeVideos: false,
  folder: '手机备份',
  sourcePaths: [],
  organizeMode: 'year_month',
}
const EMPTY_CURSOR: GalleryCursor = { imageModified: 0, imageId: 0, videoModified: 0, videoId: 0, companionVideoId: 0 }
const settings = ref<GalleryBackupSettings>({ ...DEFAULT_SETTINGS })
const running = ref(false)
const status = ref<BackupStatus>('idle')
const pauseReason = ref<PauseReason>(null)
const pauseRequested = ref(false)
const currentFile = ref('')
const currentFileProgress = ref(0)
const backedUp = ref(0)
const skipped = ref(0)
const totalItems = ref(0)
const processedItems = ref(0)
const totalBytes = ref(0)
const processedBytes = ref(0)
const uploadedBytes = ref(0)
const speedBytesPerSecond = ref(0)
const lastError = ref('')
const lastRunAt = ref<number | null>(null)
const queueItems = ref<BackupQueueItem[]>([])
const overallProgress = computed(() => {
  if (!totalItems.value) return running.value ? 0 : 100
  const fractionalItem = currentFile.value ? currentFileProgress.value / 100 : 0
  return Math.min(100, Math.round(((processedItems.value + fractionalItem) / totalItems.value) * 100))
})

let initializedKey = ''
let notificationListenerReady = false
let notificationShown = false
let lastNotificationAt = 0
let resumeWaiters: Array<() => void> = []
let speedSamples: Array<{ at: number; bytes: number }> = []

const namespace = () => `${getServerUrl()}|${useUserStore().userInfo?.id || 'anonymous'}`
const storageKey = (name: string) => `trailsnap_gallery_backup_${name}_${encodeURIComponent(namespace())}`

async function readJson<T>(key: string, fallback: T): Promise<T> {
  try {
    const value = (await Preferences.get({ key })).value
    return value ? { ...fallback, ...JSON.parse(value) } : fallback
  } catch {
    return fallback
  }
}

async function applyNotificationAction(action: 'pause' | 'resume' | '') {
  if (!action) return
  await galleryBackupNative.consumeNotificationAction().catch(() => ({ action: '' as const }))
  if (action === 'pause') pauseBackup()
  else resumeBackup()
}

async function initializeNotificationActions() {
  if (notificationListenerReady || !supportsGalleryBackup()) return
  notificationListenerReady = true
  await galleryBackupNative.addListener('notificationAction', ({ action }) => void applyNotificationAction(action))
  const pending = await galleryBackupNative.consumeNotificationAction().catch(() => ({ action: '' as const }))
  await applyNotificationAction(pending.action)
}

async function initialize() {
  const key = namespace()
  if (initializedKey !== key) {
    initializedKey = key
    settings.value = await readJson(storageKey('settings'), { ...DEFAULT_SETTINGS })
    const last = await Preferences.get({ key: storageKey('last_run') })
    lastRunAt.value = last.value ? Number(last.value) : null
  }
  if (!supportsGalleryBackup()) {
    status.value = 'unsupported'
    return
  }
  await initializeNotificationActions()
}

async function saveSettings(next: GalleryBackupSettings) {
  settings.value = {
    ...next,
    folder: next.folder.trim() || DEFAULT_SETTINGS.folder,
    sourcePaths: [...new Set(next.sourcePaths)].sort(),
  }
  await Preferences.set({ key: storageKey('settings'), value: JSON.stringify(settings.value) })
  if (!settings.value.enabled && running.value) pauseBackup()
}

function cursorScopeKey(config: GalleryBackupSettings = settings.value) {
  // v4 also reconciles companions that MediaStore indexed after their still
  // image while preserving an older filesystem modification timestamp.
  const input = JSON.stringify({ version: 4, includeVideos: config.includeVideos, sourcePaths: [...config.sourcePaths].sort() })
  let hash = 2166136261
  for (let index = 0; index < input.length; index++) {
    hash ^= input.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return storageKey(`cursor_${(hash >>> 0).toString(36)}`)
}

async function getCursor(key = cursorScopeKey()) {
  return readJson(key, { ...EMPTY_CURSOR })
}

async function saveCursor(cursor: GalleryCursor, key = cursorScopeKey()) {
  await Preferences.set({ key, value: JSON.stringify(cursor) })
}

function formatSpeed(bytesPerSecond: number) {
  if (bytesPerSecond <= 0) return ''
  if (bytesPerSecond >= 1024 * 1024) return `${(bytesPerSecond / 1024 / 1024).toFixed(1)} MB/s`
  if (bytesPerSecond >= 1024) return `${Math.round(bytesPerSecond / 1024)} KB/s`
  return `${Math.round(bytesPerSecond)} B/s`
}

function recordNetworkBytes(delta: number) {
  if (delta <= 0) return
  uploadedBytes.value += delta
  const now = Date.now()
  speedSamples.push({ at: now, bytes: uploadedBytes.value })
  const cutoff = now - 5000
  while (speedSamples.length > 2 && speedSamples[0].at < cutoff) speedSamples.shift()
  const first = speedSamples[0]
  const elapsed = (now - first.at) / 1000
  if (elapsed >= 0.25) speedBytesPerSecond.value = Math.max(0, (uploadedBytes.value - first.bytes) / elapsed)
  void syncNotification()
}

async function syncNotification(force = false, state?: 'running' | 'paused' | 'completed' | 'error') {
  if (!supportsGalleryBackup()) return
  const now = Date.now()
  if (!force && now - lastNotificationAt < 500) return
  lastNotificationAt = now
  notificationShown = true
  await galleryBackupNative.updateBackupNotification({
    state: state || (pauseRequested.value ? 'paused' : 'running'),
    processed: processedItems.value,
    total: totalItems.value,
    percent: overallProgress.value,
    speed: formatSpeed(speedBytesPerSecond.value),
    currentFile: currentFile.value,
  }).catch(() => undefined)
}

async function waitIfPaused() {
  if (!pauseRequested.value) return
  status.value = 'paused'
  pauseReason.value = 'user'
  speedBytesPerSecond.value = 0
  await syncNotification(true, 'paused')
  await new Promise<void>(resolve => resumeWaiters.push(resolve))
  pauseReason.value = null
  status.value = currentFile.value ? 'uploading' : 'scanning'
  await syncNotification(true, 'running')
}

function pauseBackup() {
  if (pauseRequested.value) return
  pauseRequested.value = true
  pauseReason.value = 'user'
  if (!running.value) {
    status.value = 'paused'
    return
  }
  status.value = status.value === 'uploading' ? 'pausing' : 'paused'
  void syncNotification(true, 'paused')
}

function resumeBackup() {
  if (!running.value) {
    pauseRequested.value = false
    pauseReason.value = null
    void runBackup({ manual: true })
    return
  }
  if (!pauseRequested.value) return
  pauseRequested.value = false
  pauseReason.value = null
  speedBytesPerSecond.value = 0
  speedSamples = [{ at: Date.now(), bytes: uploadedBytes.value }]
  const waiters = resumeWaiters
  resumeWaiters = []
  waiters.forEach(resolve => resolve())
}

async function uploadAsset(asset: GalleryAsset, config: GalleryBackupSettings, replaceExisting: boolean) {
  const exported = await galleryBackupNative.exportAsset({ uri: asset.uri, fileName: asset.name })
  let reportedBytes = 0
  if (!speedSamples.length) speedSamples.push({ at: Date.now(), bytes: uploadedBytes.value })
  const reportAbsolute = (loaded: number) => {
    const bounded = Math.min(asset.size, Math.max(reportedBytes, loaded))
    const delta = bounded - reportedBytes
    reportedBytes = bounded
    currentFileProgress.value = asset.size ? Math.round((bounded / asset.size) * 100) : 100
    recordNetworkBytes(delta)
  }
  try {
    const response = await fetch(Capacitor.convertFileSrc(exported.path))
    if (!response.ok) throw new Error(`读取临时文件失败 (${response.status})`)
    const blob = await response.blob()
    const file = new File([blob], asset.name, { type: asset.mimeType, lastModified: asset.modifiedMs })
    if (file.size > 5 * 1024 * 1024) {
      const uploadId = await albumService.initUpload()
      const chunkSize = 2 * 1024 * 1024
      for (let start = 0, index = 0; start < file.size; start += chunkSize, index++) {
        await waitIfPaused()
        const chunk = file.slice(start, start + chunkSize)
        await albumService.uploadChunk(uploadId, index, chunk, loaded => reportAbsolute(start + Math.min(chunk.size, loaded)))
      }
      await waitIfPaused()
      await albumService.finishUpload(uploadId, file.name, undefined, destinationFolder(asset, config), asset.backupKey, replaceExisting)
    } else {
      await waitIfPaused()
      await albumService.uploadPhoto(
        file, undefined, destinationFolder(asset, config), asset.backupKey,
        loaded => reportAbsolute(Math.min(file.size, loaded)), replaceExisting,
      )
    }
    reportAbsolute(asset.size)
  } finally {
    await galleryBackupNative.releaseAsset({ path: exported.path }).catch(() => undefined)
  }
}

function livePhotoPair(asset: GalleryAsset) {
  const companion = asset.liveCompanion
  if (!companion || companion.kind === asset.kind) return null
  return asset.kind === 'image'
    ? { image: asset, video: companion }
    : { image: companion, video: asset }
}

async function exportedFile(asset: GalleryAsset) {
  const exported = await galleryBackupNative.exportAsset({ uri: asset.uri, fileName: asset.name })
  const response = await fetch(Capacitor.convertFileSrc(exported.path))
  if (!response.ok) {
    await galleryBackupNative.releaseAsset({ path: exported.path }).catch(() => undefined)
    throw new Error(`读取临时文件失败 (${response.status})`)
  }
  const blob = await response.blob()
  return {
    exportedPath: exported.path,
    file: new File([blob], asset.name, { type: asset.mimeType, lastModified: asset.modifiedMs }),
  }
}

async function uploadLivePhoto(image: GalleryAsset, video: GalleryAsset, config: GalleryBackupSettings, replaceExisting: boolean) {
  const imageFile = await exportedFile(image)
  let videoFile: Awaited<ReturnType<typeof exportedFile>> | null = null
  const totalSize = Math.max(0, image.size) + Math.max(0, video.size)
  let reportedBytes = 0
  if (!speedSamples.length) speedSamples.push({ at: Date.now(), bytes: uploadedBytes.value })
  const reportAbsolute = (loaded: number) => {
    const bounded = Math.min(totalSize, Math.max(reportedBytes, loaded))
    recordNetworkBytes(bounded - reportedBytes)
    reportedBytes = bounded
    currentFileProgress.value = totalSize ? Math.round((bounded / totalSize) * 100) : 100
  }
  try {
    videoFile = await exportedFile(video)
    const folder = destinationFolder(image, config)
    if (imageFile.file.size > 5 * 1024 * 1024) {
      const uploadId = await albumService.initUpload()
      const chunkSize = 2 * 1024 * 1024
      for (let start = 0, index = 0; start < imageFile.file.size; start += chunkSize, index++) {
        await waitIfPaused()
        const chunk = imageFile.file.slice(start, start + chunkSize)
        await albumService.uploadChunk(uploadId, index, chunk, loaded => reportAbsolute(start + Math.min(chunk.size, loaded)))
      }
      await waitIfPaused()
      await albumService.finishLivePhotoUpload(
        uploadId, imageFile.file.name, videoFile.file, folder, image.backupKey, video.backupKey,
        replaceExisting,
        loaded => reportAbsolute(imageFile.file.size + loaded),
      )
    } else {
      await waitIfPaused()
      await albumService.uploadLivePhoto(
        imageFile.file, videoFile.file, folder, image.backupKey, video.backupKey,
        replaceExisting,
        loaded => reportAbsolute(loaded),
      )
    }
    reportAbsolute(totalSize)
  } finally {
    await galleryBackupNative.releaseAsset({ path: imageFile.exportedPath }).catch(() => undefined)
    if (videoFile) await galleryBackupNative.releaseAsset({ path: videoFile.exportedPath }).catch(() => undefined)
  }
}

function safePathSegments(path: string) {
  return path.replace(/\\/g, '/').split('/')
    .map(segment => segment.trim().replace(/[<>:"|?*]/g, '_'))
    .filter(segment => segment && segment !== '.' && segment !== '..')
}

function joinFolder(...parts: string[]) {
  return parts.flatMap(safePathSegments).join('/')
}

function destinationFolder(asset: GalleryAsset, config: GalleryBackupSettings) {
  const base = config.folder
  if (config.organizeMode === 'flat') return joinFolder(base)
  if (config.organizeMode === 'preserve') return joinFolder(base, asset.relativePath)
  const date = new Date(asset.takenMs || asset.modifiedMs || Date.now())
  return joinFolder(base, String(date.getFullYear()), String(date.getMonth() + 1).padStart(2, '0'))
}

function updateQueueStatus(backupKey: string, next: BackupQueueStatus) {
  const item = queueItems.value.find(candidate => candidate.backupKey === backupKey)
  if (item) item.status = next
}

function resetRunProgress() {
  backedUp.value = 0
  skipped.value = 0
  totalItems.value = 0
  processedItems.value = 0
  totalBytes.value = 0
  processedBytes.value = 0
  uploadedBytes.value = 0
  speedBytesPerSecond.value = 0
  currentFileProgress.value = 0
  speedSamples = []
  notificationShown = false
  lastNotificationAt = 0
  queueItems.value = []
}

async function runBackup(options: { manual?: boolean } = {}) {
  await initialize()
  if (running.value || !supportsGalleryBackup() || !useUserStore().token) return
  if (!options.manual && !settings.value.enabled) return
  const runSettings: GalleryBackupSettings = { ...settings.value, sourcePaths: [...settings.value.sourcePaths] }
  const runCursorKey = cursorScopeKey(runSettings)
  const startPaused = pauseRequested.value && pauseReason.value === 'user'
  running.value = true
  pauseRequested.value = startPaused
  pauseReason.value = startPaused ? 'user' : null
  resetRunProgress()
  lastError.value = ''
  try {
    const network = await galleryBackupNative.getNetworkStatus()
    if (!network.connected || (runSettings.wifiOnly && !network.unmetered)) {
      pauseReason.value = 'network'
      status.value = 'paused'
      await syncNotification(true, 'paused')
      return
    }
    const permission = await galleryBackupNative.requestGalleryPermission()
    if (!permission.granted) {
      if (!permission.imageGranted) {
        throw new Error('请允许行影集访问照片和视频')
      }
      if (!permission.videoGranted) {
        throw new Error('请允许行影集访问视频，否则无法备份实况照片的动态部分')
      }
      if (!permission.originalGranted) {
        throw new Error('请允许“照片和视频中的位置”权限，否则无法备份包含 GPS 的原图')
      }
      throw new Error('请允许行影集访问照片和视频')
    }
    void galleryBackupNative.requestNotificationPermission().catch(() => undefined)

    status.value = 'scanning'
    const cursor = await getCursor(runCursorKey)
    const sourcePaths = runSettings.sourcePaths
    const totals = await galleryBackupNative.countAssets({ ...cursor, includeVideos: runSettings.includeVideos, sourcePaths })
    totalItems.value = totals.count
    totalBytes.value = totals.bytes
    if (totalItems.value > 0) await syncNotification(true, 'running')
    await waitIfPaused()
    const completedLivePairs = new Set<string>()

    while (true) {
      await waitIfPaused()
      const page = await galleryBackupNative.listAssets({ ...cursor, limit: 40, includeVideos: runSettings.includeVideos, sourcePaths })
      if (!page.assets.length) {
        cursor.imageModified = page.imageModified
        cursor.imageId = page.imageId
        cursor.videoModified = page.videoModified
        cursor.videoId = page.videoId
        cursor.companionVideoId = page.companionVideoId
        await saveCursor(cursor, runCursorKey)
        if (page.hasMore) continue
        break
      }
      if (!runSettings.includeVideos) {
        // A returned video is a late companion for an image that was already
        // scanned, so it was not included in countAssets' image-only total.
        totalItems.value += page.assets.filter(asset => asset.kind === 'video').length
        const companionBytes = new Map<string, number>()
        for (const asset of page.assets) {
          const pair = livePhotoPair(asset)
          if (pair) companionBytes.set(pair.video.backupKey, pair.video.size)
        }
        totalBytes.value += [...companionBytes.values()].reduce((sum, size) => sum + Math.max(0, size), 0)
      }
      const queued = new Map<string, BackupQueueItem>()
      for (const asset of page.assets) {
        const pair = livePhotoPair(asset)
        const key = pair?.image.backupKey || asset.backupKey
        if (!queued.has(key)) queued.set(key, {
          backupKey: key,
          name: pair ? `${pair.image.name} · 实况照片` : asset.name,
          size: pair ? pair.image.size + pair.video.size : asset.size,
          relativePath: pair?.image.relativePath || asset.relativePath,
          status: 'pending',
        })
      }
      queueItems.value = [...queued.values()]
      const keysToCheck = new Set(page.assets.map(asset => asset.backupKey))
      page.assets.forEach(asset => {
        const pair = livePhotoPair(asset)
        if (pair) {
          keysToCheck.add(pair.image.backupKey)
          keysToCheck.add(pair.video.backupKey)
        }
      })
      const existing = await albumService.checkBackupKeys([...keysToCheck])
      for (const asset of page.assets) {
        await waitIfPaused()
        const pair = livePhotoPair(asset)
        const operationKey = pair?.image.backupKey || asset.backupKey
        const replaceExisting = existing.has(operationKey)
        currentFile.value = pair ? `${pair.image.name} · 实况照片` : asset.name
        currentFileProgress.value = 0
        if (pair && completedLivePairs.has(operationKey)) {
          currentFileProgress.value = 100
          updateQueueStatus(operationKey, 'uploaded')
        } else {
          status.value = 'uploading'
          updateQueueStatus(operationKey, 'uploading')
          try {
            if (pair) {
              await uploadLivePhoto(pair.image, pair.video, runSettings, replaceExisting)
              completedLivePairs.add(operationKey)
            } else {
              await uploadAsset(asset, runSettings, replaceExisting)
            }
            updateQueueStatus(operationKey, 'uploaded')
          } catch (error) {
            updateQueueStatus(operationKey, 'error')
            throw error
          }
          backedUp.value++
        }
        processedItems.value++
        processedBytes.value += Math.max(0, asset.size)
        currentFile.value = ''
        currentFileProgress.value = 0
        if (asset.kind === 'image') {
          cursor.imageModified = asset.modifiedMs
          cursor.imageId = asset.id
        }
        await saveCursor(cursor, runCursorKey)
        await syncNotification()
      }
      // Native scanning may consume non-live videos as companion probes without
      // returning them. Persist the page cursors only after every returned asset
      // has completed, so a failed upload is still retried on the next run.
      cursor.imageModified = page.imageModified
      cursor.imageId = page.imageId
      cursor.videoModified = page.videoModified
      cursor.videoId = page.videoId
      cursor.companionVideoId = page.companionVideoId
      await saveCursor(cursor, runCursorKey)
      status.value = 'scanning'
      if (!page.hasMore) break
    }
    lastRunAt.value = Date.now()
    await Preferences.set({ key: storageKey('last_run'), value: String(lastRunAt.value) })
    status.value = 'idle'
    speedBytesPerSecond.value = 0
    if (notificationShown) await syncNotification(true, 'completed')
    else await galleryBackupNative.cancelBackupNotification().catch(() => undefined)
  } catch (error) {
    lastError.value = error instanceof Error ? error.message : String(error)
    status.value = 'error'
    speedBytesPerSecond.value = 0
    if (notificationShown) await syncNotification(true, 'error')
  } finally {
    currentFile.value = ''
    currentFileProgress.value = 0
    running.value = false
    pauseRequested.value = false
    resumeWaiters.splice(0).forEach(resolve => resolve())
  }
}

async function resetCursor() {
  if (running.value) return
  await saveCursor({ ...EMPTY_CURSOR })
  lastRunAt.value = null
}

export function useGalleryBackup() {
  return {
    supported: computed(supportsGalleryBackup), settings, running: readonly(running), status: readonly(status),
    pauseReason: readonly(pauseReason), pauseRequested: readonly(pauseRequested), currentFile: readonly(currentFile),
    currentFileProgress: readonly(currentFileProgress), backedUp: readonly(backedUp), skipped: readonly(skipped),
    totalItems: readonly(totalItems), processedItems: readonly(processedItems), totalBytes: readonly(totalBytes),
    processedBytes: readonly(processedBytes), uploadedBytes: readonly(uploadedBytes),
    speedBytesPerSecond: readonly(speedBytesPerSecond), overallProgress, lastError: readonly(lastError),
    lastRunAt: readonly(lastRunAt), queueItems: readonly(queueItems), initialize, saveSettings, runBackup,
    pauseBackup, resumeBackup, resetCursor,
  }
}
