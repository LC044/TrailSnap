import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  desktopExtensionRequest, importDesktopAIExtension,
  type ExtensionSnapshot, type ExtensionAction,
} from '@/api/desktopAIExtensions'

export const useDesktopAIExtensionsStore = defineStore('desktopAIExtensions', () => {
  const snapshot = ref<ExtensionSnapshot>({ platform: '', clientVersion: '', operationBusy: false,
    releasePageUrl: 'https://github.com/LC044/TrailSnap/releases', extensions: [], gateway: { running: false } })
  const desktopAvailable = ref(true)
  const checking = ref(false)
  const actionPending = ref(false)
  const checkError = ref<string | null>(null)
  let issued = 0
  let applied = 0
  const busy = computed(() => snapshot.value.operationBusy || actionPending.value)
  const catalogError = computed(() => checkError.value || snapshot.value.catalogError || null)

  function accept(data: ExtensionSnapshot, sequence: number) {
    if (sequence < applied) return
    applied = sequence
    snapshot.value = data
    desktopAvailable.value = true
  }
  async function load() {
    const sequence = ++issued
    try { accept(await desktopExtensionRequest(''), sequence) }
    catch { if (sequence >= applied) desktopAvailable.value = false }
  }
  async function refresh() {
    if (checking.value) return
    checking.value = true
    checkError.value = null
    const sequence = ++issued
    try {
      const data = await desktopExtensionRequest('/refresh', { method: 'POST', body: '{}' })
      // A manual check result supersedes earlier background polls.
      accept(data, Math.max(sequence, ++issued))
    } catch (error) {
      checkError.value = error instanceof Error ? error.message : String(error)
    } finally { checking.value = false }
  }
  async function action(id: string, action: ExtensionAction) {
    if (actionPending.value) return
    actionPending.value = true
    try {
      await desktopExtensionRequest(`/${encodeURIComponent(id)}/${action}`, {
        method: action === 'uninstall' ? 'DELETE' : 'POST', body: '{}',
      })
      await load()
    } finally { actionPending.value = false }
  }
  async function importArchive() {
    if (busy.value) throw new Error('AI 扩展操作进行中，请等待完成')
    actionPending.value = true
    try {
      const result = await importDesktopAIExtension()
      await load()
      return result
    } finally { actionPending.value = false }
  }
  return { snapshot, desktopAvailable, checking, actionPending, busy, catalogError, load, refresh, action, importArchive }
})
