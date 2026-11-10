import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { workflowApi, type ToolboxPreferences } from '@/api/toolboxWorkflows'
import { useUserStore } from '@/stores/user'

export const useToolboxStore = defineStore('toolbox', () => {
  const preferences = ref<ToolboxPreferences>({ version: 0, presets: [], default_rename_id: null, recent: [] })
  const loadedOwner = ref('')
  const busy = ref(false)
  const user = useUserStore()
  let loadVersion = 0
  watch(() => user.userInfo?.id, () => {
    loadVersion++
    preferences.value = { version: 0, presets: [], default_rename_id: null, recent: [] }
    loadedOwner.value = ''
  })
  const load = async () => {
    const version = ++loadVersion
    const owner = user.userInfo?.id || ''
    if (!owner) throw new Error('请先登录')
    const value = await workflowApi.preferences()
    if (user.userInfo?.id !== owner || version !== loadVersion) throw new Error('账号或模板请求已变化')
    preferences.value = value
    loadedOwner.value = owner
  }
  const save = async (value: ToolboxPreferences) => {
    if (busy.value) throw new Error('模板正在保存')
    if (loadedOwner.value !== user.userInfo?.id) throw new Error('账号已切换，请重新载入模板')
    busy.value = true
    const owner = loadedOwner.value
    try {
      const saved = await workflowApi.savePreferences(value)
      if (user.userInfo?.id === owner) preferences.value = saved
    }
    finally { busy.value = false }
  }
  return { preferences, loadedOwner, busy, load, save }
})
