<template>
  <div class="photo-selector-container h-full flex flex-col bg-white dark:bg-gray-950">
    <!-- Header -->
    <div class="p-4 border-b border-gray-100 dark:border-gray-800 flex justify-between items-center sticky top-0 z-[60] bg-white/80 dark:bg-gray-950/80 backdrop-blur-md">
      <div class="flex items-center gap-3">
        <button v-if="isSelector" @click="$emit('cancel')" class="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full transition-colors">
          <X class="w-5 h-5 text-gray-500" />
        </button>
        <h3 class="font-bold text-lg text-gray-900 dark:text-white">{{ title || '选择照片' }}</h3>
      </div>
      <div class="flex items-center gap-2">
        <button
          @click="showViewOptions = !showViewOptions"
          class="p-2 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full transition-all"
          title="视图设置"
        >
          <Settings2 class="w-5 h-5" />
        </button>

        <button
          v-if="isSelector"
          @click="confirmSelection"
          :disabled="selectedIds.length === 0"
          class="bg-primary-500 hover:bg-primary-600 disabled:opacity-50 disabled:cursor-not-allowed text-white px-4 py-2 rounded-full shadow-lg shadow-primary-500/30 flex items-center gap-2 text-sm font-medium transition-all active:scale-95"
        >
          <Check class="w-4 h-4" />
          <span>确认选择 ({{ selectedIds.length }})</span>
        </button>
      </div>

      <!-- View Options Dropdown -->
      <Transition
        enter-active-class="transition duration-200 ease-out"
        enter-from-class="transform scale-95 opacity-0"
        enter-to-class="transform scale-100 opacity-100"
        leave-active-class="transition duration-75 ease-in"
        leave-from-class="transform scale-100 opacity-100"
        leave-to-class="transform scale-95 opacity-0"
      >
        <div v-if="showViewOptions" 
             ref="viewOptionsRef"
             class="absolute right-4 top-full mt-2 w-48 bg-white dark:bg-gray-900 rounded-xl shadow-xl border border-gray-100 dark:border-gray-800 p-2 z-50 origin-top-right"
        >
          <div class="space-y-3 p-1">
            <!-- View Size -->
            <div class="space-y-2">
              <p class="text-xs font-medium text-gray-500 px-1">图片大小</p>
              <div class="flex bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
                <button v-for="size in ['sm', 'md', 'lg']" :key="size"
                  @click="viewSize = size as any"
                  class="flex-1 p-1.5 rounded text-center transition-colors"
                  :class="{ 'bg-white dark:bg-gray-700 shadow-sm text-primary-500': viewSize === size, 'text-gray-500': viewSize !== size }"
                >
                  <Grid3x3 v-if="size === 'sm'" class="w-4 h-4 mx-auto" />
                  <Grid2x2 v-if="size === 'md'" class="w-4 h-4 mx-auto" />
                  <Maximize v-if="size === 'lg'" class="w-4 h-4 mx-auto" />
                </button>
              </div>
            </div>

            <!-- Layout Mode -->
            <div class="space-y-2">
              <p class="text-xs font-medium text-gray-500 px-1">布局模式</p>
              <div class="grid grid-cols-1 gap-1">
                <button
                  @click="layoutMode = 'waterfall'"
                  class="flex items-center gap-2 px-2 py-1.5 rounded-lg transition-colors text-sm"
                  :class="{ 'bg-primary-50 dark:bg-primary-900/20 text-primary-600': layoutMode === 'waterfall', 'hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300': layoutMode !== 'waterfall' }"
                >
                  <LayoutDashboard class="w-4 h-4" />
                  <span>瀑布流</span>
                </button>
                <button
                  @click="layoutMode = 'grid'"
                  class="flex items-center gap-2 px-2 py-1.5 rounded-lg transition-colors text-sm"
                  :class="{ 'bg-primary-50 dark:bg-primary-900/20 text-primary-600': layoutMode === 'grid', 'hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300': layoutMode !== 'grid' }"
                >
                  <LayoutGrid class="w-4 h-4" />
                  <span>正方形</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </div>

    <!-- Main Content -->
    <div ref="scrollContainer" class="flex-1 overflow-y-auto relative custom-scrollbar">
      <!-- Loading Overlay for initial data -->
      <div v-if="initialLoading" class="absolute inset-0 z-10 flex items-center justify-center bg-white/50 dark:bg-gray-950/50 backdrop-blur-sm">
        <div class="flex flex-col items-center gap-3">
          <Loader2 class="w-8 h-8 animate-spin text-primary-500" />
          <p class="text-sm text-gray-500">加载中...</p>
        </div>
      </div>

      <div class="container mx-auto px-4 py-6">
        <PhotoGallery
          ref="galleryRef"
          :store="store"
          :photos="images"
          :timeline-stats="store.timelineStats"
          :loading="store.loading"
          :has-more="store.hasMore"
          :error="store.error"
          :layout-mode="layoutMode"
          :view-size="viewSize"
          :scroll-container="scrollContainer"
          :show-action-bar="false"
          v-model:active-date="activeDate"
          @load-more="store.loadPhotos"
          @click-photo="openLightbox"
          @batch-delete="handleBatchDelete"
          @add-to-album="handleBatchAddToAlbum"
          @retry="store.loadPhotos(true)"
          @selection-change="handleSelectionChange"
        />
      </div>

      <!-- Timeline Sidebar -->
      <AlbumTimeline
        :items="store.timelineStats?.timeline || []"
        :active-date="activeDate"
        @select="scrollToDate"
      />
    </div>

    <!-- Lightbox -->
    <PhotoLightbox
      :visible="!!lightboxImage"
      :image="lightboxImage"
      @close="closeLightbox"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useAlbumStore } from '@/stores/albumStore'
