import { defineStore } from 'pinia'
import { ref } from 'vue'
import { chapterApi } from '@/api/chapter'
import type { ChapterItem, ChapterStatus } from '@/types/chapter'

export const useChapterStore = defineStore('chapters', () => {
  const items = ref<ChapterItem[]>([])
  const status = ref<ChapterStatus>('confirmed')
  const hidden = ref(false)
  const total = ref(0)
  const loading = ref(false)
  const loadingMore = ref(false)

  async function load(nextStatus: ChapterStatus = status.value, nextHidden = false) {
    loading.value = true
    status.value = nextStatus
    hidden.value = nextHidden
    try {
      const result = await chapterApi.list(nextStatus, nextHidden, 0, 50)
      items.value = result.items
      total.value = result.total
    } finally { loading.value = false }
  }
  async function loadMore() {
    if (loading.value || loadingMore.value || items.value.length >= total.value) return
    loadingMore.value = true
    try {
      const result = await chapterApi.list(status.value, hidden.value, items.value.length, 50)
      items.value.push(...result.items)
      total.value = result.total
    } finally { loadingMore.value = false }
  }
  return { items, status, hidden, total, loading, loadingMore, load, loadMore }
})
