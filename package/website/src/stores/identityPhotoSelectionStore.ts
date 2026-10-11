import { defineStore } from 'pinia'
import { ref } from 'vue'
import { faceApi } from '@/api/face'
import { mapPhotoToImage } from '@/stores/photoStore'
import type { AlbumImage } from '@/types/album'

// 独立于图库/相册状态，分页读取人物照片，封面候选不限于前 100 张。
export const useIdentityPhotoSelectionStore = defineStore('identity-photo-selection', () => {
  const images = ref<AlbumImage[]>([])
  const loading = ref(false)
  const hasMore = ref(true)
  const error = ref<string | null>(null)
  const identityId = ref('')
  let page = 1
  let generation = 0
  const resetAll = () => {
    generation++
    images.value = []
    loading.value = false
    hasMore.value = true
    error.value = null
    page = 1
  }
  const setIdentity = (id: string) => { resetAll(); identityId.value = id }
  const loadPhotos = async (reset = false) => {
    if (reset) resetAll()
    if (loading.value || !hasMore.value || !identityId.value) return
    const requestGeneration = generation
    loading.value = true
    error.value = null
    try {
      const photos = await faceApi.getIdentityPhotos(identityId.value, page, 100)
      if (requestGeneration !== generation) return
      images.value.push(...photos.map(mapPhotoToImage))
      hasMore.value = photos.length === 100
      page++
    } catch {
      if (requestGeneration === generation) error.value = '加载人物照片失败，请重试'
    } finally {
      if (requestGeneration === generation) loading.value = false
    }
  }
  return {
    images, loading, hasMore, error, resetAll, setIdentity, loadPhotos,
    getPickerSearchFilters: () => ({ face_id: identityId.value }),
    // 无时间统计的画廊使用平铺模式，数据由 load-more 分页获取。
    timelineStats: null,
    currentContext: { type: 'identity' },
    fetchTimelineStats: async () => {},
    loadPhotosByMonth: async () => {},
  }
})
