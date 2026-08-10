<template>
  <UnifiedPhotoPage
    :title="title"
    :subtitle="`${(photos.length + (hasMore ? '+' : '')) + ' 个项目'}`"
    :loading="loading && photos.length === 0"
    :photos="photos"
    :has-more="hasMore"
    :timeline-items="timeline"
    :timeline-stats="{ timeline }"
    @confirm-delete="handleConfirmDelete"
    @back="goBack"
    @load-more="loadMore"
    >
    <template #batch-actions="{ selectedIds, clearSelection }">
      <el-dropdown-item
          v-if="selectedIds.size === 1"
          @click="handleSetCover(Array.from(selectedIds)); clearSelection()"
      >
          <div class="flex items-center gap-2">
            <ImageIcon class="w-4 h-4" />
            <span>设为封面</span>
          </div>
      </el-dropdown-item>
      <el-dropdown-item
          @click="removePhotoFromTags(Array.from(selectedIds)); clearSelection()"
      >
          <div class="flex items-center gap-2">
            <ImageMinus class="w-4 h-4" />
            <span>从分类中移除</span>
          </div>
      </el-dropdown-item>
    </template>
  </UnifiedPhotoPage>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppBack } from '@/composables/useAppBack'
import { classificationService } from '@/api/classification'
import UnifiedPhotoPage from '@/components/UnifiedPhotoPage.vue'
import { mapPhotoToImage, usePhotoStore } from '@/stores/photoStore'
import type { AlbumImage } from '@/types/album'
import { ElMessage } from 'element-plus'
import { ImageMinus, ImageIcon } from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const goBack = useAppBack('/album/classification')
const name = route.params.name as string
const photoStore = usePhotoStore()
const loading = ref(false)
const photos = ref<AlbumImage[]>([])
const timeline = ref<any[]>([])
const skip = ref(0)
const hasMore = ref(true)
const totalCount = ref(0)
const pendingRemoveIds = ref(new Set<string>())
const title = computed(() => name)

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

const loadMore = async () => {
  if (loading.value || !hasMore.value) return
  loading.value = true
  try {
    const limit = 500
    let hasNext = true

    while (hasNext) {
      const rawPhotos = await classificationService.getTagPhotos(name, skip.value, limit)

      if (rawPhotos.length < limit) {
        hasMore.value = false
        hasNext = false
      }

      const newPhotos = rawPhotos.map(mapPhotoToImage)
      photos.value.push(...newPhotos)
      skip.value += limit

      calculateTimelineStats(photos.value)
    }
  } catch (e) {
    console.error('Failed to load tag photos:', e)
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

const removePhotoFromTags = async (ids: string[]) => {
  try {
    await classificationService.removePhotosFromTag(name, ids)
    photos.value = photos.value.filter(img => !ids.includes(img.id))
    calculateTimelineStats(photos.value)
    ElMessage.success('从分类中移除成功')
  } catch (e) {
    ElMessage.error('从分类中移除失败')
  }
}

const handleSetCover = async (ids: string[]) => {
  if (!ids.length) return
  const photoId = ids[0]
  try {
    await classificationService.setCover(name, photoId)
    ElMessage.success('已设为封面')
  } catch (e) {
    ElMessage.error('设置封面失败')
  }
}



onMounted(() => {
  loadMore()
})
</script>
