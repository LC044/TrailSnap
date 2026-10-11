import { defineStore } from 'pinia'
import { ref } from 'vue'
import searchService from '@/api/search'
import { albumService } from '@/api/album'
import { mapPhotoToImage } from '@/stores/photoStore'
import type { AlbumImage } from '@/types/album'
import { parseDateRange } from '@/utils/date'

export const usePhotoPickerSearchStore = defineStore('photo-picker-search', () => {
  const images = ref<AlbumImage[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const hasMore = ref(false)
  const query = ref('')
  let searchType = 'filename'
  let filters: Record<string, unknown> = {}
  let skip = 0
  let generation = 0
  const limit = 60

  const resetAll = () => {
    generation++
    query.value = ''
    images.value = []
    loading.value = false
    error.value = null
    hasMore.value = false
    skip = 0
  }
  const loadPhotos = async () => {
    if (loading.value || !query.value || !hasMore.value) return
    const requestGeneration = generation
    loading.value = true
    error.value = null
    try {
      // 使用有效图库及现有筛选条件校验候选，排除回收站照片并保持人物/省份范围。
      do {
        const dateRange = searchType === 'date' ? parseDateRange(query.value) : null
        const results = await searchService.searchByText({
          text: searchType === 'date' ? '' : query.value,
          type: searchType || undefined, skip, limit, threshold: 0.22,
          start_time: dateRange?.start, end_time: dateRange?.end,
        })
        if (requestGeneration !== generation) return
        let photos = results.map(result => result.photo)
        if (photos.length) {
          const allowed = await albumService.getAllPhotos(0, limit, { ...filters, ids: photos.map(photo => photo.id) })
          if (requestGeneration !== generation) return
          const ids = new Set(allowed.map(photo => photo.id))
          photos = photos.filter(photo => ids.has(photo.id))
        }
        skip += results.length
        hasMore.value = results.length === limit
        const existing = new Set(images.value.map(photo => photo.id))
        images.value.push(...photos.filter(photo => !existing.has(photo.id)).map(mapPhotoToImage))
        if (photos.length) break
      } while (hasMore.value && requestGeneration === generation)
    } catch {
      if (requestGeneration === generation) error.value = '搜索失败，请重试'
    } finally {
      if (requestGeneration === generation) loading.value = false
    }
  }
  const search = async (text: string, type: string, scope: Record<string, unknown> = {}) => {
    resetAll()
    query.value = text.trim()
    searchType = type
    filters = scope
    hasMore.value = Boolean(query.value)
    await loadPhotos()
  }
  return {
    images, loading, error, hasMore, query, search, loadPhotos, resetAll,
    timelineStats: null,
    currentContext: { type: 'search' },
    loadPhotosByMonth: async () => {},
  }
})
