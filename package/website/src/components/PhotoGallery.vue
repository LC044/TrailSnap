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
                    :disabled="localSelectedIds.size === 0"
                    @click="$emit('transfer', 'move', Array.from(localSelectedIds))"
                  >
                     <div class="flex items-center gap-2">
                        <FolderOutput class="w-4 h-4" />
                        <span>移动到目录</span>
                     </div>
                  </el-dropdown-item>
                  
                  <el-dropdown-item 
                    :disabled="localSelectedIds.size === 0"
                    @click="$emit('transfer', 'copy', Array.from(localSelectedIds))"
                  >
                     <div class="flex items-center gap-2">
                        <Copy class="w-4 h-4" />
                        <span>复制到目录</span>
                     </div>
                  </el-dropdown-item>

                  <el-dropdown-item 
                    v-if="store?.currentContext?.type === 'album'"
                    :disabled="localSelectedIds.size === 0"
                    @click="$emit('remove-from-album', Array.from(localSelectedIds))"
                  >
                     <div class="flex items-center gap-2">
                        <ImageMinusIcon class="w-4 h-4" />
                        <span>移出相册</span>
                     </div>
                  </el-dropdown-item>

                  <el-dropdown-item 
                    v-if="store?.currentContext?.type === 'album' && localSelectedIds.size===1"
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
        v-for="block in monthBlocks"
        :key="block.key"
        :style="{ 
          position: 'absolute', 
          top: block.top + 'px', 
          left: 0, 
          width: '100%',
          height: block.height + 'px'
        }"
        class="month-block px-4"
        :data-month="block.key"
      >
        <!-- Render month content only if visible -->
        <template v-if="visibleBlockKeys.has(block.key)">
            <!-- Days Container -->
            <div
                v-for="day in block.days"
                :key="day.key"
                :style="{
                    position: 'absolute',
                    top: day.top + 'px',
                    left: 0,
                    width: '100%',
                    height: day.height + 'px'
                }"
                class="day-block"
            >
                <template v-if="visibleDayRanges.has(day.key)">
                     <!-- Day Header -->
                    <div class="h-[50px] flex items-center mb-0 sticky top-[20px] z-20 py-2 transition-opacity duration-300 pointer-events-none">
                        <div class="flex items-center gap-3 group cursor-pointer text-sm font-bold text-gray-800 dark:text-gray-200 bg-white/90 dark:bg-gray-900/90 backdrop-blur-sm px-4 py-1.5 rounded-full shadow-sm border border-gray-100 dark:border-gray-800 flex items-center gap-2 pointer-events-auto cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800" @click="toggleDaySelection(day)">
                             <div 
                                class="w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all duration-200"
                                :class="isDaySelected(day) ? 'bg-primary-500 border-primary-500' : 'border-gray-300 dark:border-gray-600 group-hover:border-primary-400'"
                             >
                                <Check v-if="isDaySelected(day)" class="w-3 h-3 text-white" />
                             </div>
                             <span class="">
                                {{ day.year }}-{{ String(day.month).padStart(2, '0') }}-{{ String(day.day).padStart(2, '0') }}
                             </span>
                            <CalendarDays class="w-4 h-4 text-primary-500" />
                        </div>
                    </div>

                    <!-- Photos Grid -->
                    <div 
                        :class="layoutMode === 'waterfall' ? 'flex flex-wrap' : 'grid w-full'" 
                        :style="layoutMode === 'waterfall' ? { gap: gap + 'px' } : {
                            gridTemplateColumns: `repeat(${colCount}, minmax(0, 1fr))`,
                            gap: gap + 'px'
                        }"
                    >
                        <!-- Top Spacer -->
                        <div v-if="getRange(day.key).topH > 0" 
                             :style="layoutMode === 'waterfall' ? { width: '100%', height: getRange(day.key).topH + 'px' } : { gridColumn: '1 / -1', height: getRange(day.key).topH + 'px' }">
                        </div>

                        <!-- Actual Photos -->
                        <template v-if="getPhotos(day.key).length > 0">
                            <div
                                v-for="img in getPhotos(day.key).slice(getRange(day.key).start, getRange(day.key).end)"
                                :key="img.id"
                                class="relative group rounded-lg overflow-hidden cursor-pointer transform transition-all duration-300 hover:scale-[1.02] hover:shadow-lg hover:z-10 flex items-center justify-center"
                                :class="{
                                  'aspect-square bg-gray-100 dark:bg-gray-800': layoutMode === 'grid',
                                  'aspect-[3/2] bg-gray-100 dark:bg-gray-800': layoutMode === 'masonry',
                                  'flex-grow bg-gray-100 dark:bg-gray-800': layoutMode === 'waterfall',
                                  'shrink-animation grayscale opacity-70': pendingRemoveIds.has(img.id)
                                }"
                                :style="layoutMode === 'waterfall' ? {
                                    height: rowHeight + 'px',
                                    width: (img.width && img.height ? (img.width / img.height * rowHeight) : (rowHeight * 1.5)) + 'px',
                                    minWidth: '50px',maxWidth: '400px'
                                } : {}"
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
                                <!-- Video Indicator (List View) -->
                                <div v-if="img.file_type === 'video'" class="flex mb-1 absolute top-1 right-2 justify-center pointer-events-none z-10 items-center">
                                  <div class="text-white text-sm">
                                    {{ img.duration}}
                                  </div>
                                  <PlayCircle class="w-4 h-4 text-white drop-shadow-md opacity-90" />
                                </div>
                                <div v-else-if="img.file_type === 'live_photo'" class="flex mb-1 absolute top-2 right-2 justify-center pointer-events-none z-10 items-center">
                                    <span class="icon-[tabler--live-photo] w-4 h-4 text-white drop-shadow-md opacity-90"></span>
                                </div>
                                <!-- Info Overlay -->
                                <div class="absolute inset-x-0 bottom-0 p-2 bg-gradient-to-t from-black/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex justify-between items-end">
                                    <p class="text-white text-xs font-medium truncate flex items-center gap-1">
                                      <MapPin v-if="img.filename" class="w-3 h-3 text-white/80" />
                                      {{ img.filename || formatTime(img.timestamp) }}
                                    </p>
                                    <slot name="overlay-actions" :photo="img"></slot>
                                </div>
                            </div>
                        </template>

                        <!-- Placeholders for missing photos -->
                         <template v-else>
                             <div
                                v-for="n in (getRange(day.key).end - getRange(day.key).start)"
                                :key="`ph-${day.key}-${getRange(day.key).start + n}`"
                                class="aspect-[3/2] bg-gray-50 dark:bg-gray-900/50 rounded-lg animate-pulse"
                            ></div>
                         </template>
                         
                         <!-- Bottom Spacer -->
                        <div v-if="getRange(day.key).bottomH > 0" 
                             :style="{ gridColumn: '1 / -1', height: getRange(day.key).bottomH + 'px' }">
                        </div>
                    </div>
                </template>
            </div>
        </template>
        <template v-else>
            <!-- Invisible Placeholder -->
             <div class="w-full h-full bg-gray-50/50 dark:bg-gray-900/20 rounded-lg border border-transparent"></div>
        </template>
      </div>
    </div>

    <!-- Empty State -->
    <div v-if="totalHeight === 0 && !loading" class="flex flex-col items-center justify-center py-20 text-gray-400">
        <slot name="empty">
          <ImageIcon class="w-16 h-16 mb-4 opacity-20" />
          <p>暂无照片</p>
        </slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  ref, computed, watch, onMounted, onUnmounted, nextTick, toRef, reactive
} from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { CalendarDays, PlayCircle, Image as ImageIcon, MapPin, Check, X, Download, Trash2, FolderMinus, Loader2, PlaySquare, Play, PlayIcon, PlayCircleIcon, Plus, FolderPlus, PhoneOutgoingIcon, PictureInPicture, CloverIcon, ImageMinusIcon, ImagePlusIcon, RefreshCcw, Aperture, MoreHorizontal, UserPlus, CheckSquare, FolderOutput, Copy } from 'lucide-vue-next'
import { format } from 'date-fns'
import { useAlbumStore } from '@/stores/albumStore'
import { usePhotoStore } from '@/stores/photoStore'
import type { TimelineStats, AlbumImage } from '@/types/album'
import { useVirtualLayout, type MonthBlock, type DayBlock } from '@/composables/useVirtualLayout'
import { useSelection } from '@/composables/useSelection'
import { useWindowScroll, useScroll, useDebounceFn } from '@vueuse/core'
import PersonSelector from './PersonSelector.vue'
import { faceApi } from '@/api/face'

