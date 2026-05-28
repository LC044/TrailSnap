<template>
  <div class="container mx-auto py-6 px-4 flex flex-col">
    <!-- Header -->
    <div class="sticky top-0 z-30 backdrop-blur-md">
      <div class="flex px-4 py-3 items-center justify-between flex-shrink-0">
        <div class="flex items-center gap-4">
            <button 
            @click="router.back()" 
            class="p-2 -ml-2 rounded-full hover:bg-gray-100 dark:bg-gray-900 dark:hover:bg-gray-800 transition-colors"
            >
            <ArrowLeft class="w-5 h-5 text-gray-600 dark:text-gray-300" />
            </button>
            <div>
            <h1 class="text-lg font-bold text-gray-900 dark:text-white leading-tight">
                清理相册
            </h1>
            <p class="text-xs text-gray-500">{{ subtitle }}</p>
            </div>
        </div>
        
        <!-- Sort Control -->
        <div class="flex items-center gap-2">
            <span class="text-sm text-gray-600 dark:text-gray-400">排序:</span>
            <select v-model="sortBy" @change="refresh" class="border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 rounded px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500">
                <option value="asc">升序</option>
                <option value="desc">降序</option>
            </select>
        </div>
      </div>
    </div>
    
    <!-- Content -->
    <div class="max-w-7xl mx-auto px-4 py-6">
        <!-- Empty State -->
      <div v-if="!loading && photos.length === 0" class="flex flex-col items-center justify-center py-20 text-gray-500">
        <div class="p-6 rounded-full bg-gray-100 dark:bg-gray-900 mb-4">
          <ImageIcon class="w-12 h-12 opacity-20" />
        </div>
        <p class="text-lg font-medium">暂无照片，请在完成
          <a href="/settings#tasks" class="text-primary-500 hover:underline">大模型智能分析任务</a>
          之后再执行清理操作</p>
      </div>

       <FlatPhotoGallery 
            v-else
            ref="galleryRef"
            :photos="photos" 
            :loading="loading" 
            :show-action-bar="true"
            @click-photo="handleGalleryClick"
            @batch-delete="handleBatchDelete"
            @add-to-album="handleAddToAlbum"
        />
        
        <!-- Load More Sentinel -->
        <div 
            ref="loadMoreTrigger" 
            class="h-20 flex items-center justify-center mt-8"
            v-if="hasMore && photos.length > 0"
        >
            <div v-if="loading" class="w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full animate-spin"></div>
        </div>
    </div>
    
    <!-- Lightbox -->
    <PhotoLightbox
      :visible="showLightbox"
      :image="photos[lightboxIndex]"
      :has-prev="lightboxIndex > 0"
      :has-next="lightboxIndex < photos.length - 1"
      @close="closeLightbox"
      @prev="prevPhoto"
      @next="nextPhoto"
      @delete="handlePhotoDelete"
    />
    
    <!-- Album Select Modal -->
    <AlbumSelector
      v-model:visible="showAlbumSelectModal"
      :photo-ids="tempSelectedIds"
      @success="closeAlbumSelectModal"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Image as ImageIcon } from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import { photoApi } from '@/api/photo'
import { albumService } from '@/api/album'
import { mapPhotoToImage } from '@/stores/photoStore'
import PhotoLightbox from '@/components/PhotoLightbox.vue'
import FlatPhotoGallery from '@/components/FlatPhotoGallery.vue'
import AlbumSelector from '@/components/AlbumSelector.vue'
import type { AlbumImage } from '@/types/album'

const router = useRouter()

const loading = ref(false)
const photos = ref<AlbumImage[]>([])
const skip = ref(0)
const limit = 50
const hasMore = ref(true)
const loadMoreTrigger = ref<HTMLElement | null>(null)
const sortBy = ref<'asc' | 'desc'>('asc')
const galleryRef = ref<InstanceType<typeof FlatPhotoGallery> | null>(null)
const showAlbumSelectModal = ref(false)
const tempSelectedIds = ref<string[]>([])

const subtitle = computed(() => {
  if (loading.value && photos.value.length === 0) return '加载中...'
  return `${photos.value.length}${hasMore.value ? '+' : ''} 张照片`
})

