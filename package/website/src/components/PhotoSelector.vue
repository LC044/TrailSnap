<template>
  <div class="photo-selector-container relative min-h-0 min-w-0 h-full flex flex-col bg-white dark:bg-gray-950"
    :style="{ '--photo-page-header-height': headerHeight + 'px' }">
    <div ref="scrollContainer" class="picker-scroll-container min-h-0 flex-1 overflow-y-auto" @scroll.passive="onGalleryScroll">
      <div ref="scrollContent">
        <header ref="header" v-glass-refraction="glassHeader" class="picker-header sticky top-0 z-[60]"
          :class="{ 'ts-liquid-glass': glassHeader, 'picker-header--fullscreen': mobileDialogHeader }">
          <div class="relative flex min-h-14 items-center justify-between gap-2 px-[var(--ts-page-gutter)] py-2 md:py-4">
            <div v-if="mobileDialogHeader" class="flex min-w-0 flex-1 items-center gap-2 md:hidden">
              <BackButton label="返回" :disabled="busy" @click="$emit('cancel')" />
              <h2 class="truncate text-base font-semibold" :title="title">{{ title }}</h2>
            </div>
            <div v-else-if="!embedded" class="flex min-w-0 items-center gap-2">
              <button v-if="isSelector" @click="$emit('cancel')" class="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full transition-colors">
                <X class="w-5 h-5 text-gray-500 dark:text-gray-400" />
              </button>
              <h3 class="truncate font-bold text-lg text-gray-900 dark:text-white">{{ title || '选择照片' }}</h3>
            </div>
            <div class="picker-actions ml-auto flex shrink-0 items-center gap-1 md:gap-2">
              <button type="button" aria-label="搜索照片" title="搜索照片" :disabled="busy"
                class="picker-tool ts-button ts-button-secondary ts-button-sm" @click="showSearchDialog = true">
                <Search class="h-4 w-4" /><span class="hidden md:inline">搜索</span>
              </button>
              <button v-if="enableFilters" type="button" aria-label="筛选照片" title="筛选照片"
                :aria-expanded="showFilterDialog" :disabled="busy"
                class="picker-tool ts-button ts-button-secondary ts-button-sm"
                :class="{ 'text-primary-600 dark:text-primary-400': activeFilterCount > 0 }"
                @click="showFilterDialog = true">
                <Filter class="h-4 w-4" /><span class="hidden md:inline">筛选</span><span v-if="activeFilterCount">{{ activeFilterCount }}</span>
              </button>
              <button
                @click="showViewOptions = !showViewOptions"
                type="button"
                class="picker-tool ts-icon-button ts-button-ghost rounded-full"
                aria-label="视图设置"
                :aria-expanded="showViewOptions"
                title="视图设置"
              >
                <Settings2 class="w-5 h-5" />
              </button>

              <button
                v-if="isSelector"
                type="button"
                @click="confirmSelection"
                :disabled="selectedIds.length === 0 || busy"
                :aria-label="confirmationLabel"
                class="picker-confirm bg-primary-500 hover:bg-primary-600 disabled:opacity-50 disabled:cursor-not-allowed text-white px-2.5 md:px-4 py-2 rounded-full shadow-lg shadow-primary-500/30 flex items-center justify-center gap-1 md:gap-2 whitespace-nowrap text-sm font-medium transition-all active:scale-95"
              >
                <Check class="w-4 h-4" />
                <span>{{ confirmationLabel }}</span>
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

          <div v-if="searchStore.query" class="shrink-0 flex items-center gap-2 border-b border-gray-100 px-4 py-2 dark:border-gray-800">
            <p class="min-w-0 flex-1 truncate text-sm text-gray-700 dark:text-gray-200">搜索：{{ searchStore.query }}</p>
            <button type="button" class="ts-button ts-button-ghost ts-button-sm" :disabled="busy" @click="clearSearch">返回图库</button>
          </div>

          <!-- Main Content -->
          <div v-if="enableFilters && activeFilterCount" class="shrink-0 flex items-center justify-between gap-2 border-b border-gray-100 px-4 py-2 dark:border-gray-800">
            <p class="text-sm ts-muted">已启用 {{ activeFilterCount }} 项筛选</p>
            <button type="button" class="ts-button ts-button-ghost ts-button-sm" :disabled="busy" @click="clearFilters">清除筛选</button>
          </div>
        </header>
        <div class="relative">
          <!-- Loading Overlay for initial data -->
          <div v-if="initialLoading" class="absolute inset-0 z-10 flex items-center justify-center bg-white/50 dark:bg-gray-950/50 backdrop-blur-sm">
            <div class="flex flex-col items-center gap-3">
              <Loader2 class="w-8 h-8 animate-spin text-primary-500" />
              <p class="text-sm text-gray-500">加载中...</p>
            </div>
          </div>

          <div class="mx-auto w-full max-w-screen-2xl px-[var(--ts-page-gutter)] py-6">
            <PhotoGallery
              class="!min-h-0"
              ref="galleryRef"
              :store="displayStore"
              :photos="images"
              :timeline-stats="displayStore.timelineStats"
              :loading="displayStore.loading"
              :has-more="displayStore.hasMore"
              :error="displayStore.error"
              :layout-mode="layoutMode"
              :view-size="viewSize"
              :scroll-container="scrollContainer"
              :show-action-bar="false"
              :single-select="singleSelect"
              v-model:active-date="activeDate"
              @load-more="loadMore"
              @click-photo="openLightbox"
              @batch-delete="handleBatchDelete"
              @add-to-album="handleBatchAddToAlbum"
              @retry="retryLoad"
              @selection-change="handleSelectionChange"
            />
            <div v-if="!displayStore.timelineStats && displayStore.hasMore" class="mt-4 flex justify-center">
              <button type="button" class="ts-button ts-button-secondary" :disabled="displayStore.loading" @click="loadMore">
                {{ displayStore.loading ? '加载中…' : '加载更多照片' }}
              </button>
            </div>
          </div>

          <!-- Timeline Sidebar -->
          <div class="hidden md:block">
            <AlbumTimeline
              :items="displayStore.timelineStats?.timeline || []"
              :active-date="activeDate"
              @select="scrollToDate"
            />
          </div>
        </div>
      </div>
    </div>
    <PhotoPickerScrollbar v-if="images.length || displayStore.timelineStats?.timeline?.length" :container="scrollContainer" :content="scrollContent" />

    <ResponsiveDialog v-model="showSearchDialog" title="搜索照片" max-width="48rem"
      mobile-mode="fullscreen" mobile-back panel-class="photo-picker-search-dialog">
      <MobileSearch v-if="showSearchDialog" embedded @search="submitSearch" />
    </ResponsiveDialog>

    <ResponsiveDialog v-if="enableFilters" v-model="showFilterDialog" title="筛选照片" max-width="28rem" mobile-mode="fullscreen" mobile-back>
      <FilterPanel v-if="showFilterDialog" :store="filterStore" />
      <template #footer>
        <div class="flex justify-between gap-3">
          <button type="button" class="ts-button ts-button-secondary" :disabled="busy" @click="clearFilters">清除筛选</button>
          <button type="button" class="ts-button ts-button-primary" @click="showFilterDialog = false">查看结果</button>
        </div>
      </template>
    </ResponsiveDialog>

    <!-- Lightbox -->
    <PhotoLightbox
      :visible="!!lightboxImage"
      :image="lightboxImage"
      @close="closeLightbox"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, onUnmounted, watch } from 'vue'
