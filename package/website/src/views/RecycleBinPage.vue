<template>
  <div class="recycle-bin-page container mx-auto flex flex-col">
    <!-- Header -->
    <div class="sticky top-0 z-30 mb-4 md:mb-6 bg-white/90 dark:bg-gray-900/90 backdrop-blur-md border-b border-gray-200 dark:border-gray-800">
      <!-- Responsive Header -->
      <div class="flex items-center justify-between px-4 py-3">
        <!-- Left Side -->
        <div class="flex items-center gap-2">
          <!-- Back button: visible unless we are in mobile selection mode -->
          <button @click="router.back()" class="p-1.5 -ml-1.5 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors" :class="{ 'hidden md:block': isSelectionMode }">
            <ArrowLeft class="w-6 h-6 text-gray-800 dark:text-gray-200" />
          </button>
          
          <!-- Mobile Select All -->
          <button v-if="isSelectionMode" @click="toggleSelectAll" class="md:hidden text-primary-600 dark:text-primary-400 font-medium px-2 py-1">
            {{ isAllSelected ? '取消全选' : '全选' }}
          </button>

          <!-- Title -->
          <h1 class="text-lg md:text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <span :class="{ 'hidden md:inline': isSelectionMode }">最近删除</span>
            <span v-if="isSelectionMode" class="md:hidden">已选择 {{ selectedIds.length }} 项</span>
            <span v-if="isSelectionMode" class="hidden md:inline text-sm font-medium text-gray-500 bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded-full mt-0.5">已选择 {{ selectedIds.length }} 项</span>
          </h1>
        </div>

        <!-- Right Side -->
        <div class="flex items-center gap-1">
          <!-- Normal Actions -->
          <template v-if="!isSelectionMode">
            <button @click="handleEnterSelectionMode" class="p-1.5 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors" title="选择">
              <CheckSquare class="w-5 h-5 text-gray-700 dark:text-gray-300" />
            </button>
            <button class="p-1.5 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
               <MoreVertical class="w-5 h-5 text-gray-700 dark:text-gray-300" />
            </button>
          </template>
          <!-- Selection Actions -->
          <template v-else>
            <!-- PC Select All -->
            <button @click="toggleSelectAll" class="hidden md:block text-primary-600 dark:text-primary-400 font-medium px-3 py-1.5 hover:bg-primary-50 dark:hover:bg-primary-900/30 rounded-full transition-colors mr-2">
              {{ isAllSelected ? '取消全选' : '全选' }}
            </button>
            <button @click="cancelSelection" class="text-primary-600 dark:text-primary-400 font-medium px-2 py-1 hover:bg-primary-50 dark:hover:bg-primary-900/30 rounded-full transition-colors">
              取消
            </button>
          </template>
        </div>
      </div>
      <!-- Hint Text -->
      <div class="px-4 pb-3 text-xs md:text-sm text-gray-500 dark:text-gray-400">
        已删除的内容仅保留{{ retentionDays }}天，逾期将永久删除。
      </div>
    </div>

    <!-- Gallery -->
    <div class="mx-auto w-full px-2 sm:px-4" :class="{ 'pb-28': isSelectionMode }">
      <!-- Empty State -->
      <div v-if="!loading && photos.length === 0" class="flex flex-col items-center justify-center py-20 text-gray-500">
        <div class="p-6 rounded-full bg-gray-100 dark:bg-gray-900 mb-4">
          <Trash2 class="w-12 h-12 opacity-20" />
        </div>
        <p class="text-lg font-medium">回收站为空</p>
      </div>

      <FlatPhotoGallery
        v-else
        ref="galleryRef"
        :photos="photos"
        :loading="loading && photos.length === 0"
        delete-label="永久删除"
        :pending-remove-ids="pendingRemoveIds"
        :show-action-bar="false"
        @click-photo="openLightbox"
        @batch-delete="handlePermanentDelete"
        @selection-change="handleSelectionChange"
      >
        <template #bottom-left-overlay="{ photo }">
           <div class="text-xs text-white drop-shadow-md flex items-center gap-1 px-1">
             <Disc class="w-3.5 h-3.5" />
             <span>{{ calculateDaysRemaining(photo) }}天</span>
           </div>
        </template>
      </FlatPhotoGallery>
    </div>

    <!-- Floating selection action bar (restore / delete) -->
    <Transition name="bar-slide">
      <div
        v-if="isSelectionMode"
        class="fixed bottom-6 left-0 right-0 z-40 flex justify-center px-4 pointer-events-none"
      >
        <div class="pointer-events-auto flex items-center justify-around w-full max-w-[280px] bg-white/95 dark:bg-gray-800/95 backdrop-blur-md shadow-xl border border-gray-200/50 dark:border-gray-700/50 rounded-[2rem] px-6 py-2.5">
          <button 
            @click="handleRestore(selectedIds)" 
            :disabled="selectedIds.length === 0"
            class="flex flex-col items-center justify-center gap-1 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex-1"
            :class="selectedIds.length === 0 ? 'text-gray-400' : 'text-primary-500 hover:text-primary-600'"
          >
            <RefreshCcw class="w-5 h-5" />
            <span class="text-[11px] font-medium">恢复</span>
          </button>

          <!-- Divider -->
          <div class="w-px h-8 bg-gray-200 dark:bg-gray-700 mx-2"></div>

          <button 
            @click="handlePermanentDelete(selectedIds)" 
            :disabled="selectedIds.length === 0"
            class="flex flex-col items-center justify-center gap-1 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex-1"
            :class="selectedIds.length === 0 ? 'text-gray-400' : 'text-red-500 hover:text-red-600'"
          >
            <Trash2 class="w-5 h-5" />
            <span class="text-[11px] font-medium">删除</span>
          </button>
        </div>
      </div>
    </Transition>

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
import { RefreshCcw, ArrowLeft, Trash2, Clock, X, CheckSquare, MoreVertical, Disc } from 'lucide-vue-next'
import FlatPhotoGallery from '@/components/FlatPhotoGallery.vue'
import PhotoLightbox from '@/components/PhotoLightbox.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import type { AlbumImage } from '@/types/album'
import request from '@/utils/request'
import { mapPhotoToImage } from '@/stores/photoStore'
import { useScroll } from '@vueuse/core'
import { useUiStore } from '@/stores/uiStore'

