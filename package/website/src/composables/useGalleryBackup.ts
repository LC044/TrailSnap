import { computed, readonly, ref } from 'vue'
import { Capacitor } from '@capacitor/core'
import { Preferences } from '@capacitor/preferences'
import { albumService } from '@/api/album'
import { transferChunks } from '@/utils/uploadTransfer'
import { getServerUrl } from '@/config/server'
import { useUserStore } from '@/stores/user'
import router from '@/router'
import { galleryBackupNative, supportsGalleryBackup, type GalleryAsset, type GalleryCursor } from '@/native/galleryBackup'
import {
  adaptTransferTuning,
  backupUploadAction,
  initialTransferTuning,
  shouldUseChunkedUpload,
  transferPipeline,
  type TransferTuning,
  type LiveBackupPresence,
} from '@/utils/backupTransfer'

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
type UploadProgress = (loaded: number, total: number) => void
type LivePair = { image: GalleryAsset; video: GalleryAsset }

interface BackupOperation {
  key: string
  name: string
  size: number
  relativePath: string
  asset: GalleryAsset
  pair: LivePair | null
  coveredAssets: GalleryAsset[]
  replaceExisting: boolean
  md5?: string
  livePresence?: LiveBackupPresence
}

interface ActiveUpload {
  name: string
  size: number
  loaded: number
  itemWeight: number
}

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
const failedItems = ref(0)
const totalItems = ref(0)
const processedItems = ref(0)
const totalBytes = ref(0)
const processedBytes = ref(0)
const uploadedBytes = ref(0)
const speedBytesPerSecond = ref(0)
const activeItemProgress = ref(0)
const lastError = ref('')
const lastRunAt = ref<number | null>(null)
const queueItems = ref<BackupQueueItem[]>([])
const overallProgress = computed(() => {
  if (status.value === 'idle') return 100
  if (!totalItems.value) return running.value ? 0 : 100
  const progress = Math.round(((processedItems.value + activeItemProgress.value) / totalItems.value) * 100)
  return running.value ? Math.min(99, progress) : Math.min(100, progress)
})

let initializedKey = ''
let notificationListenerReady = false
let notificationShown = false
let lastNotificationAt = 0
let notificationUpdate: Promise<void> = Promise.resolve()
let resumeWaiters: Array<() => void> = []
let speedSamples: Array<{ at: number; bytes: number }> = []
let transferTuning: TransferTuning | null = null
const activeUploads = new Map<string, ActiveUpload>()

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

async function applyNotificationAction(action: 'pause' | 'resume' | 'open' | '') {
  if (!action) return
  await galleryBackupNative.consumeNotificationAction().catch(() => ({ action: '' as const }))
  if (action === 'open') {
    await router.push({ path: '/settings', hash: '#mobile-backup' })
  } else if (action === 'pause') pauseBackup()
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
  // Keep the v5 scope stable so upgrading does not force a full-library rescan.
  // Fresh v5 cursors receive the corrected native companion-video baseline.
  const input = JSON.stringify({ version: 5, includeVideos: config.includeVideos, sourcePaths: [...config.sourcePaths].sort() })
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
  const payload = {
    state: state || (pauseRequested.value ? 'paused' : 'running'),
    processed: processedItems.value,
    total: totalItems.value,
    percent: overallProgress.value,
    speed: formatSpeed(speedBytesPerSecond.value),
    currentFile: currentFile.value,
  } as const
  notificationUpdate = notificationUpdate.then(() => galleryBackupNative.updateBackupNotification(payload)).catch(() => undefined)
  await notificationUpdate
}