import { useAlbumStore } from '@/stores/albumStore'
import { usePhotoStore } from '@/stores/photoStore'
import { useUiStore } from '@/stores/uiStore'
import { usePhotoPickerSearchStore } from '@/stores/photoPickerSearchStore'
import ResponsiveDialog from '@/components/ui/ResponsiveDialog.vue'
import BackButton from '@/components/ui/BackButton.vue'
import MobileSearch from '@/views/search/MobileSearch.vue'
import PhotoPickerScrollbar from '@/components/PhotoPickerScrollbar.vue'
import FilterPanel from '@/components/FilterPanel.vue'
import type { AlbumImage } from '@/types/album'
import {
  X, Maximize, Grid3x3, Grid2x2, LayoutDashboard, LayoutGrid,
  Check, Settings2, Loader2, Search, Filter
} from 'lucide-vue-next'
import { onClickOutside, useMediaQuery, useResizeObserver } from '@vueuse/core'
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
  embedded?: boolean
  mobileDialogHeader?: boolean
  singleSelect?: boolean
  busy?: boolean
  enableFilters?: boolean
  allowedFileTypes?: string[]
}>()

const emit = defineEmits<{
  (e: 'select', ids: string[]): void
  (e: 'cancel'): void
}>()

const albumStore = useAlbumStore()
const defaultStore = usePhotoStore()
const uiStore = useUiStore()
const store = computed(() => props.store || defaultStore)
const searchStore = usePhotoPickerSearchStore()
searchStore.resetAll()
const showSearchDialog = ref(false)
const showFilterDialog = ref(false)
const displayStore = computed(() => searchStore.query ? searchStore : store.value)
const constrainMediaTypes = () => {
  if (!props.allowedFileTypes?.length) return
  const selected = store.value.selectedFilters.file_types.filter((type: string) => props.allowedFileTypes!.includes(type))
  store.value.selectedFilters.file_types.splice(0, store.value.selectedFilters.file_types.length,
    ...(selected.length ? selected : props.allowedFileTypes))
}
const activeFilterCount = computed(() => Object.entries(store.value.selectedFilters || {}).reduce((count, [key, value]) => {
  if (!Array.isArray(value)) return count
  if (key === 'file_types' && props.allowedFileTypes?.length &&
    value.length === props.allowedFileTypes.length && value.every(type => props.allowedFileTypes!.includes(type))) return count
  return count + value.length
}, 0))
const refreshFilters = async () => {
  constrainMediaTypes()
  if (scrollContainer.value) scrollContainer.value.scrollTop = 0
  if (searchStore.query) await searchStore.refreshFilters(store.value.getPickerSearchFilters?.() ?? {})
  else await store.value.loadPhotos(true)
}
// Adapt the shared panel to the currently displayed gallery or search results.
const filterStore = computed(() => ({
  ...store.value,
  get availableFilters() { return {
    ...store.value.availableFilters,
    file_types: (store.value.availableFilters?.file_types || []).filter((type: string) => !props.allowedFileTypes?.length || props.allowedFileTypes.includes(type)),
  } },
  get loading() { return displayStore.value.loading },
  get error() { return displayStore.value.error },
  loadPhotos: refreshFilters,
}))
const clearFilters = async () => {
  for (const values of Object.values(store.value.selectedFilters)) {
    if (Array.isArray(values)) values.splice(0)
  }
  await refreshFilters()
}
const clearSearch = () => {
  searchStore.resetAll()
  if (scrollContainer.value) scrollContainer.value.scrollTop = 0
  if (props.enableFilters) void store.value.loadPhotos(true)
}
const submitSearch = async (criteria: { query: string; type?: string }) => {
  if (props.busy) return
  if (scrollContainer.value) scrollContainer.value.scrollTop = 0
  showSearchDialog.value = false
  await searchStore.search(criteria.query, criteria.type || '', store.value.getPickerSearchFilters?.() ?? {})
}
const loadMore = () => displayStore.value.loadPhotos()
const retryLoad = () => searchStore.query ? searchStore.loadPhotos() : store.value.loadPhotos(true)

