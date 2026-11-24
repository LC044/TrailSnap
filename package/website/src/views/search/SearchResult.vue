<template>
  <ConditionSearchResult v-if="isConditionSearch(type)" />
  <div v-else class="mx-auto w-full max-w-screen-2xl min-h-screen pb-8 px-[var(--ts-page-gutter)]">
    <header class="pointer-events-none sticky top-0 z-30 flex min-w-0 items-center gap-2 py-2">
      <BackButton class="pointer-events-auto" label="返回" @click="goBack" />
      <div v-glass-refraction.rim class="ts-liquid-glass ts-glass-title pointer-events-auto flex h-9 min-w-0 items-center gap-2 px-3 md:h-11">
        <h1 class="min-w-0 truncate text-sm font-semibold" :title="title">{{ title }}</h1>
        <p class="ts-muted shrink-0 whitespace-nowrap text-xs">{{ subtitle }}</p>
      </div>
    </header>

    <!-- Content -->
    <div class="mx-auto pb-6 pt-2">
      <!-- Loading State (Initial) -->
      <div v-if="loading && photos.length === 0" class="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 xl:grid-cols-10 gap-4">
        <div v-for="i in 20" :key="i" class="aspect-square bg-gray-200 dark:bg-gray-800 rounded-lg animate-pulse"></div>
      </div>

      <!-- Empty State -->
      <div v-else-if="!loading && photos.length === 0" class="flex flex-col items-center justify-center py-20 text-gray-500">
        <div class="p-6 rounded-full bg-gray-100 dark:bg-gray-900 mb-4">
          <Search class="w-12 h-12 opacity-20" />
        </div>
        <p class="text-lg font-medium">未找到相关照片</p>
        <p class="text-sm mt-2">尝试更换搜索关键词</p>
      </div>

      <!-- Photo Grid -->
      <div v-else>
        <FlatPhotoGallery 
            ref="galleryRef"
            :photos="photos" 
            :loading="loading" 
            :show-action-bar="true"
            context-add-to-album
            @click-photo="handleGalleryClick"
            @batch-delete="handleBatchDelete"
            @add-to-album="handleAddToAlbum"
        />
      </div>

      <!-- Load More Sentinel / Loading Indicator -->
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
      :initial-details="lightboxInitialDetails"
      :image="photos[lightboxIndex] ?? null"
      :images="photos"
      :current-index="lightboxIndex"
      :has-prev="lightboxIndex > 0"
      :has-next="lightboxIndex < photos.length - 1"
      :allow-edit="true"
      :allow-delete="true"
      :allow-add-to-album="true"
      :allow-add-to-person="true"
      :allow-move-to-folder="true"
      @close="closeLightbox"
      @prev="prevPhoto"
      @next="nextPhoto"
      @select="index => (lightboxIndex = index)"
      @delete="handlePhotoDelete"
      @update="performSearch(false)"
      @add-to-album="image => organizeActions?.openAlbum(image.id)"
      @transfer="organizeActions?.openMove(photos[lightboxIndex]?.id || '')"
    />

    <PhotoOrganizeActions ref="organizeActions" @transfer-success="performSearch(false)" />
    
    <!-- Album Select Modal -->
    <AlbumSelector
      v-model:visible="showAlbumSelectModal"
      :photo-ids="tempSelectedIds"
      @success="closeAlbumSelectModal"
    />
  </div>
</template>

<script setup lang="ts">
import BackButton from '@/components/ui/BackButton.vue'
import ConditionSearchResult from './ConditionSearchResult.vue'
import { isConditionSearch } from '@/utils/conditionSearch'
import { ref, computed, watch, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppBack } from '@/composables/useAppBack'
import { Search } from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import searchService from '@/api/search'
import { albumService } from '@/api/album'
import { mapPhotoToImage } from '@/stores/photoStore'
import { usePhotoViewer } from '@/composables/usePhotoViewer'
import PhotoLightbox from '@/components/PhotoLightbox.vue'
import PhotoOrganizeActions from '@/components/PhotoOrganizeActions.vue'
import FlatPhotoGallery from '@/components/FlatPhotoGallery.vue'
import AlbumSelector from '@/components/AlbumSelector.vue'
import type { AlbumImage } from '@/types/album'
import { parseDateRange } from '@/utils/date'

