import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * 全局 UI 状态。
 *
 * selectionActive：是否有任意画廊进入「选择模式」。
 * 由 useSelection() 组合式与 RecycleBinPage 等选择宿主同步；
 * 移动端底部 Tab 栏（BottomNav）与 Agent 悬浮按钮在选择模式激活时隐藏，
 * 避免与各画廊底部的批量操作条（fixed bottom-[20px] z-40）重叠。
 * BottomNav 在路由切换时复位，防止跨页残留。
 */
export const useUiStore = defineStore('ui', () => {
  const selectionActive = ref(false)
  const agentOpen = ref(false)
  const pendingAgentPrompt = ref('')
  const pendingAgentAutoSend = ref(false)

  const setSelectionActive = (v: boolean) => {
    selectionActive.value = v
  }

  const setAgentOpen = (v: boolean) => {
    agentOpen.value = v
  }

  const openAgent = () => setAgentOpen(true)
  const openAgentWithPrompt = (prompt: string, autoSend = false) => {
    pendingAgentPrompt.value = prompt
    pendingAgentAutoSend.value = autoSend
    setAgentOpen(true)
  }
  const consumeAgentPrompt = () => {
    const request = { prompt: pendingAgentPrompt.value, autoSend: pendingAgentAutoSend.value }
    pendingAgentPrompt.value = ''
    pendingAgentAutoSend.value = false
    return request
  }
  const closeAgent = () => setAgentOpen(false)

  return { selectionActive, agentOpen, pendingAgentPrompt, pendingAgentAutoSend, setSelectionActive, setAgentOpen, openAgent, openAgentWithPrompt, consumeAgentPrompt, closeAgent }
})
