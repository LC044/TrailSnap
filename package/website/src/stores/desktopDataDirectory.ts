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
    loading.value = true
    error.value = ''
    preview.value = null
    try { preview.value = await previewPortableMigration(sourcePath) }
    catch (cause) { error.value = String(cause) }
    finally { loading.value = false }
  }
  async function convert(path: string, copyExternal: boolean, sourcePath?: string) {
    converting.value = true
    error.value = ''
    try { await convertPortableInstance(path, copyExternal, sourcePath) }
    catch (cause) { error.value = `${String(cause)}。请重新启动后重试，原图库仍保留。`; converting.value = false }
  }
  async function safeExit() {
    converting.value = true
    try { await safeExitDesktop() }
    catch (cause) { error.value = String(cause); converting.value = false }
  }
  return { directory, loading, saving, error, preview, converting, load, save, inspectPortable, convert, safeExit }
})
