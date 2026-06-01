<template>
  <div class="recycle-bin-page container mx-auto flex flex-col">
    <!-- Header -->
    <div class="sticky top-[60px] md:top-0 z-30 pointer-events-none mb-4">
      <div class="flex md:flex-row items-center justify-between gap-4 mx-auto px-4 py-3 pointer-events-auto">
        <div class="flex items-center gap-3 w-full max-w-full md:w-auto bg-white/80 dark:bg-gray-900/80 backdrop-blur-md px-3 py-1.5 rounded-full shadow-sm border border-gray-200/50 dark:border-gray-700/50">
          <button @click="router.back()" class="p-1.5 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors bg-white dark:bg-gray-900">
            <ArrowLeft class="w-5 h-5 text-gray-600 dark:text-gray-300" />
          </button>
          <div class="pr-2 min-w-0">
            <h1 class="max-w-[140px] md:max-w-[300px] text-sm md:text-lg font-bold text-gray-900 dark:text-white leading-tight flex items-center gap-2 truncate">
              <span class="truncate">回收站</span>
            </h1>
            <!-- <p class="text-xs text-gray-500 truncate">回收站中的照片将在保留期后被永久删除</p> -->
          </div>
        </div>
      </div>
    </div>

    <!-- Gallery -->
    <div class="mx-auto w-full">
      <!-- Empty State -->
      <div v-if="!loading && photos.length === 0" class="flex flex-col items-center justify-center py-20 text-gray-500">
        <div class="p-6 rounded-full bg-gray-100 dark:bg-gray-900 mb-4">
          <Trash2 class="w-12 h-12 opacity-20" />
        </div>
        <p class="text-lg font-medium">回收站为空</p>
      </div>

      <FlatPhotoGallery
        v-else
        :photos="photos"
        :loading="loading && photos.length === 0"
        delete-label="永久删除"
        :pending-remove-ids="pendingRemoveIds"
        @click-photo="openLightbox"
        @batch-delete="handlePermanentDelete"
      >
        <template #batch-actions="{ selectedIds, clearSelection }">
          <el-dropdown-item
              @click="handleRestore(Array.from(selectedIds)); clearSelection()"
          >
              <div class="flex items-center gap-2 text-primary-600">
                <RefreshCcw class="w-4 h-4" />
                <span>恢复照片</span>
              </div>
          </el-dropdown-item>
        </template>
        <template #overlay-actions="{ photo }">
           <div class="text-xs text-white/90 bg-black/50 px-2 py-0.5 rounded-full flex items-center gap-1">
             <Clock class="w-3 h-3" />
             <span>{{ calculateDaysRemaining(photo) }} 天后删除</span>
           </div>
        </template>
      </FlatPhotoGallery>
    </div>

    <!-- Lightbox -->
    <PhotoLightbox
      :visible="!!lightboxImage"
      :image="lightboxImage"
      :has-prev="hasPrev"
      :has-next="hasNext"
      delete-title="永久删除"
      @close="closeLightbox"
      @delete="handlePhotoDelete"
      @prev="handlePrev"
      @next="handleNext"
    />

    <!-- Delete Confirmation -->
    <ConfirmDialog
      v-model:visible="showDeleteConfirm"
      title="确认操作"
      :message="confirmMessage"
      confirm-text="确定"
      cancel-text="取消"
      type="danger"
      @confirm="confirmDelete"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { RefreshCcw, ArrowLeft, Trash2, Clock } from 'lucide-vue-next'
import FlatPhotoGallery from '@/components/FlatPhotoGallery.vue'
import PhotoLightbox from '@/components/PhotoLightbox.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import type { AlbumImage } from '@/types/album'
import request from '@/utils/request'
import { mapPhotoToImage } from '@/stores/photoStore'
import { useScroll } from '@vueuse/core'

const router = useRouter()
const loading = ref(false)
const photos = ref<AlbumImage[]>([])
const pendingRemoveIds = ref(new Set<string>())
const skip = ref(0)
const limit = 100
const hasMore = ref(true)

// Config
const retentionDays = ref(7)

const fetchConfig = async () => {
    try {
        const { data } = await request.get('/api/system/config')
        if (data && data.recycle_bin && data.recycle_bin.retention_days) {
            retentionDays.value = data.recycle_bin.retention_days
        }
    } catch (e) {
        console.error('Failed to load system config', e)
    }
}

// Calculate days remaining
const calculateDaysRemaining = (photo: AlbumImage) => {
    if (photo.deleted_at) {
        // Assume deleted_at might be in UTC string format, like "2023-10-25T10:00:00"
        // Ensure timezone correctness if backend doesn't return Z
        const deletedAt = new Date(photo.deleted_at + (photo.deleted_at.includes('Z') ? '' : 'Z')).getTime()
        const now = Date.now()
        // Calculate full 24 hour periods passed
        const daysPassed = Math.floor((now - deletedAt) / (1000 * 60 * 60 * 24))
        return Math.max(0, retentionDays.value - daysPassed)
    }
    return retentionDays.value // Fallback
}