// Props
interface Props {
  photos: AlbumImage[]
  timelineStats?: TimelineStats
  loading?: boolean
  hasMore?: boolean
  layoutMode?: 'grid' | 'masonry' | 'waterfall' | 'list'
  viewSize?: 'sm' | 'md' | 'lg'
  groupByDate?: boolean
  deleteLabel?: string
  activeDate?: string // v-model
  pendingRemoveIds?: Set<string>
  error?: string | null
  store?: any
  scrollContainer?: HTMLElement | null,
  showActionBar?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  layoutMode: 'masonry',
  viewSize: 'md',
  groupByDate: true,
  deleteLabel: '删除',
  loading: false,
  hasMore: false,
  pendingRemoveIds: () => new Set(),
  error: null,
  showActionBar: true
})

const emit = defineEmits(['click-photo', 'load-more', 'load-range', 'update:activeDate', 'batch-delete', 'add-to-album', 'remove-from-album', 'set-album-cover', 'retry', 'selection-change', 'transfer'])

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
// 缓存Request对象，避免重复创建导致连接重建
const requestCache = new Map<string, Request>();

const loadImage = async (image: AlbumImage) => {
    if (loadedImages[image.id]) return;
    if (imageLoaders.has(image.id)) return;

    // 复用Request对象
    let request = requestCache.get(image.id);
    if (!request) {
        request = new Request(image.thumbnail, {
            method: 'GET',
            headers: {
                'Connection': 'keep-alive'  // 显式要求keep-alive
            }
        });
        requestCache.set(image.id, request);
    }

    const controller = new AbortController();
    imageLoaders.set(image.id, controller);

    try {
      // loadedImages[image.id] = image.thumbnail;
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

// Ensure cleanup on component unmount
onUnmounted(() => {
    window.removeEventListener('resize', handleResize)
    imageLoaders.forEach(c => c.abort())
    imageLoaders.clear()
    if (resizeObserver) resizeObserver.disconnect()
})
// --- End Image Loading Logic ---

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
  updateVisibleBlocks()
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

const layoutOptions = {
    timelineStats: toRef(props, 'timelineStats'),
    containerWidth,
    layoutMode: toRef(props, 'layoutMode'),
    viewSize: toRef(props, 'viewSize'),
    photos: toRef(props, 'photos')
}

const { monthBlocks, totalHeight, getVisibleBlocks, recalculateLayout, colCount, rowHeight, gap } = useVirtualLayout(layoutOptions)

// Visible Blocks Calculation
const visibleBlockKeys = ref(new Set<string>())
// Map<dayKey, { start: number, end: number, topH: number, bottomH: number }>
const visibleDayRanges = ref(new Map<string, { start: number, end: number, topH: number, bottomH: number }>())
// We keep a reference to visible blocks for active date calculation
const visibleBlocksList = ref<MonthBlock[]>([])

const DAY_HEADER_HEIGHT = 40

const getRange = (key: string) => {
  return visibleDayRanges.value.get(key) || { start: 0, end: 0, topH: 0, bottomH: 0 }
}

const updateVisibleBlocks = () => {
    const buffer = 1000 // Month Buffer
    const visibleMonths = getVisibleBlocks(scrollTop.value, viewportHeight.value, buffer)
    visibleBlocksList.value = visibleMonths

    const newMonthKeys = new Set<string>()
    const newDayRanges = new Map<string, { start: number, end: number, topH: number, bottomH: number }>()

    // Dynamic Buffer for Rows: (hn + 2 + 2) * wn -> 2 rows buffer
    // But here we calculate based on pixels
    const rHeight = rowHeight.value || 200
    const rGap = gap.value || 0
    const rowUnit = rHeight + rGap
    const rowBuffer = rowUnit * 2 
    
    const startY = scrollTop.value - rowBuffer
    const endY = scrollTop.value + viewportHeight.value + rowBuffer

    visibleMonths.forEach(m => {
        newMonthKeys.add(m.key)
        
        // Check Days visibility
        m.days.forEach(d => {
            // Calculate absolute top of the day block
            const dayTopAbs = m.top + d.top
            const dayBottomAbs = dayTopAbs + d.height
            
            // Check if day is within buffer
            if (dayBottomAbs > startY && dayTopAbs < endY) {
                // Calculate visible rows within the day
                // The photos start after the header
                const photosTopAbs = dayTopAbs + DAY_HEADER_HEIGHT
                
                // Relative to photos start
                const relStart = startY - photosTopAbs
                const relEnd = endY - photosTopAbs
                
                if (props.layoutMode === 'waterfall') {
                     // In waterfall mode, disable row virtualization within day for simplicity
                     newDayRanges.set(d.key, { start: 0, end: d.count, topH: 0, bottomH: 0 })
                } else {
                    let startRow = Math.floor(relStart / rowUnit)
                    let endRow = Math.ceil(relEnd / rowUnit)
                    
                    // Clamp rows
                    startRow = Math.max(0, startRow)
                    endRow = Math.min(d.rows, endRow) // d.rows is total rows in day
                    
                    if (startRow < d.rows && endRow > 0) {
                         const startIndex = startRow * colCount.value
                         const endIndex = Math.min(d.count, endRow * colCount.value)
                         
                         const topH = startRow * rowUnit
                         const bottomH = Math.max(0, d.rows - endRow) * rowUnit
                         
                         newDayRanges.set(d.key, { start: startIndex, end: endIndex, topH, bottomH })
                    }
                }
            }
        })
    })

    visibleBlockKeys.value = newMonthKeys
    visibleDayRanges.value = newDayRanges
}

// Throttle scroll updates
const handleScroll = useDebounceFn(() => {
    updateVisibleBlocks()
    // Update active date based on first visible block
    if (visibleBlocksList.value.length > 0) {
        const center = scrollTop.value + viewportHeight.value / 2
        const current = visibleBlocksList.value.find(b => {
             return (b.top <= center) && (b.top + b.height >= center)
        }) || visibleBlocksList.value[0]
        const dateStr = `${current.year}年${String(current.month).padStart(2, '0')}月`
        if (props.activeDate !== dateStr) {
            emit('update:activeDate', dateStr)
        }
    }
}, 50, { maxWait: 100 }) // More aggressive update for row virtualization

watch(scrollTop, handleScroll)

// Watch for layout changes to update visibility immediately
watch(monthBlocks, () => {
    updateVisibleBlocks()
    checkAndLoadVisibleMonths()
}, { deep: true })

// Resize Observer for Container Width
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
                recalculateLayout()
                updateVisibleBlocks()
            }
        })
        resizeObserver.observe(galleryEl.value)
    }
    updateVisibleBlocks()
    setTimeout(() => {
      updateVisibleBlocks()
    }, 1000);
})

