<template>
  <div class="photo-gallery min-h-screen relative" ref="galleryEl">
    <!-- Skeleton Loader (Initial Load) -->
    <GalleryChrome :loading="loading" :error="error" :photos="photos" @retry="$emit('retry')" />

    <PhotoBatchActionBar
      :visible="isSelectionMode && showActionBar" :selected-ids="localSelectedIds"
      :is-all-selected="isAllSelected" :is-downloading="isDownloading" :delete-label="deleteLabel"
      :album-context="store?.currentContext?.type === 'album'"
      @cancel="exitSelectionMode" @select-all="toggleSelectAll" @download="handleDownload"
      @delete="handleDelete" @person="openPersonSelector"
      @add-to-album="ids => $emit('add-to-album', ids)"
      @remove-from-album="ids => $emit('remove-from-album', ids)"
      @set-album-cover="ids => $emit('set-album-cover', ids)"
      @batch-edit-location="ids => $emit('batch-edit-location', ids)"
    >
      <template v-if="$slots['batch-actions']" #batch-actions="scope"><slot name="batch-actions" v-bind="scope" /></template>
    </PhotoBatchActionBar>

    <PersonSelector 
      v-model:visible="showPersonSelector"
      :submitting="isAddingPerson"
      @select="handlePersonSelected"
    />
    
    <!-- Virtual Scroll Container -->
    <div :style="{ height: totalHeight + 'px', position: 'relative' }">
        <div 
            class="grid w-full"
            :style="{
                gridTemplateColumns: `repeat(${colCount}, minmax(0, 1fr))`,
                gap: gap + 'px',
                transform: `translateY(${paddingTop}px)`
            }"
        >
            <div
                v-for="img in visiblePhotos"
                :key="img.id"
                class="relative group rounded-lg overflow-hidden cursor-pointer transform transition-all duration-300 hover:scale-[1.02] hover:shadow-lg hover:z-10 flex items-center justify-center aspect-square bg-gray-100 dark:bg-gray-800"
                :class="{
                  'shrink-animation grayscale opacity-70': pendingRemoveIds.has(img.id)
                }"
                @click="handlePhotoClick(img)"
                @vue:mounted="loadImage(img)"
                @vue:unmounted="cancelImageLoad(img.id)"
            >
                <img
                    :src="loadedImages[img.id] || placeholderSrc"
                    class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
                    :alt="img.filename"
                />
                
                <!-- Selection Checkbox (Top Left) -->
                <div
                    class="absolute top-2 left-2 z-30 transition-opacity duration-200 cursor-pointer"
                    :class="(isSelectionMode || localSelectedIds.has(img.id)) ? 'opacity-100 pointer-events-auto' : 'opacity-0 group-hover:opacity-100 pointer-events-none group-hover:pointer-events-auto'"
                    @click.stop="toggleSelection(img)"
                >
                    <div
                    class="w-6 h-6 rounded-full border-2 flex items-center justify-center transition-all duration-200 backdrop-blur-sm shadow-sm"
                    :class="localSelectedIds.has(img.id) ? 'bg-primary-500 border-primary-500' : 'bg-black/10 border-white/70 hover:bg-black/40'"
                    >
                    <Check v-if="localSelectedIds.has(img.id)" class="w-3.5 h-3.5 text-white" />
                    </div>
                </div>
                
                <!-- Selected Overlay (Darken) -->
                <div 
                    v-if="localSelectedIds.has(img.id)"
                    class="absolute inset-0 bg-black/10 z-10 pointer-events-none"
                ></div>
                <!-- Video Indicator -->
                <div v-if="img.file_type === 'video'" class="flex mb-1 absolute top-1 right-2 justify-center pointer-events-none z-10 items-center">
                  <div class="text-white text-sm">
                    {{ img.duration}}
                  </div>
                  <PlayCircle class="w-4 h-4 text-white drop-shadow-md opacity-90" />
                </div>
                <div v-else-if="img.file_type === 'live_photo'" class="flex mb-1 absolute top-2 right-2 justify-center pointer-events-none z-10 items-center">
                    <span class="icon-[tabler--live-photo] w-4 h-4 text-white drop-shadow-md opacity-90"></span>
                </div>
                <!-- Always Visible Overlay Actions Slot -->
                <div v-if="$slots['overlay-actions']" class="absolute top-2 right-2 z-10">
                  <slot name="overlay-actions" :photo="img"></slot>
                </div>
                <!-- Info Overlay -->
                <div class="absolute inset-x-0 bottom-0 p-2 bg-gradient-to-t from-black/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex justify-between items-end">
                    <p class="text-white text-xs font-medium truncate flex items-center gap-1">
                      <MapPin v-if="img.filename" class="w-3 h-3 text-white/80" />
                      {{ img.filename || formatTime(img.timestamp) }}
                    </p>
                </div>
                <!-- Bottom Left Overlay Slot -->
                <div v-if="$slots['bottom-left-overlay']" class="absolute bottom-1 left-1 z-10">
                  <slot name="bottom-left-overlay" :photo="img"></slot>
                </div>
            </div>
        </div>
    </div>

    <!-- Empty State -->
    <div v-if="totalHeight === 0 && !loading" class="flex flex-col items-center justify-center py-20 text-gray-400">
        <ImageIcon class="w-16 h-16 mb-4 opacity-20" />
        <p>暂无照片</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  ref, computed, watch, onMounted, onUnmounted, reactive
} from 'vue'
import { PlayCircle, Image as ImageIcon, MapPin, Check } from 'lucide-vue-next'
import { format } from 'date-fns'
import { usePhotoStore } from '@/stores/photoStore'
import type { AlbumImage } from '@/types/album'
import { useSelection } from '@/composables/useSelection'
import { useWindowScroll, useScroll } from '@vueuse/core'
import PersonSelector from './PersonSelector.vue'
import PhotoBatchActionBar from './PhotoBatchActionBar.vue'
import { usePhotoBatchActions } from '@/composables/usePhotoBatchActions'
import GalleryChrome from './GalleryChrome.vue'

