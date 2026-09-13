import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api, type User } from '../api'

const TOKEN_KEY = 'rp_token'

export const useSessionStore = defineStore('session', () => {
  const user = ref<User | null>(null)
  const restoring = ref(false)
  const isManager = computed(() => user.value?.role === 'admin' || user.value?.role === 'owner')
  const isOwner = computed(() => user.value?.role === 'owner')

  function acceptSession(token: string, nextUser: User) {
    localStorage.setItem(TOKEN_KEY, token)
    user.value = nextUser
  }

  async function restore() {
    if (!localStorage.getItem(TOKEN_KEY) || restoring.value) return
    restoring.value = true
    try {
      user.value = await api.me()
    } catch {
      localStorage.removeItem(TOKEN_KEY)
      user.value = null
    } finally {
      restoring.value = false
    }
  }

  function clear() {
    localStorage.removeItem(TOKEN_KEY)
    user.value = null
  }

  return { user, restoring, isManager, isOwner, acceptSession, restore, clear }
})