import { usePhotoStore } from '@/stores/photoStore'
import type { AlbumImage } from '@/types/album'
import {
  X, Maximize, Grid3x3, Grid2x2, LayoutDashboard, LayoutGrid,
  Check, Settings2, Loader2, Folder, ImagePlus
} from 'lucide-vue-next'
import { onClickOutside } from '@vueuse/core'
import AlbumTimeline from '@/components/AlbumTimeline.vue'
import PhotoLightbox from '@/components/PhotoLightbox.vue'
import PhotoGallery from '@/components/PhotoGallery.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import ParticleExplosion from '@/components/ParticleExplosion.vue'
import { ElMessage } from 'element-plus'

const props = defineProps<{
  isSelector?: boolean
  title?: string
  store?: any
}>()

const emit = defineEmits<{
  (e: 'select', ids: string[]): void
  (e: 'cancel'): void
}>()

const albumStore = useAlbumStore()
const defaultStore = usePhotoStore()
const store = computed(() => props.store || defaultStore)

// UI State
const images = computed(() => store.value.images)
const albums = computed(() => albumStore.allAlbums)
const viewSize = ref<'sm' | 'md' | 'lg'>('md')
const layoutMode = ref<'masonry' | 'grid' | 'list' | 'waterfall'>('grid')
const activeDate = ref('')
const lightboxImage = ref<AlbumImage | null>(null)
const showViewOptions = ref(false)
const viewOptionsRef = ref<HTMLElement | null>(null)
const initialLoading = ref(false)

// Selection State
const selectedIds = ref<string[]>([])
const galleryRef = ref<InstanceType<typeof PhotoGallery> | null>(null)
const scrollContainer = ref<HTMLElement | null>(null)

// Animation & Modal State
const showAlbumSelectModal = ref(false)
const tempSelectedIds = ref<string[]>([])
const showDeleteConfirm = ref(false)
const idsToDelete = ref<string[]>([])

onClickOutside(viewOptionsRef, () => {
  showViewOptions.value = false
})

// Methods
const confirmSelection = () => {
  emit('select', selectedIds.value)
}

const scrollToDate = (date: string) => {
  galleryRef.value?.scrollToDate(date)
  activeDate.value = date
}

const openLightbox = (img: AlbumImage) => {
  lightboxImage.value = img
}

const closeLightbox = () => {
  lightboxImage.value = null
}

const handleBatchDelete = async (ids: string[]) => {
  if (ids.length === 0) return
  idsToDelete.value = ids
  showDeleteConfirm.value = true
}

const handleBatchAddToAlbum = (ids: string[]) => {
  if (ids.length === 0) return
  if (props.isSelector) {
    // In selector mode, this action is the same as confirm
    selectedIds.value = ids
    confirmSelection()
  } else {
    tempSelectedIds.value = ids
    showAlbumSelectModal.value = true
  }
}


const handleSelectionChange = (ids: string[]) => {
  selectedIds.value = ids
}

onMounted(async () => {
  initialLoading.value = true
  try {
    if (props.isSelector) {
      galleryRef.value?.enterSelectionMode()
    }
    // Initial Load for selector
    await albumStore.fetchAlbums()
    await store.value.fetchTimelineStats()
    await store.value.loadPhotos(true)
  } finally {
    initialLoading.value = false
  }
})

onUnmounted(() => {
  if (props.isSelector) {
    store.value.resetAll()
  }
})
</script>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(156, 163, 175, 0.3);
  border-radius: 3px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(156, 163, 175, 0.5);
}

.shake-animation {
  animation: shake 0.5s cubic-bezier(.36,.07,.19,.97) both;
}

@keyframes shake {
  10%, 90% { transform: translate3d(-1px, 0, 0); }
  20%, 80% { transform: translate3d(2px, 0, 0); }
  30%, 50%, 70% { transform: translate3d(-4px, 0, 0); }
  40%, 60% { transform: translate3d(4px, 0, 0); }
}
</style>