// UI State
const images = computed(() => displayStore.value.images)
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
const scrollContent = ref<HTMLElement | null>(null)
const header = ref<HTMLElement | null>(null)
const headerHeight = ref(0)
const scrolled = ref(false)
const mobile = useMediaQuery('(max-width: 767px)')
const glassHeader = computed(() => mobile.value && scrolled.value)
const confirmationLabel = computed(() => props.busy ? '保存中…' : props.singleSelect ? '使用此照片' : `确认选择 (${selectedIds.value.length})`)
const onGalleryScroll = (event: Event) => {
  scrolled.value = (event.currentTarget as HTMLElement).scrollTop > 0
}
useResizeObserver(header, () => { headerHeight.value = header.value?.offsetHeight ?? 0 })

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
  if (!props.busy) emit('select', selectedIds.value)
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
    if (props.enableFilters) {
      constrainMediaTypes()
      await store.value.fetchAvailableFilters()
    }
    await store.value.fetchTimelineStats()
    await store.value.loadPhotos(true)
  } finally {
    initialLoading.value = false
  }
})

onBeforeUnmount(() => {
  searchStore.resetAll()
  if (props.isSelector) {
    galleryRef.value?.exitSelectionMode()
    uiStore.setSelectionActive(false)
  }
})

onUnmounted(() => {
  if (props.isSelector) {
    store.value.resetAll()
  }
})
</script>

<style scoped>
.picker-header:not(.ts-liquid-glass) {
  color: var(--ts-color-text);
  background: var(--ts-color-surface);
  border: var(--ts-border-unit, 1px) solid transparent;
  border-bottom-color: var(--ts-color-divider);
}
.picker-header.ts-liquid-glass { position: sticky; --glass-tint: var(--ts-glass-control); }
.picker-scroll-container { scroll-padding-top: var(--photo-page-header-height); }
.picker-scroll-container::-webkit-scrollbar {
  width: 6px;
}
.picker-scroll-container::-webkit-scrollbar-track {
  background: transparent;
}
.picker-scroll-container::-webkit-scrollbar-thumb {
  background: rgba(156, 163, 175, 0.3);
  border-radius: 3px;
}
.picker-scroll-container::-webkit-scrollbar-thumb:hover {
  background: rgba(156, 163, 175, 0.5);
}
@media (max-width: 767px) {
  .picker-header--fullscreen { padding-top: var(--ts-safe-area-top); }
  .picker-scroll-container { scrollbar-width: none; }
  .picker-scroll-container::-webkit-scrollbar { display: none; }
  .picker-tool { min-width: 36px; width: auto; min-height: 36px; height: 36px; padding-inline: 5px; gap: 2px; }
  .picker-header--fullscreen .picker-confirm { min-height: 36px; }
}
@media (max-width: 359px) {
  .picker-header--fullscreen .picker-confirm { width: 36px; padding: 0; }
  .picker-header--fullscreen .picker-confirm > span { display: none; }
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


<style>
.photo-picker-search-dialog.responsive-dialog-panel .responsive-dialog-body,
.photo-picker-search-dialog.responsive-dialog-panel.mobile-fullscreen .responsive-dialog-body {
  display: flex;
  overflow: hidden;
  padding: 0;
}
@media (min-width: 768px) {
  .photo-picker-search-dialog.responsive-dialog-panel { height: 90dvh; }
}
</style>
