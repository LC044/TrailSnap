import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getDesktopDataDirectory, setDesktopDataDirectory, type DesktopDataDirectory } from '@/api/desktopDataDirectory'

export const useDesktopDataDirectoryStore = defineStore('desktop-data-directory', () => {
  const directory = ref<DesktopDataDirectory | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const error = ref('')

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

  return { directory, loading, saving, error, load, save }
})
