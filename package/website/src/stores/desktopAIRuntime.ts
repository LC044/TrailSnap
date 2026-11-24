import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { listen } from '@tauri-apps/api/event'
import { getAIRuntimeStatus, autoSelectAIRuntime, downloadAIRuntime, selectAIRuntime, type AIBackend, type AIRuntimeStatus, type AIRuntimeProgress } from '@/api/desktopAIRuntime'

export const useDesktopAIRuntimeStore = defineStore('desktop-ai-runtime', () => {
  const status = ref<AIRuntimeStatus | null>(null)
  const progress = ref<AIRuntimeProgress | null>(null)
  const error = ref('')
  const readError = ref('')
  const working = ref(false)
  const busy = computed(() => working.value || !!progress.value && !['ready', 'error'].includes(progress.value.phase))
  let reading: Promise<void> | null = null
  let listener: Promise<() => void> | null = null
  async function refresh() {
    if (reading) return reading
    reading = (async () => {
      try {
        status.value = await getAIRuntimeStatus()
        progress.value = status.value.progress
        readError.value = ''
      } catch (cause) { readError.value = String(cause) }
    })()
    try { await reading } finally { reading = null }
  }
  async function subscribe() {
    listener ??= listen<AIRuntimeProgress>('desktop-ai-runtime-progress', event => { progress.value = event.payload })
    try { await listener } catch (cause) { listener = null; throw cause }
    await refresh()
  }
  async function run(action: () => Promise<void>) {
    if (busy.value) return
    working.value = true
    error.value = ''
    try {
      await action()
    } catch (cause) { error.value = String(cause) }
    finally { working.value = false; await refresh() }
  }
  function act(backend: AIBackend, device: string, download = false) {
    return run(() => download ? downloadAIRuntime(backend) : selectAIRuntime(backend, device))
  }
  const autoSelect = () => run(autoSelectAIRuntime)
  return { status, progress, error, readError, busy, refresh, subscribe, act, autoSelect }
})
