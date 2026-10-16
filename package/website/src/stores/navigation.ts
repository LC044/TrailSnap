import { defineStore } from 'pinia'
import { ref, shallowRef } from 'vue'
import type { RouteLocationNormalized } from 'vue-router'

export const useNavigationStore = defineStore('navigation', () => {
  const pending = shallowRef<RouteLocationNormalized | null>(null)
  const failed = shallowRef<RouteLocationNormalized | null>(null)
  const message = ref('')

  function start(to: RouteLocationNormalized) {
    pending.value = to
    failed.value = null
    message.value = ''
  }

  function owns(to: RouteLocationNormalized): boolean {
    for (let target: RouteLocationNormalized | undefined = to; target; target = target.redirectedFrom) {
      if (pending.value === target) return true
    }
    return false
  }

  function finish(to: RouteLocationNormalized) {
    if (owns(to)) pending.value = null
  }

  function fail(to: RouteLocationNormalized) {
    if (!owns(to)) return
    pending.value = null
    failed.value = to
    message.value = '页面未能打开，请检查网络后重试。如果仍然失败，可以重新加载页面。'
  }

  function dismiss() { failed.value = null }

  return { pending, failed, message, start, finish, fail, dismiss }
})
