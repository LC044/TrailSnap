import { defineStore } from 'pinia'
import { ref } from 'vue'
import { listen, type UnlistenFn } from '@tauri-apps/api/event'
import { getDesktopDataDirectory, isDesktopDrainPending, waitForDesktopDrain, restartDesktop } from '@/api/desktopDataDirectory'
import { applyPortableUpdate, checkPortableUpdate, downloadPortableUpdate, prepareInstalledUpdate, checkInstalledUpdate, getDesktopUpdateStatus, type PortableUpdate } from '@/api/desktopUpdates'

export const useDesktopUpdatesStore = defineStore('desktop-updates', () => {
  const visible = ref(false)
  const version = ref('')
  const phase = ref<'downloading' | 'ready' | 'installing' | 'error'>('downloading')
  const message = ref('正在检查更新…')
  const progress = ref(0)
  const needsRestart = ref(false)
  const waitingForTasks = ref(false)
  let portable = false
  let installedUpdate: Awaited<ReturnType<typeof checkInstalledUpdate>> = null
  let unlisten: UnlistenFn | null = null
  function updateProgress(value: PortableUpdate) {
    progress.value = value.size ? Math.min(100, Math.round(value.downloaded / value.size * 100)) : 0
  }
  async function check(retry = false) {
    phase.value = 'downloading'
    message.value = '正在检查并下载更新…'
    progress.value = 0
    try {
      portable = (await getDesktopDataDirectory()).mode === 'portable'
      if (portable) {
        const status = retry ? null : await getDesktopUpdateStatus()
        const update = await checkPortableUpdate()
        if (status?.transaction?.phase === 'rolled_back'
          && (update.phase === 'current' || update.version === status.transaction.version)) {
          visible.value = true
          version.value = `v${status.transaction.version}`
          phase.value = 'error'
          message.value = `上次更新失败，已恢复升级前的程序与数据。${status.transaction.error || ''} 备份：${status.backupPath || '数据目录/backups'}。可继续使用当前版本，或手动重试。`
          return
        }
        if (!unlisten) unlisten = await listen<PortableUpdate>('desktop-update-status', event => updateProgress(event.payload))
        if (update.phase === 'current') { visible.value = false; return }
        version.value = `v${update.version}`
        visible.value = true
        if (update.phase !== 'ready') await downloadPortableUpdate()
      } else {
        installedUpdate = await checkInstalledUpdate()
        if (!installedUpdate) { visible.value = false; return }
        version.value = `v${installedUpdate.version.replace(/^v/i, '')}`
        visible.value = true
        let downloaded = 0
        let total = 0
        await installedUpdate.download(event => {
          if (event.event === 'Started') total = event.data.contentLength ?? 0
          if (event.event === 'Progress') downloaded += event.data.chunkLength
          progress.value = total ? Math.min(100, Math.round(downloaded / total * 100)) : 0
        })
      }
      progress.value = 100
      phase.value = 'ready'
      message.value = '新版已通过签名校验。更新前会安全结束任务并备份数据库。'
    } catch (error) {
      visible.value = true
      phase.value = 'error'
      message.value = `更新下载失败：${String(error)}`
    }
  }
  async function install() {
    phase.value = 'installing'
    message.value = '正在等待上传和任务结束、备份数据库，请勿拔出磁盘…'
    try {
      if (waitingForTasks.value) await waitForDesktopDrain()
      waitingForTasks.value = false
      if (portable) await applyPortableUpdate()
      else if (installedUpdate) {
        await prepareInstalledUpdate()
        await installedUpdate.install()
        await restartDesktop()
      }
    } catch (error) {
      waitingForTasks.value = isDesktopDrainPending(error)
      needsRestart.value = !waitingForTasks.value
      phase.value = 'error'
      message.value = waitingForTasks.value ? String(error) : `更新失败，请重新启动后重试：${String(error)}`
    }
  }
  function dispose() { unlisten?.(); unlisten = null }
  return { visible, version, phase, message, progress, needsRestart, waitingForTasks, check, install, dispose }
})
