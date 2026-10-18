import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

const AUTO_ORIGINAL_KEY = 'trailsnap_auto_view_original'

export const usePhotoViewingStore = defineStore('photoViewing', () => {
  let saved: string | null = null
  try { saved = localStorage.getItem(AUTO_ORIGINAL_KEY) } catch { /* Storage may be unavailable. */ }
  const autoViewOriginal = ref(saved !== 'false')

  watch(autoViewOriginal, value => {
    try { localStorage.setItem(AUTO_ORIGINAL_KEY, String(value)) } catch { /* Keep the session preference. */ }
  }, { flush: 'sync' })

  return { autoViewOriginal }
})