// Lightbox state
const lightboxImage = ref<AlbumImage | null>(null)
const currentIndex = computed(() => {
  if (!lightboxImage.value) return -1
  return photos.value.findIndex(p => p.id === lightboxImage.value!.id)
})
const hasPrev = computed(() => currentIndex.value > 0)
const hasNext = computed(() => currentIndex.value < photos.value.length - 1 && currentIndex.value !== -1)

const openLightbox = (photo: AlbumImage) => {
  lightboxImage.value = photo
}

const closeLightbox = () => {
  lightboxImage.value = null
}

const handlePrev = () => {
  if (hasPrev.value) {
    lightboxImage.value = photos.value[currentIndex.value - 1]
  }
}

const handleNext = () => {
  if (hasNext.value) {
    lightboxImage.value = photos.value[currentIndex.value + 1]
  } else if (hasMore.value) {
    loadMore()
  }
}

const handlePhotoDelete = async (photo: AlbumImage) => {
  showDeleteConfirm.value = true
  confirmMessage.value = '确定要永久删除这张照片吗？该操作不可恢复！'
  pendingDeleteIds.value = [photo.id]
}

// Delete Confirm state
const showDeleteConfirm = ref(false)
const confirmMessage = ref('')
const pendingDeleteIds = ref<string[]>([])
let deleteCallback: ((success: boolean) => void) | null = null

const handlePermanentDelete = (ids: string[], callback?: (success: boolean) => void) => {
  showDeleteConfirm.value = true
  confirmMessage.value = `确定要永久删除这 ${ids.length} 张照片吗？该操作不可恢复！`
  pendingDeleteIds.value = ids
  if (callback) {
    deleteCallback = callback
  }
}

const confirmDelete = async () => {
  const ids = pendingDeleteIds.value
  if (ids.length === 0) return
  
  try {
    await request.delete('/api/photos/recycle-bin/permanent', { data: { photo_ids: ids } })
    ElMessage.success(`成功永久删除 ${ids.length} 张照片`)
    photos.value = photos.value.filter(p => !ids.includes(p.id))
    if (lightboxImage.value && ids.includes(lightboxImage.value.id)) {
        closeLightbox()
    }
    if (deleteCallback) {
        deleteCallback(true)
        deleteCallback = null
    }
  } catch (error) {
    console.error(error)
    ElMessage.error('永久删除失败')
    if (deleteCallback) {
        deleteCallback(false)
        deleteCallback = null
    }
  } finally {
    showDeleteConfirm.value = false
    pendingDeleteIds.value = []
  }
}

const fetchPhotos = async (isLoadMore = false) => {
  if (loading.value) return
  if (!isLoadMore) {
    skip.value = 0
    hasMore.value = true
  }
  if (!hasMore.value) return

  loading.value = true
  try {
    const { data } = await request.get('/api/photos/recycle-bin', {
      params: { skip: skip.value, limit }
    })
    
    if (data.length < limit) {
      hasMore.value = false
    }

    const mappedPhotos = data.map(mapPhotoToImage)
    
    if (isLoadMore) {
      photos.value = [...photos.value, ...mappedPhotos]
    } else {
      photos.value = mappedPhotos
    }
    skip.value += data.length

  } catch (error) {
    console.error(error)
    ElMessage.error('加载回收站照片失败')
  } finally {
    loading.value = false
  }
}

const loadMore = () => {
  fetchPhotos(true)
}

const handleRestore = async (ids: string[]) => {
  if (ids.length === 0) return
  try {
    await request.post('/api/photos/recycle-bin/restore', { photo_ids: ids })
    ElMessage.success(`成功恢复 ${ids.length} 张照片`)
    photos.value = photos.value.filter(p => !ids.includes(p.id))
  } catch (error) {
    console.error(error)
    ElMessage.error('恢复失败')
  }
}

const scrollContainer = ref<HTMLElement | Window>(window)
const { y: windowScrollY } = useScroll(scrollContainer)

onMounted(async () => {
  await fetchConfig()
  fetchPhotos()
  
  const mainEl = document.querySelector('main')
  if (mainEl && window.getComputedStyle(mainEl).overflowY === 'auto') {
    scrollContainer.value = mainEl
  }
})

watch(windowScrollY, (y) => {
    if (!hasMore.value || loading.value) return
    
    let scrollHeight = 0
    let clientHeight = 0
    if (scrollContainer.value === window) {
      scrollHeight = document.documentElement.scrollHeight
      clientHeight = window.innerHeight
    } else {
      scrollHeight = (scrollContainer.value as HTMLElement).scrollHeight
      clientHeight = (scrollContainer.value as HTMLElement).clientHeight
    }
    
    const bottom = scrollHeight - clientHeight - y
    if (bottom < 500) {
        loadMore()
    }
})

</script>

<style scoped>
</style>
