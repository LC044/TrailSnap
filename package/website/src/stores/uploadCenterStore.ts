import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUploadStore = defineStore('upload', () => {
  const visible = ref(false)
  const initialized = ref(false)
  const running = ref(false)
  const completed = ref(0)
  const total = ref(0)
  const failed = ref(0)
  const progress = ref(0)
  const open = () => { initialized.value = true; visible.value = true }
  return { visible, initialized, running, completed, total, failed, progress, open }
})
