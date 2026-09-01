import { computed, readonly, ref } from 'vue'
import { Capacitor } from '@capacitor/core'
import { Preferences } from '@capacitor/preferences'
import { albumService } from '@/api/album'
import { getServerUrl } from '@/config/server'
import { useUserStore } from '@/stores/user'
import { galleryBackupNative, supportsGalleryBackup, type GalleryAsset, type GalleryCursor } from '@/native/galleryBackup'
import {
  adaptTransferTuning,
  backupUploadAction,
  initialTransferTuning,
  takeTransferBatch,
  type TransferTuning,
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
  if (!totalItems.value) return running.value ? 0 : 100
  return Math.min(100, Math.round(((processedItems.value + activeItemProgress.value) / totalItems.value) * 100))
})

let initializedKey = ''
let notificationListenerReady = false
let notificationShown = false
let lastNotificationAt = 0
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
  // v5 rechecks pairs previously rejected because Android MediaStore reported
  // incompatible DATE_TAKEN values for the still image and companion video.
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
    } catch (error) {
      lastError = error
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
) {
  const chunks = Math.ceil(file.size / tuning.chunkSize)
  const loadedByChunk = new Array<number>(chunks).fill(0)
  let nextChunk = 0
  const report = () => reportAbsolute(offset + loadedByChunk.reduce((sum, loaded) => sum + loaded, 0))
  const worker = async () => {
    while (true) {
      const index = nextChunk++
      if (index >= chunks) return
      const start = index * tuning.chunkSize
      const chunk = file.slice(start, Math.min(file.size, start + tuning.chunkSize))
      await waitIfPaused()
      await retryTransfer(
        () => albumService.uploadChunk(uploadId, index, chunk, loaded => {
          loadedByChunk[index] = Math.max(loadedByChunk[index], Math.min(chunk.size, loaded))
          report()
        }),
        config,
      )
      loadedByChunk[index] = chunk.size
      report()
    }
  }
  await Promise.all(Array.from({ length: Math.min(tuning.chunkConcurrency, chunks) }, worker))
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
  if (!speedSamples.length) speedSamples.push({ at: Date.now(), bytes: uploadedBytes.value })
  const reportAbsolute = (loaded: number) => {
    const bounded = Math.min(asset.size, Math.max(reportedBytes, loaded))
    const delta = bounded - reportedBytes
    reportedBytes = bounded
    onProgress(bounded, asset.size)
    recordNetworkBytes(delta)
  }
  try {
    const response = await fetch(Capacitor.convertFileSrc(exported.path))
    if (!response.ok) throw new Error(`读取临时文件失败 (${response.status})`)
    const blob = await response.blob()
    const file = new File([blob], asset.name, { type: asset.mimeType, lastModified: asset.modifiedMs })
    if (file.size > 5 * 1024 * 1024) {
      const uploadId = await retryTransfer(() => albumService.initUpload(), config)
      await uploadChunks(uploadId, file, tuning, config, reportAbsolute)
      await waitIfPaused()
      await retryTransfer(
        () => albumService.finishUpload(uploadId, file.name, undefined, destinationFolder(asset, config), asset.backupKey, replaceExisting),
        config,
      )
    } else {
      await waitIfPaused()
      await retryTransfer(
        () => albumService.uploadPhoto(
          file, undefined, destinationFolder(asset, config), asset.backupKey,
          loaded => reportAbsolute(Math.min(file.size, loaded)), replaceExisting,
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
) {
  const imageFile = await exportedFile(image)
  let videoFile: Awaited<ReturnType<typeof exportedFile>> | null = null
  const totalSize = Math.max(0, image.size) + Math.max(0, video.size)
  let reportedBytes = 0
  if (!speedSamples.length) speedSamples.push({ at: Date.now(), bytes: uploadedBytes.value })
  const reportAbsolute = (loaded: number) => {
    const bounded = Math.min(totalSize, Math.max(reportedBytes, loaded))
    recordNetworkBytes(bounded - reportedBytes)
    reportedBytes = bounded
    onProgress(bounded, totalSize)
  }
  try {
    videoFile = await exportedFile(video)
    const folder = destinationFolder(image, config)
    if (imageFile.file.size > 5 * 1024 * 1024) {
      const uploadId = await retryTransfer(() => albumService.initUpload(), config)
      await uploadChunks(uploadId, imageFile.file, tuning, config, reportAbsolute)
      await waitIfPaused()
      await retryTransfer(
        () => albumService.finishLivePhotoUpload(
          uploadId, imageFile.file.name, videoFile.file, folder, image.backupKey, video.backupKey,
          replaceExisting,
          loaded => reportAbsolute(imageFile.file.size + loaded),
        ),
        config,
      )
    } else {
      await waitIfPaused()
      await retryTransfer(
        () => albumService.uploadLivePhoto(
          imageFile.file, videoFile.file, folder, image.backupKey, video.backupKey,
          replaceExisting,
          loaded => reportAbsolute(loaded),
        ),
        config,
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
  // A transfer error requires an explicit retry. App foreground events must
  // not restart the same failed asset indefinitely in the background.
  if (!options.manual && status.value === 'error') return
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
      const operations = new Map<string, BackupOperation>()
      for (const asset of page.assets) {
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
      queueItems.value = [...operations.values()].map(operation => ({
        backupKey: operation.key,
        name: operation.name,
        size: operation.size,
        relativePath: operation.relativePath,
        status: 'pending',
      }))
      const keysToCheck = new Set(page.assets.map(asset => asset.backupKey))
      page.assets.forEach(asset => {
        const pair = livePhotoPair(asset)
        if (pair) {
          keysToCheck.add(pair.image.backupKey)
          keysToCheck.add(pair.video.backupKey)
        }
      })
      const presence = await albumService.checkBackupKeys([...keysToCheck])
      const remaining: BackupOperation[] = []
      for (const operation of operations.values()) {
        const action = backupUploadAction(operation.key, Boolean(operation.pair), presence)
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
      await syncNotification()
      while (remaining.length) {
        await waitIfPaused()
        const tuning = currentTransferTuning()
        const batch = takeTransferBatch(remaining, tuning)
        remaining.splice(0, batch.length)
        status.value = 'uploading'
        const results = await Promise.allSettled(batch.map(async operation => {
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
                  pair.image, pair.video, runSettings, operation.replaceExisting, tuning, report,
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
        }))
        const failed = results.find((result): result is PromiseRejectedResult => result.status === 'rejected')
        if (failed) {
          if (transferTuning) transferTuning = adaptTransferTuning(transferTuning, speedBytesPerSecond.value, true)
          throw failed.reason
        }
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
