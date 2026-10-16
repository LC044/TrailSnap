import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getDesktopDataDirectory, setDesktopDataDirectory, previewPortableMigration, convertPortableInstance, safeExitDesktop, type DesktopDataDirectory, type PortablePreview, discoverLegacyLibraries, checkImportSpace, resumeDesktopImport, cleanupDesktopImport, type LegacyDiscovery, type ImportSpace, type ImportProgress } from '@/api/desktopDataDirectory'

export const useDesktopDataDirectoryStore = defineStore('desktop-data-directory', () => {
  const directory = ref<DesktopDataDirectory | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const error = ref('')
  const preview = ref<PortablePreview | null>(null)
  const converting = ref(false)
  const inspecting = ref(false)
  const needsRestart = ref(false)
  const discovery = ref<LegacyDiscovery | null>(null)
  const discoveryError = ref('')
  const space = ref<ImportSpace | null>(null)
  const progress = ref<ImportProgress | null>(null)
  const checkingSpace = ref(false)
  let spaceGeneration = 0
  function clearSpace() { spaceGeneration += 1; space.value = null }
  async function loadDiscovery() {
    try { discovery.value = await discoverLegacyLibraries(); discoveryError.value = '' }
    catch (cause) { discoveryError.value = String(cause) }
  }
  async function inspectSpace(target: string, copyExternal: boolean) {
    clearSpace()
    if (!preview.value) return
    const generation = spaceGeneration
    checkingSpace.value = true
    error.value = ''
    try {
      const result = await checkImportSpace(preview.value.source, target, copyExternal)
      if (generation === spaceGeneration) space.value = result
    } catch (cause) { if (generation === spaceGeneration) error.value = String(cause) }
    finally { checkingSpace.value = false }
  }
  async function recover(resume: boolean) {
    converting.value = true
    error.value = ''
    try {
      if (resume) await resumeDesktopImport()
      else { await cleanupDesktopImport(); await loadDiscovery(); converting.value = false }
    } catch (cause) {
      needsRestart.value = resume
      error.value = `${String(cause)}。已保留原图库；请重启当前程序恢复服务。`
      converting.value = false
    }
  }
  let inspectedSource: string | null = null
  let previewGeneration = 0

  function clearPreview() {
    clearSpace()
    previewGeneration += 1
    preview.value = null
    inspectedSource = null
  }

  async function load() {
    loading.value = true
    error.value = ''
    try {
      directory.value = await getDesktopDataDirectory()
    } catch (cause) {
      error.value = String(cause)
    } finally {
      loading.value = false
    }
  }

  async function save(path: string | null) {
    saving.value = true
    error.value = ''
    try {
      await setDesktopDataDirectory(path)
      directory.value = await getDesktopDataDirectory()
      return true
    } catch (cause) {
      error.value = String(cause)
      return false
    } finally {
      saving.value = false
    }
  }

  async function inspectPortable(sourcePath?: string) {
    if (needsRestart.value) { error.value = '请先重启当前程序恢复服务。'; return }
    clearPreview()
    const generation = previewGeneration
    const selectedSource = sourcePath?.trim() || ''
    loading.value = true
    inspecting.value = true
    needsRestart.value = false
    error.value = ''
    try {
      const result = await previewPortableMigration(selectedSource)
      if (generation === previewGeneration) {
        preview.value = result
        inspectedSource = selectedSource
      }
    }
    catch (cause) { if (generation === previewGeneration) error.value = String(cause) }
    finally { loading.value = false; inspecting.value = false }
  }
  async function convert(path: string, copyExternal: boolean, sourcePath?: string, activate?: boolean) {
    if (!preview.value || inspectedSource !== (sourcePath?.trim() || '')) {
      error.value = '请先检查所选图库，确认来源和照片数量后再开始复制。'
      return
    }
    if (!path.trim()) { error.value = '请选择一个新的空文件夹，用于保存导入后的新实例。'; return }
    converting.value = true
    error.value = ''
    progress.value = { stage: 'waiting', completed: 0, total: 0 }
    try {
      if (activate === undefined) await convertPortableInstance(path.trim(), copyExternal, preview.value.source)
      else await convertPortableInstance(path.trim(), copyExternal, preview.value.source, activate)
    }
    catch (cause) {
      needsRestart.value = true
      error.value = `${String(cause)}。原图库仍保留；若当前服务已停止，请重启当前实例后重试。`
      converting.value = false
      await loadDiscovery()
    }
  }
  async function safeExit() {
    converting.value = true
    try { await safeExitDesktop() }
    catch (cause) { needsRestart.value = true; error.value = `安全退出未完成：${String(cause)}。请重启当前程序恢复服务。`; converting.value = false }
  }
  return { discovery, discoveryError, space, progress, checkingSpace, clearSpace, loadDiscovery, inspectSpace, recover, directory, loading, saving, error, preview, converting, inspecting, needsRestart, clearPreview, load, save, inspectPortable, convert, safeExit }
})
