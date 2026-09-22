import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { memoryApi } from '@/api/memory'
import type { MemoryItem, MemoryStatus } from '@/types/memory'

export const useMemoryStore = defineStore('memory', () => {
  const activeStatus = ref<MemoryStatus>('candidate')
  const items = ref<MemoryItem[]>([])
  const counts = ref({ candidate: 0, confirmed: 0, ignored: 0 })
  const loading = ref(false)
  const discovering = ref(false)
  const total = ref(0)
  const page = ref(1)
  const pageSize = ref(20)

  const candidateCount = computed(() => counts.value.candidate)

  async function fetchCounts() {
    counts.value = await memoryApi.counts()
  }

  async function fetchList(status: MemoryStatus = activeStatus.value, targetPage = page.value) {
    activeStatus.value = status
    page.value = targetPage
    loading.value = true
    try {
      const data = await memoryApi.list(status, (page.value - 1) * pageSize.value, pageSize.value)
      items.value = data.items
      total.value = data.total
      const lastPage = Math.max(1, Math.ceil(total.value / pageSize.value))
      if (page.value > lastPage) return fetchList(status, lastPage)
    } finally {
      loading.value = false
    }
  }

  async function discover() {
    discovering.value = true
    try {
      const result = await memoryApi.discover()
      await Promise.all([fetchList('candidate', 1), fetchCounts()])
      return result.created
    } finally {
      discovering.value = false
    }
  }

  async function confirm(id: string) {
    await memoryApi.confirm(id)
    await Promise.all([fetchList(activeStatus.value, page.value), fetchCounts()])
  }

  async function ignore(id: string) {
    await memoryApi.ignore(id)
    await Promise.all([fetchList(activeStatus.value, page.value), fetchCounts()])
  }

  async function restore(id: string) {
    await memoryApi.restore(id)
    await Promise.all([fetchList(activeStatus.value, page.value), fetchCounts()])
  }

  return {
    activeStatus, items, counts, candidateCount, loading, discovering, total, page, pageSize,
    fetchCounts, fetchList, discover, confirm, ignore, restore,
  }
})