const dedupePhotos = (items: AlbumImage[], existingIds = new Set<string>()) => {
  const seen = new Set(existingIds)
  return items.filter(item => {
    if (seen.has(item.id)) return false
    seen.add(item.id)
    return true
  })
}

const fetchPhotos = async (isLoadMore = false) => {
  if (loading.value) return
  
  if (!isLoadMore) {
    photos.value = []
    skip.value = 0
    hasMore.value = true
  }
  
  loading.value = true
  try {
    const res = await photoApi.getCleanupPhotos({
      skip: skip.value,
      limit: limit,
      sort_by: sortBy.value
    })

    const newPhotos = res.map(item => mapPhotoToImage(item))
    const uniqueNewPhotos = isLoadMore
      ? dedupePhotos(newPhotos, new Set(photos.value.map(item => item.id)))
      : dedupePhotos(newPhotos)

    if (newPhotos.length < limit) {
      hasMore.value = false
    }

    if (isLoadMore) {
      photos.value.push(...uniqueNewPhotos)
    } else {
      photos.value = uniqueNewPhotos
    }

    skip.value += newPhotos.length
  } catch (e) {
    console.error('Fetch failed:', e)
    ElMessage.error('获取照片失败')
  } finally {
    loading.value = false
  }
}

const refresh = () => {
    fetchPhotos(false)
}

const loadMore = () => {
  if (hasMore.value) {
    fetchPhotos(true)
  }
}

// Observer
let observer: IntersectionObserver | null = null

const setupObserver = () => {
  if (observer) observer.disconnect()
  
  observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && hasMore.value && !loading.value) {
      loadMore()
    }
  }, {
    rootMargin: '200px'
  })

  if (loadMoreTrigger.value) {
    observer.observe(loadMoreTrigger.value)
  }
}

watch(loadMoreTrigger, () => {
  if (loadMoreTrigger.value) setupObserver()
})

onMounted(() => {
    fetchPhotos()
})

onUnmounted(() => {
  if (observer) observer.disconnect()
})

// Gallery Actions
const showLightbox = ref(false)
const lightboxIndex = ref(0)

const handleGalleryClick = (photo: AlbumImage) => {
  const index = photos.value.findIndex(p => p.id === photo.id)
  if (index !== -1) {
    openLightbox(index)
  }
}

const handleBatchDelete = async (ids: string[]) => {
  try {
    await ElMessageBox.confirm(`确定要删除选中的 ${ids.length} 张照片吗？`, '批量删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
    
    await albumService.batchUpdatePhotos({
        photo_ids: ids,
        action: 'delete'
    })
    galleryRef.value?.exitSelectionMode()
    photos.value = photos.value.filter(p => !ids.includes(p.id))
    ElMessage.success('批量删除成功')
  } catch (e) {
    if (e !== 'cancel') {
        console.error(e)
        ElMessage.error('删除失败')
    }
  }
}

const handleAddToAlbum = (ids: string[]) => {
    if (ids.length === 0) return
    tempSelectedIds.value = ids
    showAlbumSelectModal.value = true
}

const closeAlbumSelectModal = () => {
    showAlbumSelectModal.value = false
    tempSelectedIds.value = []
    galleryRef.value?.exitSelectionMode()
}

// Lightbox
const openLightbox = (index: number) => {
  lightboxIndex.value = index
  showLightbox.value = true
}

const closeLightbox = () => {
  showLightbox.value = false
}

const prevPhoto = () => {
  if (lightboxIndex.value > 0) {
    lightboxIndex.value--
  }
}

const nextPhoto = () => {
  if (lightboxIndex.value < photos.value.length - 1) {
    lightboxIndex.value++
  }
}

const handlePhotoDelete = async (id: string) => {
  try {
    await albumService.deletePhoto(id)
    photos.value = photos.value.filter(p => p.id !== id)
    ElMessage.success('删除成功')
    if (photos.value.length === 0) {
      closeLightbox()
    } else {
      if (lightboxIndex.value >= photos.value.length) {
        lightboxIndex.value = photos.value.length - 1
      }
    }
  } catch (e) {
    console.error(e)
    ElMessage.error('删除失败')
  }
}
</script>