async function waitIfPaused() {
  if (!pauseRequested.value) return
  status.value = 'paused'
  pauseReason.value = 'user'
  speedBytesPerSecond.value = 0
  // Register before notifying: resume can arrive while the native call is pending.
  const resumed = new Promise<void>(resolve => resumeWaiters.push(resolve))
  await syncNotification(true, 'paused')
  await resumed
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

function refreshActiveProgress() {
  const uploads = [...activeUploads.values()]
  if (!uploads.length) {
    currentFile.value = ''
    currentFileProgress.value = 0
    activeItemProgress.value = 0
    return
  }
  currentFile.value = uploads.length === 1 ? uploads[0].name : `并行上传 ${uploads.length} 项`
  const total = uploads.reduce((sum, upload) => sum + Math.max(0, upload.size), 0)
  const loaded = uploads.reduce((sum, upload) => sum + Math.min(upload.size, Math.max(0, upload.loaded)), 0)
  currentFileProgress.value = total ? Math.round((loaded / total) * 100) : 100
  activeItemProgress.value = uploads.reduce((sum, upload) => {
    const fraction = upload.size ? Math.min(1, Math.max(0, upload.loaded) / upload.size) : 1
    return sum + fraction * upload.itemWeight
  }, 0)
}

function beginActiveUpload(operation: BackupOperation) {
  activeUploads.set(operation.key, {
    name: operation.name,
    size: operation.size,
    loaded: 0,
    itemWeight: operation.coveredAssets.length,
  })
  refreshActiveProgress()
}

function updateActiveUpload(key: string, loaded: number) {
  const upload = activeUploads.get(key)
  if (!upload) return
  upload.loaded = Math.max(upload.loaded, Math.min(upload.size, loaded))
  refreshActiveProgress()
}

function endActiveUpload(key: string) {
  activeUploads.delete(key)
  refreshActiveProgress()
}

function currentTransferTuning() {
  if (!transferTuning) throw new Error('上传并发参数尚未初始化')
  transferTuning = adaptTransferTuning(transferTuning, speedBytesPerSecond.value)
  return transferTuning
}

function waitForRetry(delayMs: number) {
  return new Promise<void>(resolve => window.setTimeout(resolve, delayMs))
}

async function retryTransfer<T>(action: () => Promise<T>, config: GalleryBackupSettings): Promise<T> {
  const attempts = transferTuning?.maxAttempts || 2
  let lastError: unknown
  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      return await action()
    } catch (error: any) {
      lastError = error
      if (error.response?.status && ![408, 429, 500, 502, 503, 504].includes(error.response.status)) throw error
      if (transferTuning) transferTuning = adaptTransferTuning(transferTuning, speedBytesPerSecond.value, true)
      if (attempt >= attempts) break
      const network = await galleryBackupNative.getNetworkStatus().catch(() => ({ connected: true, wifi: false, unmetered: false }))
      if (!network.connected) throw new Error('网络连接已断开，备份将在下次运行时继续')
      if (config.wifiOnly && !network.unmetered) throw new Error('当前已离开 Wi-Fi / 不计费网络，备份已停止')
      await waitForRetry(attempt === 1 ? 1000 : 3000)
      await waitIfPaused()
    }
  }
  throw lastError
}

async function uploadChunks(
  uploadId: string,
  file: File,
  tuning: TransferTuning,
  config: GalleryBackupSettings,
  reportAbsolute: (loaded: number) => void,
  offset = 0,
  completed: ReadonlySet<number> = new Set(),
) {
  return await transferChunks(file, tuning.chunkSize, tuning.chunkConcurrency,
    async (index, chunk, report) => {
      await waitIfPaused()
      if (completed.has(index)) { report(chunk.size); return }
      await retryTransfer(
        () => albumService.uploadChunk(uploadId, index, chunk, report),
        config,
      )
    }, loaded => reportAbsolute(offset + loaded))
}