// --- Data Fetching Logic ---
const checkAndLoadVisibleMonths = (refresh = false) => {
    const context = store.value.currentContext
    const albumId = context.type === 'album' ? context.id : undefined
    visibleBlocksList.value.forEach(block => {
        const key = `${block.year}-${block.month}`
        // Check if we have photos for this month
        // store uses "YYYY-MM" format in loadPhotosByMonth
        // Note: hasPhotos(key) checks props.photos. 
        if (!hasPhotosForMonth(key) || refresh) {
             store.value.loadPhotosByMonth(block.year, block.month, albumId, refresh)
        }
    })
}

watch(visibleBlockKeys, () => {
    checkAndLoadVisibleMonths()
}, { deep: true, immediate: true })


// --- Photo Grouping ---
const groupedPhotos = computed(() => {
    const map = new Map<string, AlbumImage[]>()
    
    // Check if we are in dummy mode (no timeline stats)
    // If no timeline stats provided, we assume flat list mode
    // We check if monthBlocks has 'all' key (which comes from useVirtualLayout handling)
    // But monthBlocks is derived from useVirtualLayout.
    // A simpler check is if timelineStats prop is missing/empty
    if (!props.timelineStats?.timeline) {
         // Create a single group with key 'all'
         // We must filter out invalid dates if needed, but for 'all' we take everything
         map.set('all', props.photos)
         return map
    }

    // Group by Day Key: YYYY-MM-DD
    props.photos.forEach(p => {
        const d = new Date(p.timestamp)
        const dayKey = `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`
        if (!map.has(dayKey)) map.set(dayKey, [])
        map.get(dayKey)!.push(p)
    })
    return map
})