const router = useRouter()
const loading = ref(false)
const photos = ref<AlbumImage[]>([])
const pendingRemoveIds = ref(new Set<string>())
const skip = ref(0)
const limit = 100
const hasMore = ref(true)

const galleryRef = ref<InstanceType<typeof FlatPhotoGallery> | null>(null)
const selectedIds = ref<string[]>([])
const isSelectionMode = ref(false)

// 同步到全局 UI 状态：移动端底部 Tab 栏 / Agent FAB 在选择模式激活时隐藏
const uiStore = useUiStore()
watch(isSelectionMode, (v) => uiStore.setSelectionActive(v))

const isAllSelected = computed(() => {
  return photos.value.length > 0 && selectedIds.value.length === photos.value.length
})

const handleEnterSelectionMode = () => {
  isSelectionMode.value = true
  galleryRef.value?.enterSelectionMode()
}

const toggleSelectAll = () => {
  const allIds = photos.value.map(p => p.id)
  galleryRef.value?.selectAll(allIds)
  if (!isSelectionMode.value) {
    galleryRef.value?.enterSelectionMode()
    isSelectionMode.value = true
  }
}

const handleSelectionChange = (ids: string[]) => {
  selectedIds.value = ids
  if (ids.length > 0) {
    isSelectionMode.value = true
  } else if (isSelectionMode.value && galleryRef.value && !galleryRef.value.isSelectionMode) {
    isSelectionMode.value = false
  }
}

const cancelSelection = () => {
  isSelectionMode.value = false
  galleryRef.value?.exitSelectionMode()
}

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
  deleteCallback = callback || null
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
    cancelSelection()
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
    cancelSelection()
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
/* Floating action bar slides up from the bottom when selection is active. */
.bar-slide-enter-active,
.bar-slide-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}
.bar-slide-enter-from,
.bar-slide-leave-to {
  transform: translateY(100%);
  opacity: 0;
}
</style>
