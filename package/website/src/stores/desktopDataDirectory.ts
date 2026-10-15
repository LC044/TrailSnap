import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getDesktopDataDirectory, setDesktopDataDirectory, previewPortableMigration, convertPortableInstance, safeExitDesktop, type DesktopDataDirectory, type PortablePreview } from '@/api/desktopDataDirectory'

export const useDesktopDataDirectoryStore = defineStore('desktop-data-directory', () => {
  const directory = ref<DesktopDataDirectory | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const error = ref('')
  const preview = ref<PortablePreview | null>(null)
  const converting = ref(false)
  const inspecting = ref(false)
  const needsRestart = ref(false)
  let inspectedSource: string | null = null
  let previewGeneration = 0

  function clearPreview() {
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
  async function convert(path: string, copyExternal: boolean, sourcePath?: string) {
    if (!preview.value || inspectedSource !== (sourcePath?.trim() || '')) {
      error.value = '请先检查所选图库，确认来源和照片数量后再开始复制。'
      return
    }
    if (!path.trim()) { error.value = '请选择一个新的空文件夹，用于保存导入后的新实例。'; return }
    converting.value = true
    error.value = ''
    try { await convertPortableInstance(path.trim(), copyExternal, preview.value.source) }
    catch (cause) {
      needsRestart.value = true
      error.value = `${String(cause)}。原图库仍保留；若当前服务已停止，请重启当前实例后重试。`
      converting.value = false
    }
  }
  async function safeExit() {
    converting.value = true
    try { await safeExitDesktop() }
    catch (cause) { error.value = String(cause); converting.value = false }
  }
  return { directory, loading, saving, error, preview, converting, inspecting, needsRestart, clearPreview, load, save, inspectPortable, convert, safeExit }
})
