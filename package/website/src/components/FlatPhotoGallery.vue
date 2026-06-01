<template>
  <div class="photo-gallery min-h-screen relative" ref="galleryEl">
    <!-- Skeleton Loader (Initial Load) -->
    <div v-if="loading && photos.length === 0" class="absolute inset-0 z-10 bg-white dark:bg-gray-950 p-4">
        <div class="grid grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
            <div v-for="i in 20" :key="i" class="aspect-[3/2] bg-gray-200 dark:bg-gray-800 rounded-lg animate-pulse"></div>
        </div>
    </div>

    <!-- Error State -->
    <div v-if="error" class="absolute inset-0 z-10 flex flex-col items-center justify-center bg-white dark:bg-gray-950">
        <div class="text-center space-y-4">
            <p class="text-red-500 font-medium">{{ error }}</p>
            <button 
                @click="$emit('retry')"
                class="flex items-center gap-2 px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors group relative overflow-hidden"
            >
                <div class="absolute inset-0 rounded-lg animate-[pulse_2s_cubic-bezier(0.4,0,0.6,1)_infinite] bg-white/20"></div>
                <RefreshCcw class="w-4 h-4 group-hover:animate-[spin_1s_ease-in-out]" />
                <span class="relative z-10">重试</span>
            </button>
        </div>
    </div>

    <!-- Batch Action Bar -->
    <transition
      enter-active-class="transition duration-300 ease-out"
      enter-from-class="transform -translate-y-full opacity-0"
      enter-to-class="transform translate-y-0 opacity-100"
      leave-active-class="transition duration-200 ease-in"
      leave-from-class="transform translate-y-0 opacity-100"
      leave-to-class="transform -translate-y-full opacity-0"
    >
      <div v-if="isSelectionMode && showActionBar" class="fixed bottom-[20px] left-0 right-0 z-40 flex justify-center pointer-events-none px-4">
        <div class="bg-white/90 dark:bg-gray-900/90 backdrop-blur-md border border-gray-200 dark:border-gray-700 shadow-lg rounded-full px-3 py-1 md:py-1 flex items-center gap-2 sm:gap-6 pointer-events-auto min-w-fit max-w-full overflow-x-auto scrollbar-hide">
          <div class="flex items-center gap-1 md:gap-3 flex-shrink-0">
            <button @click="exitSelectionMode" class="p-1.5 sm:p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full transition-colors dark:text-gray-300 bg-transparent" title="取消选择">
              <X class="w-5 h-5 text-gray-600 dark:text-gray-300" />
            </button>
            <span class="font-medium text-gray-900 dark:text-white whitespace-nowrap text-sm sm:text-base">
              <span class="sm:hidden">{{ localSelectedIds.size }}</span>
              <span class="hidden sm:inline">已选 {{ localSelectedIds.size }} 项</span>
            </span>
          </div>

          <div class="h-6 w-px bg-gray-300 dark:bg-gray-600 flex-shrink-0"></div>

          <div class="flex items-center gap-1 sm:gap-2 flex-nowrap">
            <button @click="toggleSelectAll" class="p-2 sm:px-3 sm:py-1.5 text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors bg-transparent" :title="isAllSelected ? '取消全选' : '全选'">
              <span class="hidden sm:inline">{{ isAllSelected ? '取消全选' : '全选' }}</span>
              <CheckSquare class="w-5 h-5 sm:hidden" />
            </button>
            
            <button
                @click="$emit('add-to-album', Array.from(localSelectedIds))"
                :disabled="localSelectedIds.size === 0"
                class="bg-transparent flex items-center gap-2 p-2 sm:px-4 sm:py-2 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium"
                title="添加到相册"
                >
                <ImagePlusIcon class="w-5 h-5" />
            </button>

            <!-- Download Action -->
            <button
              @click="handleDownload"
              :disabled="localSelectedIds.size === 0 || isDownloading"
              class="bg-transparent p-2 text-primary-600 hover:bg-primary-50 dark:hover:bg-primary-900/20 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed relative group"
              title="保存到本地"
            >
              <Loader2 v-if="isDownloading" class="w-5 h-5 animate-spin" />
              <Download v-else class="w-5 h-5" />
              <!-- Progress Tooltip -->
              <div v-if="isDownloading" class="absolute -bottom-8 left-1/2 -translate-x-1/2 bg-black/80 text-white text-xs px-2 py-1 rounded whitespace-nowrap">
                {{ downloadProgress }}%
              </div>
            </button>

            <!-- Delete/Remove Action -->
            <button 
              @click="handleDelete" 
              :disabled="localSelectedIds.size === 0"
              class="bg-transparent p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              :title="deleteLabel"
            >
              <Trash2 class="w-5 h-5" />
            </button>

            <!-- More Actions -->
            <el-dropdown trigger="click" placement="top-end">
              <button class="bg-transparent p-2 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors">
                <MoreHorizontal class="w-5 h-5" />
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item @click="openPersonSelector">
                    <div class="flex items-center gap-2">
                      <UserPlus class="w-4 h-4" />
                      <span>添加到人物</span>
                    </div>
                  </el-dropdown-item>

                  <el-dropdown-item 
                    v-if="store.currentContext.type === 'album'"
                    :disabled="localSelectedIds.size === 0"
                    @click="$emit('remove-from-album', Array.from(localSelectedIds))"
                  >
                     <div class="flex items-center gap-2">
                        <ImageMinusIcon class="w-4 h-4" />
                        <span>移出相册</span>
                     </div>
                  </el-dropdown-item>

                  <el-dropdown-item 
                    v-if="store.currentContext.type === 'album' && localSelectedIds.size===1"
                    @click="$emit('set-album-cover', Array.from(localSelectedIds))"
                  >
                     <div class="flex items-center gap-2">
                        <ImageIcon class="w-4 h-4" />
                        <span>设为封面</span>
                     </div>
                  </el-dropdown-item>

                  <div class="border-t border-gray-100 dark:border-gray-800 my-1 mx-2" v-if="$slots['batch-actions']"></div>
                  <slot name="batch-actions" :selected-ids="localSelectedIds" :clear-selection="exitSelectionMode"></slot>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </div>
    </transition>

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
import { ElMessage } from 'element-plus'
import { PlayCircle, Image as ImageIcon, MapPin, Check, X, Download, Trash2, Loader2, ImageMinusIcon, ImagePlusIcon, RefreshCcw, MoreHorizontal, UserPlus, CheckSquare } from 'lucide-vue-next'
import { format } from 'date-fns'
import { usePhotoStore } from '@/stores/photoStore'
import type { AlbumImage } from '@/types/album'
import { useSelection } from '@/composables/useSelection'
import { useWindowScroll, useScroll } from '@vueuse/core'
import PersonSelector from './PersonSelector.vue'
import { faceApi } from '@/api/face'

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