async function uploadAsset(
  asset: GalleryAsset,
  config: GalleryBackupSettings,
  replaceExisting: boolean,
  tuning: TransferTuning,
  onProgress: UploadProgress,
) {
  const exported = await galleryBackupNative.exportAsset({ uri: asset.uri, fileName: asset.name })
  let reportedBytes = 0
  let resumedBytes = 0
  let reportedNetworkBytes = 0
  if (!speedSamples.length) speedSamples.push({ at: Date.now(), bytes: uploadedBytes.value })
  const reportAbsolute = (loaded: number) => {
    const bounded = Math.min(asset.size, Math.max(reportedBytes, loaded))
    reportedBytes = bounded
    onProgress(bounded, asset.size)
    const networkBytes = Math.max(0, bounded - resumedBytes)
    recordNetworkBytes(networkBytes - reportedNetworkBytes)
    reportedNetworkBytes = Math.max(reportedNetworkBytes, networkBytes)
  }
  try {
    const response = await fetch(Capacitor.convertFileSrc(exported.path))
    if (!response.ok) throw new Error(`读取临时文件失败 (${response.status})`)
    const blob = await response.blob()
    const file = new File([blob], asset.name, { type: asset.mimeType, lastModified: asset.modifiedMs })
    if (shouldUseChunkedUpload(file.size, tuning)) {
      const sessionKey = storageKey(`upload_${asset.backupKey}`)
      const saved = await readJson<{ id: string; size: number; md5?: string; chunkSize: number } | null>(sessionKey, null)
      let uploadId: string | undefined
      const completed = new Set<number>()
      const chunkSize = saved && saved.size === file.size && saved.md5 === asset.contentMd5 ? saved.chunkSize : tuning.chunkSize
      if (saved && saved.size === file.size && saved.md5 === asset.contentMd5) {
        try {
          const result = await albumService.getUploadStatus(saved.id)
          uploadId = saved.id
          for (const [index, size] of Object.entries(result.chunks)) {
            const value = Number(index)
            if (size === Math.min(chunkSize, file.size - value * chunkSize)) completed.add(value)
          }
        } catch (error: any) {
          if (error.response?.status !== 404) throw error
        }
      }
      if (!uploadId) {
        if (saved) await albumService.discardUpload(saved.id).catch(() => undefined)
        uploadId = await retryTransfer(() => albumService.initUpload(), config)
        await Preferences.set({ key: sessionKey, value: JSON.stringify({ id: uploadId, size: file.size, md5: asset.contentMd5, chunkSize }) })
      }
      resumedBytes = [...completed].reduce((sum, index) => sum + Math.min(chunkSize, file.size - index * chunkSize), 0)
      const chunks = await uploadChunks(uploadId, file, { ...tuning, chunkSize }, config, reportAbsolute, 0, completed)
      await waitIfPaused()
      await retryTransfer(
        () => albumService.finishUpload(
          uploadId, file.name, undefined, destinationFolder(asset, config), asset.backupKey,
          replaceExisting, sourcePhotoTime(asset), asset.contentMd5,
          { expectedSize: file.size, expectedChunks: chunks },
        ),
        config,
      )
      await Preferences.remove({ key: sessionKey })
    } else {
      await waitIfPaused()
      await retryTransfer(
        () => albumService.uploadPhoto(
          file, undefined, destinationFolder(asset, config), asset.backupKey,
          loaded => reportAbsolute(Math.min(file.size, loaded)), replaceExisting,
          sourcePhotoTime(asset), asset.contentMd5,
        ),
        config,
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

async function uploadLivePhoto(
  image: GalleryAsset,
  video: GalleryAsset,
  config: GalleryBackupSettings,
  replaceExisting: boolean,
  tuning: TransferTuning,
  onProgress: UploadProgress,
  presence: LiveBackupPresence,
) {
  let imageFile: Awaited<ReturnType<typeof exportedFile>> | null = null
  let videoFile: Awaited<ReturnType<typeof exportedFile>> | null = null
  const totalSize = (presence.image_exists ? 0 : Math.max(0, image.size))
    + (presence.video_exists ? 0 : Math.max(0, video.size))
  let reportedBytes = 0
  if (!speedSamples.length) speedSamples.push({ at: Date.now(), bytes: uploadedBytes.value })
  const reportAbsolute = (loaded: number) => {
    const bounded = Math.min(totalSize, Math.max(reportedBytes, loaded))
    recordNetworkBytes(bounded - reportedBytes)
    reportedBytes = bounded
    onProgress(bounded, totalSize)
  }
  try {
    let imageBytes = 0
    if (!presence.image_exists) {
      if (shouldUseChunkedUpload(image.size, tuning)) {
        // Preserve chunked transfer for large still images, then attach the
        // video with a metadata-only image reference.
        await uploadAsset(image, config, replaceExisting, tuning, (loaded) => {
          imageBytes = loaded
          reportedBytes = loaded
          onProgress(loaded, totalSize)
        })
      } else {
        imageFile = await exportedFile(image)
      }
    }
    if (!presence.video_exists) videoFile = await exportedFile(video)
    const form = new FormData()
    form.append('image_md5', image.contentMd5!)
    form.append('video_md5', video.contentMd5!)
    form.append('video_name', video.name)
    form.append('backup_key', image.backupKey)
    form.append('companion_backup_key', video.backupKey)
    form.append('folder', destinationFolder(image, config))
    const photoTime = sourcePhotoTime(image)
    if (photoTime) form.append('source_photo_time', photoTime)
    if (imageFile) form.append('image', imageFile.file)
    if (videoFile) form.append('video', videoFile.file)
    await waitIfPaused()
    const saved = await retryTransfer(
      () => albumService.uploadMissingLiveContent(form, loaded => reportAbsolute(imageBytes + loaded)), config,
    )
    if (saved.file_type !== 'live_photo') throw new Error('服务端未保存实况照片的视频部分')
    reportAbsolute(totalSize)
  } finally {
    if (imageFile) await galleryBackupNative.releaseAsset({ path: imageFile.exportedPath }).catch(() => undefined)
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

function sourcePhotoTime(asset: GalleryAsset) {
  if (!asset.takenMs) return undefined
  const date = new Date(asset.takenMs)
  if (Number.isNaN(date.getTime())) return undefined
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

function updateQueueStatus(backupKey: string, next: BackupQueueStatus) {
  const item = queueItems.value.find(candidate => candidate.backupKey === backupKey)
  if (item) item.status = next
}

function resetRunProgress() {
  backedUp.value = 0
  skipped.value = 0
  failedItems.value = 0
  totalItems.value = 0
  processedItems.value = 0
  totalBytes.value = 0
  processedBytes.value = 0
  uploadedBytes.value = 0
  speedBytesPerSecond.value = 0
  activeItemProgress.value = 0
  currentFileProgress.value = 0
  speedSamples = []
  activeUploads.clear()
  transferTuning = null
  notificationShown = false
  lastNotificationAt = 0
  queueItems.value = []
}

async function runBackup(options: { manual?: boolean } = {}) {
  await initialize()
  if (running.value || !supportsGalleryBackup() || !useUserStore().token) return
  if (!options.manual && !settings.value.enabled) return
  if (!options.manual && status.value === 'error') return
  const speedTimer = setInterval(() => {
    const now = Date.now()
    const first = speedSamples.find(sample => sample.at >= now - 5000)
    speedBytesPerSecond.value = first && activeUploads.size && now > first.at
      ? Math.max(0, (uploadedBytes.value - first.bytes) / ((now - first.at) / 1000)) : 0
  }, 1000)
  // A transfer error requires an explicit retry. App foreground events must
  // not restart the same failed asset indefinitely in the background.
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
    transferTuning = initialTransferTuning(getServerUrl(), network)
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
    const seenAssetKeys = new Set<string>()
    const seenContentHashes = new Set<string>()
    let checkpointBlocked = false
    const failures: string[] = []

    while (true) {
      await waitIfPaused()
      const page = await galleryBackupNative.listAssets({ ...cursor, limit: 40, includeVideos: runSettings.includeVideos, sourcePaths })
      if (page.hasMore && (Object.keys(EMPTY_CURSOR) as Array<keyof GalleryCursor>)
        .every(key => page[key] === cursor[key])) {
        throw new Error('图库扫描未能进入下一批，请重试备份或更新 App')
      }
      if (!page.assets.length) {
        cursor.imageModified = page.imageModified
        cursor.imageId = page.imageId
        cursor.videoModified = page.videoModified
        cursor.videoId = page.videoId
        cursor.companionVideoId = page.companionVideoId
        if (!checkpointBlocked) await saveCursor(cursor, runCursorKey)
        if (page.hasMore) continue
        break
      }
      const freshAssets = page.assets.filter(asset => {
        if (seenAssetKeys.has(asset.backupKey)) return false
        seenAssetKeys.add(asset.backupKey)
        return true
      })
      if (!freshAssets.length) {
        cursor.imageModified = page.imageModified
        cursor.imageId = page.imageId
        cursor.videoModified = page.videoModified
        cursor.videoId = page.videoId
        cursor.companionVideoId = page.companionVideoId
        if (!checkpointBlocked) await saveCursor(cursor, runCursorKey)
        if (page.hasMore) continue
        break
      }
      if (!runSettings.includeVideos) {
        // A returned video is a late companion for an image that was already
        // scanned, so it was not included in countAssets' image-only total.
        totalItems.value += freshAssets.filter(asset => asset.kind === 'video').length
        const companionBytes = new Map<string, number>()
        for (const asset of freshAssets) {
          const pair = livePhotoPair(asset)
          if (pair) companionBytes.set(pair.video.backupKey, pair.video.size)
        }
        totalBytes.value += [...companionBytes.values()].reduce((sum, size) => sum + Math.max(0, size), 0)
      }
      // Late live-photo companions and media added during this run can exceed
      // the initial MediaStore count. Keep the denominator aligned with work.
      totalItems.value = Math.max(totalItems.value, processedItems.value + freshAssets.length)
      const operations = new Map<string, BackupOperation>()
      for (const asset of freshAssets) {
        const pair = livePhotoPair(asset)
        const key = pair?.image.backupKey || asset.backupKey
        const existingOperation = operations.get(key)
        if (existingOperation) {
          if (!existingOperation.coveredAssets.some(candidate => candidate.backupKey === asset.backupKey)) {
            existingOperation.coveredAssets.push(asset)
          }
          continue
        }
        operations.set(key, {
          key,
          name: pair ? `${pair.image.name} · 实况照片` : asset.name,
          size: pair ? pair.image.size + pair.video.size : asset.size,
          relativePath: pair?.image.relativePath || asset.relativePath,
          asset,
          pair,
          coveredAssets: [asset],
          replaceExisting: false,
        })
      }
      queueItems.value = [...queueItems.value.filter(item => item.status === 'error'), ...[...operations.values()].map(operation => ({
        backupKey: operation.key,
        name: operation.name,
        size: operation.size,
        relativePath: operation.relativePath,
        status: 'pending' as const,
      }))]
      const keysToCheck = new Set(freshAssets.map(asset => asset.backupKey))
      freshAssets.forEach(asset => {
        const pair = livePhotoPair(asset)
        if (pair) {
          keysToCheck.add(pair.image.backupKey)
          keysToCheck.add(pair.video.backupKey)
        }
      })
      const sourceTimes = Object.fromEntries(freshAssets.flatMap(asset => {
        const values: Array<[string, string]> = []
        const ownTime = sourcePhotoTime(asset)
        if (ownTime) values.push([asset.backupKey, ownTime])
        const pair = livePhotoPair(asset)
        const imageTime = pair ? sourcePhotoTime(pair.image) : undefined
        if (pair && imageTime) values.push([pair.image.backupKey, imageTime])
        return values
      }))
      const presence = await albumService.checkBackupKeys([...keysToCheck], [], sourceTimes)
      const remaining: BackupOperation[] = []
      for (const operation of operations.values()) {
        // A live clip can change independently of its image. Check both hashes
        // even if this image's stable key already has some companion on server.
        const action = operation.pair
          ? (presence.existing.has(operation.key) && !presence.complete.has(operation.key) ? 'replace' : 'upload')
          : backupUploadAction(operation.key, false, presence)
        operation.replaceExisting = action === 'replace'
        if (action === 'skip') {
          updateQueueStatus(operation.key, 'skipped')
          skipped.value++
          processedItems.value += operation.coveredAssets.length
          processedBytes.value += operation.coveredAssets.reduce((sum, asset) => sum + Math.max(0, asset.size), 0)
          if (operation.pair) completedLivePairs.add(operation.key)
        } else {
          remaining.push(operation)
        }
      }
      // Stable MediaStore ids are the fast path. For assets not known by id,
      // hash the original bytes locally and ask the server before transferring
      // them. This also catches the same file appearing in multiple phone
      // folders or under a changed MediaStore id.
      const failOperation = (operation: BackupOperation, error: unknown) => {
        checkpointBlocked = true
        failedItems.value++
        updateQueueStatus(operation.key, 'error')
        failures.push(`${operation.name}: ${error instanceof Error ? error.message : String(error)}`)
      }
      const skipOperation = (operation: BackupOperation) => {
        updateQueueStatus(operation.key, 'skipped')
        skipped.value++
        processedItems.value += operation.coveredAssets.length
        processedBytes.value += operation.coveredAssets.reduce((sum, asset) => sum + Math.max(0, asset.size), 0)
      }
      // Preparation workers feed the bounded transfer queue immediately. A slow
      // hash or large video no longer holds every other file in the page.
      await transferPipeline(remaining, transferTuning?.hashConcurrency || 1, currentTransferTuning,
        async operation => {
          try {
            await waitIfPaused()
            const primary = operation.pair?.image || operation.asset
            const digest = await galleryBackupNative.calculateAssetMd5({ uri: primary.uri })
            operation.md5 = primary.contentMd5 = digest.md5.toLowerCase()
            if (operation.pair) {
              const videoDigest = await galleryBackupNative.calculateAssetMd5({ uri: operation.pair.video.uri })
              operation.pair.video.contentMd5 = videoDigest.md5.toLowerCase()
              const presence = await albumService.checkLiveBackupContent([{
                key: operation.key, image_md5: operation.md5!, video_md5: operation.pair.video.contentMd5!,
              }])
              operation.livePresence = presence[operation.key]
              if (!operation.livePresence) throw new Error('服务端未返回实况照片去重结果，请更新服务端')
              operation.size = (operation.livePresence.image_exists ? 0 : operation.pair.image.size)
                + (operation.livePresence.video_exists ? 0 : operation.pair.video.size)
              if (operation.livePresence.complete) { skipOperation(operation); return null }
            } else {
              const presence = await albumService.checkBackupKeys([], [operation.md5!])
              if (presence.hashes.has(operation.md5!) || seenContentHashes.has(operation.md5!)) {
                skipOperation(operation); return null
              }
            }
            if (operation.md5) seenContentHashes.add(operation.md5)
            return operation
          } catch (error) { failOperation(operation, error); return null }
        },
        async operation => {
          await waitIfPaused()
          const tuning = currentTransferTuning()
          status.value = 'uploading'
          try {
          const { key, pair, coveredAssets } = operation
          if (pair && completedLivePairs.has(key)) {
            updateQueueStatus(key, 'uploaded')
          } else {
            updateQueueStatus(key, 'uploading')
            beginActiveUpload(operation)
            const report: UploadProgress = loaded => updateActiveUpload(key, loaded)
            try {
              if (pair) {
                await uploadLivePhoto(
                  pair.image, pair.video, runSettings, operation.replaceExisting, tuning, report, operation.livePresence!,
                )
                completedLivePairs.add(key)
              } else {
                await uploadAsset(operation.asset, runSettings, operation.replaceExisting, tuning, report)
              }
              updateQueueStatus(key, 'uploaded')
              backedUp.value++
            } catch (error) {
              // The server may have committed the file before the response was
              // interrupted. Confirm the durable state before declaring failure.
              let confirmed = false
              try {
                const confirmedPresence = await albumService.checkBackupKeys(
                  pair ? [pair.image.backupKey, pair.video.backupKey] : [operation.asset.backupKey],
                )
                confirmed = backupUploadAction(key, Boolean(pair), confirmedPresence) === 'skip'
              } catch {
                // Preserve the original upload error when confirmation is unavailable.
              }
              if (!confirmed) {
                updateQueueStatus(key, 'error')
                throw error
              }
              if (pair) completedLivePairs.add(key)
              updateQueueStatus(key, 'uploaded')
              backedUp.value++
            } finally {
              endActiveUpload(key)
            }
          }
          processedItems.value += coveredAssets.length
          processedBytes.value += coveredAssets.reduce((sum, asset) => sum + Math.max(0, asset.size), 0)
          await syncNotification()

          } catch (error) { failOperation(operation, error) }
        })
      // Native scanning may consume non-live videos as companion probes without
      // returning them. Persist the page cursors only after every returned asset
      // has completed, so a failed upload is still retried on the next run.
      cursor.imageModified = page.imageModified
      cursor.imageId = page.imageId
      cursor.videoModified = page.videoModified
      cursor.videoId = page.videoId
      cursor.companionVideoId = page.companionVideoId
      if (!checkpointBlocked) await saveCursor(cursor, runCursorKey)
      status.value = 'scanning'
      if (!page.hasMore) break
    }
    if (failures.length) throw new Error(`${failures.length} 个文件未备份，其余文件已继续处理。${failures.slice(0, 3).join('；')}`)
    lastRunAt.value = Date.now()
    await Preferences.set({ key: storageKey('last_run'), value: String(lastRunAt.value) })
    status.value = 'idle'
    speedBytesPerSecond.value = 0
    await notificationUpdate
    await galleryBackupNative.cancelBackupNotification().catch(() => undefined)
    notificationShown = false
  } catch (error) {
    lastError.value = error instanceof Error ? error.message : String(error)
    status.value = 'error'
    speedBytesPerSecond.value = 0
    if (notificationShown) await syncNotification(true, 'error')
  } finally {
    clearInterval(speedTimer)
    currentFile.value = ''
    currentFileProgress.value = 0
    running.value = false
    pauseRequested.value = false
    resumeWaiters.splice(0).forEach(resolve => resolve())
  }
}

async function resetCursor() {
  if (running.value) throw new Error('备份仍在运行，请等待本轮完成后再重置增量记录')
  await saveCursor({ ...EMPTY_CURSOR })
  lastRunAt.value = null
  pauseRequested.value = false
  pauseReason.value = null
  lastError.value = ''
  status.value = 'idle'
  resetRunProgress()
}

export function useGalleryBackup() {
  return {
    supported: computed(supportsGalleryBackup), settings, running: readonly(running), status: readonly(status),
    pauseReason: readonly(pauseReason), pauseRequested: readonly(pauseRequested), currentFile: readonly(currentFile),
    currentFileProgress: readonly(currentFileProgress), failedItems: readonly(failedItems), backedUp: readonly(backedUp), skipped: readonly(skipped),
    totalItems: readonly(totalItems), processedItems: readonly(processedItems), totalBytes: readonly(totalBytes),
    processedBytes: readonly(processedBytes), uploadedBytes: readonly(uploadedBytes),
    speedBytesPerSecond: readonly(speedBytesPerSecond), overallProgress, lastError: readonly(lastError),
    lastRunAt: readonly(lastRunAt), queueItems: readonly(queueItems), initialize, saveSettings, runBackup,
    pauseBackup, resumeBackup, resetCursor,
  }
}
