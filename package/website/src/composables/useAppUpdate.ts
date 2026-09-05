import { ref } from 'vue'
import { Preferences } from '@capacitor/preferences'
import type { PluginListenerHandle } from '@capacitor/core'
import { systemApi, type AppUpdateCheckResult } from '@/api/system'
import { toServerUrl } from '@/config/server'
import {
  appUpdaterNative,
  supportsAppUpdate,
  type ApkDownloadProgress,
  type NativeAppInfo,
} from '@/native/appUpdater'

/**
 * Android App 自更新。
 *
 * 流程：读取原生 versionName → 问服务端 `/api/system/app-update-check`
 * → 下载 APK（进度回抛）→ 唤起系统安装器。
 *
 * 与桌面端 Tauri updater 的差别：Android 无法静默安装，必须由用户在系统
 * 安装界面确认，因此这里不自动开始下载，而是先提示、由用户点「立即更新」。
 */

const SKIPPED_VERSION_KEY = 'trailsnap_app_update_skipped'
const LAST_CHECK_KEY = 'trailsnap_app_update_last_check'
/** 自动检查节流：同一版本每天最多打扰一次。 */
const AUTO_CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000

export type UpdatePhase =
  | 'idle'
  | 'checking'
  | 'available'
  | 'downloading'
  | 'downloaded'
  | 'installing'
  | 'error'

const phase = ref<UpdatePhase>('idle')
const visible = ref(false)
const currentVersion = ref('')
const latestVersion = ref('')
const updateInfo = ref('')
const totalBytes = ref(0)
const downloadedBytes = ref(0)
const percent = ref(0)
const errorMessage = ref('')

let appInfo: NativeAppInfo | null = null
let pendingUrl = ''
let pendingSize = 0
let apkPath = ''
let progressHandle: PluginListenerHandle | null = null

async function readPreference(key: string): Promise<string> {
  try {
    return (await Preferences.get({ key })).value || ''
  } catch {
    return ''
  }
}

async function writePreference(key: string, value: string): Promise<void> {
  try {
    await Preferences.set({ key, value })
  } catch {
    // 存储失败只影响「跳过此版本」的记忆，不阻断更新流程。
  }
}

async function ensureAppInfo(): Promise<NativeAppInfo | null> {
  if (appInfo) return appInfo
  if (!supportsAppUpdate()) return null
  try {
    appInfo = await appUpdaterNative.getAppInfo()
    currentVersion.value = appInfo.versionName
    return appInfo
  } catch {
    return null
  }
}

async function attachProgressListener(): Promise<void> {
  if (progressHandle) return
  progressHandle = await appUpdaterNative.addListener(
    'downloadProgress',
    (progress: ApkDownloadProgress) => {
      downloadedBytes.value = progress.downloaded
      totalBytes.value = progress.total
      percent.value = progress.percent
    },
  )
}

function applyResult(result: AppUpdateCheckResult): boolean {
  latestVersion.value = result.latest_version || ''
  updateInfo.value = result.update_info || ''
  pendingUrl = result.download_url ? toServerUrl(result.download_url) : ''
  pendingSize = result.size || 0
  return result.has_update && !!pendingUrl
}

/**
 * 检查更新。
 * @param silent 自动检查模式：命中节流或用户已跳过该版本时不弹窗。
 */
async function checkForUpdate(silent = false): Promise<boolean> {
  if (!supportsAppUpdate()) return false
  const info = await ensureAppInfo()
  if (!info) return false

  if (silent) {
    const last = Number(await readPreference(LAST_CHECK_KEY)) || 0
    if (Date.now() - last < AUTO_CHECK_INTERVAL_MS) return false
  }

  phase.value = 'checking'
  errorMessage.value = ''
  try {
    const result = await systemApi.checkAppUpdate(info.versionName, 'android')
    if (silent) await writePreference(LAST_CHECK_KEY, String(Date.now()))

    if (result.error) throw new Error(result.error)
    if (!applyResult(result)) {
      phase.value = 'idle'
      visible.value = false
      return false
    }
    if (silent && (await readPreference(SKIPPED_VERSION_KEY)) === latestVersion.value) {
      phase.value = 'idle'
      return false
    }
    phase.value = 'available'
    visible.value = true
    return true
  } catch (error) {
    phase.value = 'error'
    errorMessage.value = error instanceof Error ? error.message : '检查更新失败'
    visible.value = !silent
    return false
  }
}

async function downloadUpdate(): Promise<void> {
  if (!pendingUrl || !latestVersion.value) return
  phase.value = 'downloading'
  errorMessage.value = ''
  downloadedBytes.value = 0
  percent.value = 0
  totalBytes.value = pendingSize
  try {
    await attachProgressListener()
    const result = await appUpdaterNative.downloadApk({
      url: pendingUrl,
      version: latestVersion.value,
      size: pendingSize,
    })
    apkPath = result.path
    percent.value = 100
    phase.value = 'downloaded'
    await installUpdate()
  } catch (error) {
    phase.value = 'error'
    errorMessage.value = error instanceof Error ? error.message : '下载安装包失败'
  }
}

async function installUpdate(): Promise<void> {
  if (!apkPath) return
  phase.value = 'installing'
  try {
    const info = await appUpdaterNative.getAppInfo()
    appInfo = info
    if (!info.canRequestInstall) {
      // 未授权时先把用户送到系统授权页，回来再点一次安装即可。
      await appUpdaterNative.openInstallPermissionSettings()
      phase.value = 'downloaded'
      errorMessage.value = '请先允许 TrailSnap 安装应用，然后重新点击安装'
      return
    }
    await appUpdaterNative.installApk({ path: apkPath })
  } catch (error) {
    phase.value = 'error'
    errorMessage.value = error instanceof Error ? error.message : '唤起安装失败'
  }
}

async function cancelDownload(): Promise<void> {
  try {
    await appUpdaterNative.cancelDownload()
  } catch {
    // 取消失败时下载线程会自然结束，无需额外处理。
  }
  phase.value = 'available'
  percent.value = 0
  downloadedBytes.value = 0
}

async function skipVersion(): Promise<void> {
  if (latestVersion.value) await writePreference(SKIPPED_VERSION_KEY, latestVersion.value)
  dismiss()
}

function dismiss(): void {
  visible.value = false
  if (phase.value !== 'downloading') phase.value = 'idle'
}

export function useAppUpdate() {
  return {
    supported: supportsAppUpdate(),
    phase,
    visible,
    currentVersion,
    latestVersion,
    updateInfo,
    totalBytes,
    downloadedBytes,
    percent,
    errorMessage,
    checkForUpdate,
    downloadUpdate,
    installUpdate,
    cancelDownload,
    skipVersion,
    dismiss,
  }
}