const route = useRoute()
const router = useRouter()
const goBack = useAppBack('/photos')

const query = computed(() => route.query.q as string || '')
const type = computed(() => route.query.type as string | undefined)

const title = computed(() => query.value || '搜索结果')

const loading = ref(false)
const photos = ref<AlbumImage[]>([])
const skip = ref(0)
const limit = 50 // Increased from 3 to 50 for grid view
const hasMore = ref(true)
const loadMoreTrigger = ref<HTMLElement | null>(null)
const galleryRef = ref<InstanceType<typeof FlatPhotoGallery> | null>(null)
const organizeActions = ref<InstanceType<typeof PhotoOrganizeActions> | null>(null)

// Lightbox State
const { visible: showLightbox, index: lightboxIndex, open: openLightbox, close: closeLightbox, prev: prevPhoto, next: nextPhoto } = usePhotoViewer(photos)
const showAlbumSelectModal = ref(false)
const tempSelectedIds = ref<string[]>([])
const preserveAlbumSelection = ref(false)
const lightboxInitialDetails = ref(false)

const handleGalleryClick = (photo: AlbumImage, details = false) => {
  const index = photos.value.findIndex(p => p.id === photo.id)
  if (index !== -1) {
    lightboxInitialDetails.value = details
    openLightbox(index)
  }
}

const handleBatchDelete = async (ids: string[], preserveSelection = false) => {
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
    
    photos.value = photos.value.filter(p => !ids.includes(p.id))
    if (!preserveSelection) galleryRef.value?.exitSelectionMode()
    ElMessage.success('批量删除成功')
  } catch (e) {
    if (e !== 'cancel') {
        console.error(e)
        ElMessage.error('删除失败')
    }
  }
}

const handleAddToAlbum = (ids: string[], preserveSelection = false) => {
    if (ids.length === 0) return
    preserveAlbumSelection.value = preserveSelection
    tempSelectedIds.value = ids
    showAlbumSelectModal.value = true
    if (!preserveSelection) galleryRef.value?.exitSelectionMode()
}

const closeAlbumSelectModal = () => {
    showAlbumSelectModal.value = false
    tempSelectedIds.value = []
    if (!preserveAlbumSelection.value) galleryRef.value?.exitSelectionMode()
    preserveAlbumSelection.value = false
}

const handlePhotoDelete = async (id: string) => {
  try {
    await albumService.deletePhoto(id)
    photos.value = photos.value.filter(p => p.id !== id)
    ElMessage.success('删除成功')
    
  } catch (e) {
    console.error(e)
    ElMessage.error('删除失败')
  }
}

const subtitle = computed(() => {
  if (loading.value && photos.value.length === 0) return '搜索中...'
  return `${photos.value.length}${hasMore.value ? '+' : ''} 个结果`
})

// Intersection Observer for Infinite Scroll
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

onUnmounted(() => {
  if (observer) observer.disconnect()
})

const performSearch = async (isLoadMore = false) => {
  if (isConditionSearch(type.value)) return
  if (!query.value) return
  if (loading.value) return
  
  if (!isLoadMore) {
    photos.value = []
    skip.value = 0
    hasMore.value = true
  }
  
  loading.value = true
  try {
    let startTime = undefined;
    let endTime = undefined;
    
    if (type.value === 'date') {
      const dateRange = parseDateRange(query.value);
      if (dateRange) {
        startTime = dateRange.start;
        endTime = dateRange.end;
      }
    }

    const res = await searchService.searchByText({
      text: type.value === 'date' ? '' : query.value, // if date, text should be empty string
      type: type.value,
      limit: limit,
      skip: skip.value,
      threshold: 0.22,
      start_time: startTime,
      end_time: endTime
    })

    const newPhotos = res.map(item => mapPhotoToImage(item.photo))

    if (newPhotos.length < limit) {
      hasMore.value = false
    }

    if (isLoadMore) {
      photos.value.push(...newPhotos)
    } else {
      photos.value = newPhotos
    }

    skip.value += limit
  } catch (e) {
    console.error('Search failed:', e)
  } finally {
    loading.value = false
    // Re-setup observer after DOM update if needed, but watch handles it usually
  }
}

const loadMore = () => {
  if (hasMore.value) {
    performSearch(true)
  }
}

watch([() => route.query.q, () => route.query.type], () => {
  performSearch()
}, { immediate: true })

</script>