// Props
interface Props {
  photos: AlbumImage[]
  loading?: boolean
  viewSize?: 'sm' | 'md' | 'lg'
  deleteLabel?: string
  pendingRemoveIds?: Set<string>
  error?: string | null
  store?: any
  scrollContainer?: HTMLElement | null,
  showActionBar?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  viewSize: 'md',
  deleteLabel: '删除',
  loading: false,
  pendingRemoveIds: () => new Set(),
  error: null,
  showActionBar: true
})

const emit = defineEmits(['click-photo', 'batch-delete', 'add-to-album', 'remove-from-album', 'set-album-cover', 'retry', 'selection-change', 'batch-edit-location'])

// --- Selection State ---
const { 
  isSelectionMode, 
  selectedIds: localSelectedIds, 
  enterSelectionMode, 
  exitSelectionMode, 
  toggleSelect: toggleSelectionId,
  selectAll: selectAllIds,
  isSelected
} = useSelection()

// Sync selection with parent if needed
watch(() => localSelectedIds.size, () => {
  emit('selection-change', Array.from(localSelectedIds))
})


const photoStore = usePhotoStore()
const store = computed(() => props.store || photoStore)

// --- Image Loading Logic ---
const loadedImages = reactive<Record<string, string>>({})
const placeholderSrc = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'

const loadImage = (image: AlbumImage) => {
    loadedImages[image.id] = image.thumbnail
}

const cancelImageLoad = (imageId: string) => {
    delete loadedImages[imageId]
}

onUnmounted(() => {
    window.removeEventListener('resize', handleResize)
    if (resizeObserver) resizeObserver.disconnect()
})

// --- Virtual Scroll & Layout ---
const galleryEl = ref<HTMLElement | null>(null)
const containerWidth = ref(1000)

const scrollContainerRef = ref<HTMLElement | Window | null>(null)
const { y: containerScrollTop } = useScroll(scrollContainerRef)

const scrollTop = computed(() => containerScrollTop.value)

const viewportHeight = ref(window.innerHeight)

const handleResize = () => {
  const container = scrollContainerRef.value
  if (container && container !== window) {
    viewportHeight.value = (container as HTMLElement).clientHeight
  } else {
    viewportHeight.value = window.innerHeight
  }
}

watch(scrollContainerRef, (container) => {
  if (container && container !== window) {
    viewportHeight.value = (container as HTMLElement).clientHeight
    const ro = new ResizeObserver(handleResize)
    ro.observe(container as HTMLElement)
  } else {
    viewportHeight.value = window.innerHeight
  }
}, { immediate: true })

// 父级可能传入一个挂载后才就绪的内部滚动容器（如 FolderBrowser 的 scrollArea），
// 此时 onMounted 里拿到的还是 null，这里在 prop 真正就绪后再切换过去。
watch(() => props.scrollContainer, (c) => {
  if (c) scrollContainerRef.value = c
})

