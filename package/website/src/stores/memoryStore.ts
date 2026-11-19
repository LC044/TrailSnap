import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { memoryApi } from '@/api/memory'
import type { MemoryItem, MemoryStatus } from '@/types/memory'

export const useMemoryStore = defineStore('memory', () => {
  const activeStatus = ref<MemoryStatus>('confirmed')
  const items = ref<MemoryItem[]>([])
  const counts = ref({ candidate: 0, confirmed: 0, ignored: 0 })
  const loading = ref(false)
  const listError = ref(false)
  const discovering = ref(false)
  const total = ref(0)
  const page = ref(1)
  const pageSize = ref(20)
  let listRequest = 0

  const candidateCount = computed(() => counts.value.candidate)

  async function fetchCounts() {
    counts.value = await memoryApi.counts()
  }

  async function fetchList(status: MemoryStatus = activeStatus.value, targetPage = page.value, background = false) {
    const request = ++listRequest
    const keepVisible = background && !loading.value && status === activeStatus.value && targetPage === page.value
    activeStatus.value = status
    page.value = targetPage
    loading.value = !keepVisible
    listError.value = false
    try {
      const data = await memoryApi.list(status, (targetPage - 1) * pageSize.value, pageSize.value)
      if (request !== listRequest) return
      items.value = data.items
      total.value = data.total
      const lastPage = Math.max(1, Math.ceil(total.value / pageSize.value))
      if (targetPage > lastPage) return fetchList(status, lastPage)
    } catch (error) {
      if (request !== listRequest) return
      listError.value = true
      throw error
    } finally {
      if (request === listRequest) loading.value = false
    }
  }

  async function discover() {
    discovering.value = true
    try {
      const result = await memoryApi.discover()
      await Promise.allSettled([
        activeStatus.value === 'candidate' ? fetchList('candidate', 1, true) : Promise.resolve(),
        fetchCounts(),
      ])
      return result.created
    } finally {
      discovering.value = false
    }
  }

  async function confirm(id: string) {
    await memoryApi.confirm(id)
    await refreshList()
  }

  async function ignore(id: string) {
    await memoryApi.ignore(id)
    await refreshList()
  }

  async function restore(id: string) {
    await memoryApi.restore(id)
    await refreshList()
  }

  async function refreshList() {
    await Promise.allSettled([fetchList(activeStatus.value, page.value, true), fetchCounts()])
  }

  return {
    activeStatus, items, counts, candidateCount, loading, listError, discovering, total, page, pageSize,
    fetchCounts, fetchList, discover, confirm, ignore, restore,
  }
})