const emit = defineEmits(['click-photo', 'batch-delete', 'add-to-album', 'remove-from-album', 'set-album-cover', 'retry', 'selection-change'])

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

const isDownloading = ref(false)
const downloadProgress = ref(0)
const isAddingPerson = ref(false)

const photoStore = usePhotoStore()
const store = computed(() => props.store || photoStore)

// --- Image Loading Logic ---
const loadedImages = reactive<Record<string, string>>({})
const imageLoaders = new Map<string, AbortController>()
const placeholderSrc = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'
const requestCache = new Map<string, Request>();

const loadImage = async (image: AlbumImage) => {
    if (loadedImages[image.id]) return;
    if (imageLoaders.has(image.id)) return;

    let request = requestCache.get(image.id);
    if (!request) {
        request = new Request(image.thumbnail, {
            method: 'GET',
            headers: {
                'Connection': 'keep-alive'
            }
        });
        requestCache.set(image.id, request);
    }

    const controller = new AbortController();
    imageLoaders.set(image.id, controller);

    try {
      const response = await fetch(request, { signal: controller.signal });
      if (response.ok) {
          loadedImages[image.id] = image.thumbnail;
      }
    } catch (e: any) {
        if (e.name !== 'AbortError') {
            console.error('Image load failed', e);
        }
    } finally {
        imageLoaders.delete(image.id);
    }
};

const cancelImageLoad = (imageId: string) => {
    const controller = imageLoaders.get(imageId)
    if (controller) {
        controller.abort()
        imageLoaders.delete(imageId)
    }
}

onUnmounted(() => {
    window.removeEventListener('resize', handleResize)
    imageLoaders.forEach(c => c.abort())
    imageLoaders.clear()
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

const handlePersonSelected = async (person: any) => {
  if (localSelectedIds.size === 0) return
  
  isAddingPerson.value = true
  try {
    const ids = Array.from(localSelectedIds)
    const res = await faceApi.addPhotosToIdentity(person.id, ids)
    ElMessage.success(`成功添加 ${res.count} 张照片到 ${person.identity_name}`)
    showPersonSelector.value = false
    exitSelectionMode()
  } catch (e: any) {
    console.error(e)
    ElMessage.error('添加失败')
  } finally {
    isAddingPerson.value = false
  }
}

const showPersonSelector = ref(false)

const openPersonSelector = () => {
  showPersonSelector.value = true
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

const handleDownload = async () => {
  if (localSelectedIds.size === 0) return
  isDownloading.value = true
  downloadProgress.value = 0
  
  const total = localSelectedIds.size
  let completed = 0
  
  for (const id of localSelectedIds) {
    try {
      const photo = props.photos.find(p => p.id === id)
      if (!photo) continue

      const response = await fetch(photo.url)
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      
      const a = document.createElement('a')
      a.href = url
      a.download = photo.filename || `photo-${photo.id}.jpg`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
      
      completed++
      downloadProgress.value = Math.round((completed / total) * 100)
    } catch (e) {
      console.error('Download failed', e)
    }
  }
  
  isDownloading.value = false
  downloadProgress.value = 0
}

defineExpose({
    enterSelectionMode,
    exitSelectionMode
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