let resizeObserver: ResizeObserver | null = null
onMounted(() => {
    if (props.scrollContainer) {
      scrollContainerRef.value = props.scrollContainer
    } else {
      const mainEl = document.querySelector('main')
      if (mainEl && window.getComputedStyle(mainEl).overflowY === 'auto') {
        scrollContainerRef.value = mainEl
      } else {
        scrollContainerRef.value = window
      }
    }

    window.addEventListener('resize', handleResize)
    if (galleryEl.value) {
        containerWidth.value = galleryEl.value.clientWidth
        resizeObserver = new ResizeObserver((entries) => {
            const entry = entries[0]
            if (entry) {
                containerWidth.value = entry.contentRect.width
            }
        })
        resizeObserver.observe(galleryEl.value)
    }
    handleResize()
})

// Layout Calculations
const gap = computed(() => {
    if (props.viewSize === 'sm') return 2
    if (props.viewSize === 'lg') return 16
    return 4 // md default
})

const colCount = computed(() => {
    const w = containerWidth.value
    if (props.viewSize === 'sm') return w < 640 ? 4 : (w < 768 ? 6 : (w < 1024 ? 8 : 12))
    if (props.viewSize === 'lg') return w < 640 ? 2 : (w < 768 ? 3 : (w < 1024 ? 4 : 6))
    return w < 640 ? 3 : (w < 768 ? 4 : (w < 1024 ? 5 : 8)) // Adjusted md
})

const itemSize = computed(() => {
    const c = colCount.value
    const g = gap.value
    const w = containerWidth.value
    // width = (containerWidth - (cols - 1) * gap) / cols
    return (w - (c - 1) * g) / c
})

const totalRows = computed(() => Math.ceil(props.photos.length / colCount.value))
const totalHeight = computed(() => totalRows.value * (itemSize.value + gap.value))

// Virtual Scroll Logic
const buffer = 1000 // Buffer px
const visibleRange = computed(() => {
    const rowHeight = itemSize.value + gap.value
    if (rowHeight <= 0) return { start: 0, end: 0, paddingTop: 0 }
    
    const startRow = Math.floor(Math.max(0, scrollTop.value - buffer) / rowHeight)
    const endRow = Math.ceil((scrollTop.value + viewportHeight.value + buffer) / rowHeight)
    
    // Clamp to actual rows
    const actualStartRow = Math.min(startRow, totalRows.value)
    const actualEndRow = Math.min(endRow, totalRows.value)

    const startIndex = actualStartRow * colCount.value
    const endIndex = actualEndRow * colCount.value
    
    return {
        start: startIndex,
        end: endIndex,
        paddingTop: actualStartRow * rowHeight
    }
})

const visiblePhotos = computed(() => {
    const { start, end } = visibleRange.value
    if (end <= start) return []
    return props.photos.slice(start, end)
})

const paddingTop = computed(() => visibleRange.value.paddingTop)

// --- Interaction Helpers ---
const formatTime = (ts: number) => format(new Date(ts), 'yyyy-MM-dd HH:mm')

const toggleSelection = (photo: AlbumImage) => {
  toggleSelectionId(photo.id)
  if (localSelectedIds.size > 0) {
      if (!isSelectionMode.value) enterSelectionMode()
  }
}

const { isDownloading, isAddingPerson, showPersonSelector, openPersonSelector, handlePersonSelected, handleDownload } = usePhotoBatchActions({
  selectedIds: () => localSelectedIds,
  photos: () => props.photos,
  clearSelection: () => exitSelectionMode(),
  exitAfterDownload: false,
})

const handlePhotoClick = (photo: AlbumImage) => {
  if (isSelectionMode.value) {
    toggleSelection(photo)
  } else {
    emit('click-photo', photo)
  }
}

const isAllSelected = computed(() => {
    return props.photos.length > 0 && props.photos.every(p => localSelectedIds.has(p.id))
})

const toggleSelectAll = () => {
    if (isAllSelected.value) {
        exitSelectionMode()
    } else {
        const ids = props.photos.map(p => p.id)
        selectAllIds(ids)
        enterSelectionMode()
    }
}

const handleDelete = () => {
    if (localSelectedIds.size === 0) return
    
    const ids = Array.from(localSelectedIds)
    if (props.deleteLabel.includes('移除')) {
        emit('remove-from-album', ids)
    } else {
        emit('batch-delete', ids)
    }
}

defineExpose({
    enterSelectionMode,
    exitSelectionMode,
    selectAll: selectAllIds,
    selectedIds: localSelectedIds,
    isSelectionMode
})
</script>

<style scoped>
.scrollbar-hide::-webkit-scrollbar {
    display: none;
}
.scrollbar-hide {
    -ms-overflow-style: none;
    scrollbar-width: none;
}
</style>
