<template>
  <UnifiedPhotoPage
    :title="title"
    :subtitle="`${totalCount > 0 ? totalCount + ' 个项目' : (photos.length + (hasMore ? '+' : '')) + ' 个项目'}`"
    :loading="loading && photos.length === 0"
    :photos="photos"
    :has-more="hasMore"
    :timeline-items="timeline"
    :timeline-stats="{ timeline }"
    @confirm-delete="handleConfirmDelete"
    @back="goBack"
    @load-more="loadMore"
  />
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppBack } from '@/composables/useAppBack'
import { locationService } from '@/api/location'
import { albumService } from '@/api/album'
import UnifiedPhotoPage from '@/components/UnifiedPhotoPage.vue'
import { mapPhotoToImage, usePhotoStore } from '@/stores/photoStore'
import { useLocationStore } from '@/stores/locationStore'
import type { AlbumImage, Photo } from '@/types/album'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()
const goBack = useAppBack('/album/location')
const locationStore = useLocationStore()
const name = route.params.name as string
const level = (route.query.level as 'city' | 'province' | 'district' | 'scene') || 'city'
const startDate = route.query.startDate as string | undefined
const endDate = route.query.endDate as string | undefined

const loading = ref(false)
const photos = ref<AlbumImage[]>([])
const timeline = ref<any[]>([])
const skip = ref(0)
const limit = 100
const hasMore = ref(true)
const totalCount = ref(0) // Optional: if API returned total count, but currently it doesn't.
const pendingRemoveIds = ref(new Set<string>())
const photoStore = usePhotoStore()

const title = computed(() => {
  if (name === 'map_selection') return route.query.title as string || '地图精选'
  return name
})
const calculateTimelineStats = (photos: AlbumImage[]) => {
  const stats = new Map<string, { year: number, month: number, day: number, count: number }>()

  photos.forEach(photo => {
    const date = new Date(photo.timestamp)
    const year = date.getFullYear()
    const month = date.getMonth() + 1
    const day = date.getDate()
    const key = `${year}-${month}-${day}`

    if (!stats.has(key)) {
      stats.set(key, { year, month, day, count: 0 })
    }
    stats.get(key)!.count++
  })

  timeline.value = Array.from(stats.values()).sort((a, b) => {
    if (a.year !== b.year) return b.year - a.year
    if (a.month !== b.month) return b.month - a.month
    return b.day - a.day
  })
}

const fetchAllPhotos = async () => {
  if (loading.value || !hasMore.value) return
  loading.value = true
  try {
    if (name === 'map_selection') {
       const ids = locationStore.mapSelectedIds
       if (ids.length > 0) {
           const rawPhotos = await albumService.getPhotosByIds(ids)
           const newPhotos = rawPhotos.map(mapPhotoToImage)
           photos.value.push(...newPhotos)
          calculateTimelineStats(photos.value)
       }
       hasMore.value = false
    } else {
      let page = 1
      const limit = 1000
      let hasNext = true
      while (hasNext) {
        // Encode name to ensure special characters (like / or ?) don't break the path
        const safeName = encodeURIComponent(name)
        const rawPhotos = await locationService.getLocationPhotos(safeName, level, skip.value, limit, startDate, endDate)

        const newPhotos = rawPhotos.map(mapPhotoToImage)

        if (newPhotos.length < limit) {
          hasMore.value = false
          hasNext = false
        }
        photos.value.push(...newPhotos)
        skip.value += limit
        page++
        // Calculate timeline
        calculateTimelineStats(photos.value)
      }
    }
  } catch (e) {
    console.error('Failed to load location photos:', e)
    // Optional: show error toast
  } finally {
    loading.value = false
  }
}



const loadMore = async () => {
  if (loading.value || !hasMore.value) return
  loading.value = true
  try {
    let page = 1
    const limit = 100
    // Encode name to ensure special characters (like / or ?) don't break the path
    const safeName = encodeURIComponent(name)
    const rawPhotos = await locationService.getLocationPhotos(safeName, level, skip.value, limit, startDate, endDate)

    const newPhotos = rawPhotos.map(mapPhotoToImage)

    if (newPhotos.length < limit) {
      hasMore.value = false
    }
    photos.value.push(...newPhotos)
    skip.value += limit
    page++
    // Calculate timeline
    calculateTimelineStats(photos.value)
  } catch (e) {
    console.error('Failed to load location photos:', e)
    // Optional: show error toast
  } finally {
    loading.value = false
  }
}

const handleConfirmDelete = async (ids: string[], callback: (success: boolean) => void) => {
  try {
    ids.forEach(id => pendingRemoveIds.value.add(id))

    await photoStore.deletePhotos(ids)
    // Remove from local list
    photos.value = photos.value.filter(img => !ids.includes(img.id))
    calculateTimelineStats(photos.value)
    ElMessage.success('删除成功')

    callback(true)

  } catch (e) {
    ElMessage.error('删除失败')
    callback(false)
  } finally {
    ids.forEach(id => pendingRemoveIds.value.delete(id))
  }
}

onMounted(() => {
  // loadMore()
  fetchAllPhotos()
})
</script>
