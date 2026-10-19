import { ref } from 'vue'
import { defineStore } from 'pinia'
import { getDesktopPortConfig, setDesktopPort, restartForDesktopPort, type DesktopPortConfig } from '@/api/desktopPort'
import { isDesktopDrainPending, waitForDesktopDrain, restartDesktop } from '@/api/desktopDataDirectory'

export const useDesktopPortStore = defineStore('desktopPort', () => {
  const config = ref<DesktopPortConfig | null>(null)
  const fixed = ref(false)
  const port = ref('')
  const loading = ref(false)
  const saving = ref(false)
  const waiting = ref(false)
  const needsRestart = ref(false)
  const error = ref('')

  async function load() {
    loading.value = true
    error.value = ''
    try {
      config.value = await getDesktopPortConfig()
      fixed.value = config.value.fixed
      port.value = String(config.value.port || '')
    } catch (cause) { error.value = String(cause) }
    finally { loading.value = false }
  }

  async function saveAndRestart() {
    if (saving.value) return
    error.value = ''
    const value = Number(port.value)
    if (!needsRestart.value && fixed.value && (!/^\d+$/.test(port.value) || !Number.isInteger(value) || value < 1 || value > 65535)) {
      error.value = '端口必须是 1–65535 的整数'
      return
    }
    saving.value = true
    try {
      if (waiting.value) {
        await waitForDesktopDrain()
        waiting.value = false
        await restartDesktop()
      } else {
        if (!needsRestart.value) {
          await setDesktopPort(fixed.value ? value : null)
          needsRestart.value = true
        }
        await restartForDesktopPort()
      }
    } catch (cause) {
      waiting.value = isDesktopDrainPending(cause)
      error.value = waiting.value ? '正在等待上传和后台任务结束，请继续等待。' : String(cause)
    } finally { saving.value = false }
  }

  return { config, fixed, port, loading, saving, waiting, needsRestart, error, load, saveAndRestart }
})