const hasPhotosForMonth = (monthKey: string) => {
    // If flat mode, we don't load by month
    if (!props.timelineStats?.timeline) return true
    
    const block = monthBlocks.value.find(b => b.key === monthKey)
    if (!block || block.count === 0) return true // No need to load
    // Check if we have at least one photo for this month
    return props.photos.some(p => {
        const d = new Date(p.timestamp)
        return `${d.getFullYear()}-${d.getMonth() + 1}` === monthKey
    })
}

const getPhotos = (dayKey: string) => {
    return groupedPhotos.value.get(dayKey) || []
}

// --- Interaction Helpers ---
const scrollToDate = (date: string) => {
    // date format "YYYY年MM月" or "YYYY-MM-DD"
    const match = date.match(/(\d+)年(\d+)月/) || date.match(/(\d+)-(\d+)/)
    if (match) {
        const year = parseInt(match[1])
        const month = parseInt(match[2])
        const block = monthBlocks.value.find(b => b.year === year && b.month === month)
        if (block) {
            const container = scrollContainerRef.value
            if (container && container !== window) {
                (container as HTMLElement).scrollTo({ top: block.top + 60, behavior: 'smooth' })
            } else {
                window.scrollTo({ top: block.top + 60, behavior: 'smooth' })
            }
        }
    }
}

