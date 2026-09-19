<template>
  <UnifiedPhotoPage
    :title="title"
    :subtitle="`${images.length} 张`"
    :loading="loading"
    :loading-title="!loaded"
    :photos="images"
    :timeline-items="timeline"
    :timeline-stats="{ timeline }"
    :allow-upload="false"
    :show-back="true"
    @back="goBack"
  />
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppBack } from '@/composables/useAppBack'
import { faceApi } from '@/api/face'
import type { AlbumImage } from '@/types/album'

import UnifiedPhotoPage from '@/components/UnifiedPhotoPage.vue'
import { usePhotoStore } from '@/stores/photoStore'
import { ElMessage } from 'element-plus'

const photoStore = usePhotoStore()
const route = useRoute()
const router = useRouter()
const goBack = useAppBack('/album/people')

// 路由参数：/album/people/group/:ids（ids = 排序后逗号分隔的 identity UUID）
const idsParam = route.params.ids as string
const identityIds = computed(() => (idsParam || '').split(',').filter(Boolean))

// 标题优先用 query 里的成员名（列表页带入，避免详情页再查一遍人物名）
const title = computed(() => {
  const names = (route.query.names as string) || ''
  return names || '合影'
})

const loading = ref(true)
const loaded = ref(false)
const images = ref<AlbumImage[]>([])
const timeline = ref<any[]>([])

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
  loading.value = true
  images.value = []

  try {
    let page = 1
    const limit = 500
    let hasNext = true

    while (hasNext) {
      const photos = await faceApi.getGroupAlbumPhotos(identityIds.value, page, limit)
      if (photos.length === 0) break

      const newImages = photos.map(photoStore.mapPhotoToImage)
      images.value.push(...newImages)

      if (photos.length < limit) hasNext = false
      page++
    }

    // Sort by time desc
    images.value.sort((a, b) => b.timestamp - a.timestamp)
    calculateTimelineStats(images.value)
    loaded.value = true
  } catch (e) {
    console.error(e)
    ElMessage.error('加载合影照片失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  if (identityIds.value.length < 2) {
    router.replace('/album/people')
    return
  }
  fetchAllPhotos()
})
</script>

<style scoped>
/* Scoped styles */
</style>