const formatTime = (ts: number) => format(new Date(ts), 'yyyy-MM-dd HH:mm')

// Selection Helpers


/*
const enterSelectionMode = (photo?: AlbumImage) => {
  // if (photo) localSelectedIds.value.add(photo.id) // Hover doesn't select automatically usually
  // But legacy code did. Let's keep manual selection.
  isSelectionMode.value = true
}
*/

/*
const exitSelectionMode = () => {
  isSelectionMode.value = false
  localSelectedIds.clear()
  emit('selection-change', [])
}
*/

const toggleSelection = (photo: AlbumImage) => {
  toggleSelectionId(photo.id)
  if (localSelectedIds.size > 0) {
      if (!isSelectionMode.value) enterSelectionMode()
  } else {
      // exitSelectionMode() // Don't auto exit usually
  }
}

const isDaySelected = (day: DayBlock) => {
    const photos = getPhotos(day.key)
    if (photos.length === 0) return false
    return photos.every(p => localSelectedIds.has(p.id))
}

const toggleDaySelection = (day: DayBlock) => {
    const photos = getPhotos(day.key)
    if (photos.length === 0) return

    const allSelected = isDaySelected(day)
    const ids = photos.map(p => p.id)
    
    if (allSelected) {
        ids.forEach(id => localSelectedIds.delete(id))
        if (localSelectedIds.size === 0) exitSelectionMode()
    } else {
        ids.forEach(id => localSelectedIds.add(id))
        enterSelectionMode()
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
      // Extract filename or default
      a.download = `${photo.filename}` || `${photo.id}.jpg`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)

      completed++
      downloadProgress.value = Math.round((completed / total) * 100)
      console.log(`Downloaded ${completed}/${total} (${downloadProgress.value}%) ${photo.filename || photo.id}`)
      // Small delay to ensure browser registers the download
      await new Promise(resolve => setTimeout(resolve, 200))
    } catch (error) {
      console.error('Failed to download photo:', error)
    }
  }
  
  isDownloading.value = false
  // Notification could be handled here or by parent. Component-level simple alert or toast integration if available.
  // For now, just reset.
  exitSelectionMode()
}

defineExpose({
  scrollToDate,
  enterSelectionMode,
  exitSelectionMode,
  updateVisibleBlocks,
  checkAndLoadVisibleMonths
})
</script>

<style scoped>
/* No scrollbar style needed as we use window scroll */
  /* Existing styles */
  .shrink-animation {
    animation: shrink 0.25s forwards ease-in-out;
  }
  
  @keyframes shrink {
    0% { transform: scale(1); }
    100% { transform: scale(0.8); opacity: 0.5; }
  }
</style>