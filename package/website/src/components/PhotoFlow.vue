<template>
  <div ref="rootEl" class="photo-flow" :class="{ 'ts-photo-selecting': isSelectionMode }" @touchstart="startSwipeSelect" @click.capture="handleGridClickCapture" @wheel.passive="cancelDateJump" @touchstart.passive="cancelDateJump">
    <GalleryChrome :loading="loading && !blocks.length" :error="error" :photos="photos" @retry="$emit('retry')" />

    <PhotoContextMenu
      ref="contextMenu" :selected-ids="localSelectedIds" :is-downloading="isDownloading"
      allow-add-to-album :album-context="!!removeLabel && store?.currentContext?.type === 'album'"
      :remove-label="removeLabel"
      :delete-label="deleteLabel === '删除' ? '移到回收站' : deleteLabel"
      @view="(photo, details) => emit('click-photo', photo, details)"
      @download="downloadPhotos"
      @add-to-album="(ids, preserve) => emit('add-to-album', ids, preserve)"
      @set-cover="ids => emit('set-album-cover', ids)"
      @remove="(ids, preserve) => emit('remove-association', ids, preserve)"
      @delete="(ids, preserve) => emit('batch-delete', ids, preserve)"
    />

    <PhotoBatchActionBar
      :visible="isSelectionMode"
      :selected-ids="localSelectedIds"
      :is-all-selected="isAllSelected"
      :is-downloading="isDownloading"
      :delete-label="deleteLabel"
      :album-context="store?.currentContext?.type === 'album'"
      allow-transfer
      :remove-label="removeLabel"
      @cancel="exitSelectionMode"
      @select-all="toggleSelectAll"
      @download="handleDownload"
      @delete="handleDelete"
      @person="openPersonSelector"
      @remove-association="ids => $emit('remove-association', ids)"
      @add-to-album="ids => $emit('add-to-album', ids)"
      @remove-from-album="ids => $emit('remove-from-album', ids)"
      @set-album-cover="ids => $emit('set-album-cover', ids)"
      @batch-edit-time="ids => $emit('batch-edit-time', ids)"
      @batch-edit-location="ids => $emit('batch-edit-location', ids)"
      @transfer="(action, ids) => $emit('transfer', action, ids)"
    >
      <template v-if="$slots['batch-actions']" #batch-actions="scope"><slot name="batch-actions" v-bind="scope" /></template>
    </PhotoBatchActionBar>

    <PersonSelector
      v-model:visible="showPersonSelector"
      :submitting="isAddingPerson"
      @select="handlePersonSelected"
    />

    <!-- 悬浮日期标签：滚动时告诉你「现在停在哪一天」 -->
    <div class="pf-datebar" :class="{ 'is-visible': showDateLabel }" aria-hidden="true">
      <span v-glass-refraction.rim="showDateLabel && !isSelectionMode" class="pf-datelabel ts-liquid-glass ts-photo-date">
        <span class="pf-date-day lm-num">{{ currentDay.day }}</span>
        <span class="pf-date-copy">
          <strong>{{ currentDay.monthLabel }}</strong>
          <span v-if="currentDay.place">{{ currentDay.place }}</span>
        </span>
      </span>
    </div>

    <div ref="contentEl" class="pf-content" data-testid="photo-grid" :style="{ height: `${totalHeight}px` }">
      <!-- 供 UnifiedPhotoPage 定位的月份锚点 -->
      <span
        v-for="marker in monthMarkers"
        :key="`m-${marker.key}`"
        class="month-block pf-month-marker"
        :data-month="marker.key"
        :style="{ top: `${marker.top}px` }"
        aria-hidden="true"
      />

      <div
        v-for="block in visiblePlaceholders"
        :key="block.key"
        class="pf-placeholder"
        :style="{ top: `${block.top}px`, height: `${block.height}px` }"
      >
        <button v-if="failedPages.has(block.key)" type="button" class="ts-button ts-button-ghost" @click="retryPage(block.key)">
          加载失败，重试
        </button>
      </div>

      <div
        v-for="row in visibleRows"
        :key="row.key"
        class="pf-row"
        :style="{ top: `${row.top}px`, height: `${row.height}px`, gap: `${gap}px` }"
      >
        <div
          v-for="item in row.photos"
          :key="item.photo.id"
          :data-photo-id="item.photo.id"
          class="pf-photo"
          :class="{
            'is-selected': localSelectedIds.has(item.photo.id),
            'is-pending': pendingRemoveIds?.has(item.photo.id),
          }"
          :style="{ width: `${item.width}px` }"
          role="button"
          tabindex="0"
          :aria-label="item.photo.filename || formatTime(item.photo.timestamp)"
          @click="handlePhotoClick(item.photo, $event)"
          @keydown.enter.prevent="handlePhotoClick(item.photo, $event)"
          @keydown.space.prevent="handlePhotoClick(item.photo, $event)"
          @contextmenu="contextMenu?.open($event, item.photo)"
        >
          <img
            :src="item.photo.thumbnail"
            :alt="item.photo.filename || ''"
            loading="lazy"
            decoding="async"
            draggable="false"
            @load="onImageLoad($event)"
            @error="onImageLoad($event)"
          />

          <span class="pf-shine" aria-hidden="true"></span>

          <span class="pf-meta">
            <span class="pf-meta-name">{{ item.photo.filename || formatTime(item.photo.timestamp) }}</span>
            <span class="pf-meta-date lm-num">{{ timeOf(item.photo) }}</span>
          </span>

          <span
            class="pf-check ts-photo-selection-indicator"
            :class="{ 'is-visible': isSelectionMode || localSelectedIds.has(item.photo.id), 'is-checked': localSelectedIds.has(item.photo.id) }"
            role="checkbox"
            :aria-checked="localSelectedIds.has(item.photo.id)"
            aria-label="选择这张照片"
            @click.stop="toggleSelection(item.photo)"
          ><Check v-if="localSelectedIds.has(item.photo.id)" class="h-3.5 w-3.5" /></span>

          <span v-if="item.photo.panorama_projection" class="pf-badge pf-badge--left">360°</span>
          <span v-if="item.photo.file_type === 'video'" class="pf-badge pf-badge--right">
            <PlayCircle class="h-3.5 w-3.5" />
            <span v-if="item.photo.duration">{{ item.photo.duration }}</span>
          </span>
          <span v-else-if="item.photo.file_type === 'live_photo'" class="pf-badge pf-badge--right">
            <span class="icon-[tabler--live-photo] h-3.5 w-3.5" />
          </span>
        </div>
      </div>
    </div>

    <slot v-if="!loading && !error && !blocks.length" name="empty" />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onActivated, onDeactivated, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { Check, PlayCircle } from 'lucide-vue-next'
import { format } from 'date-fns'
import GalleryChrome from '@/components/GalleryChrome.vue'
import PhotoBatchActionBar from '@/components/PhotoBatchActionBar.vue'
import PhotoContextMenu from '@/components/PhotoContextMenu.vue'
import PersonSelector from '@/components/PersonSelector.vue'
import { useSelection } from '@/composables/useSelection'
import { useSwipeSelect } from '@/composables/useSwipeSelect'
import { usePhotoBatchActions } from '@/composables/usePhotoBatchActions'
import { aspectOf, flyPhotoIntoViewer } from '@/utils/photoFlight'
import { getPhotoColumns } from '@/utils/photoGridLayout'
import { timelineParts } from '@/utils/photoTimeline'
import type { AlbumImage, TimelineStats } from '@/types/album'
import type { usePhotoStore } from '@/stores/photoStore'

defineOptions({ name: 'PhotoFlow' })

const props = withDefaults(defineProps<{
  photos: AlbumImage[]
  activeDate?: string
  loading: boolean
  error: string | null
  hasMore?: boolean
  viewSize?: 'sm' | 'md' | 'lg'
  active?: boolean
  deleteLabel?: string
  removeLabel?: string
  pendingRemoveIds?: Set<string>
  timelineStats?: TimelineStats | null
  store?: ReturnType<typeof usePhotoStore> | null
}>(), {
  hasMore: false,
  viewSize: 'md',
  active: true,
  deleteLabel: '删除',
  removeLabel: '移除',
  pendingRemoveIds: () => new Set(),
  timelineStats: null,
  store: null,
})

const emit = defineEmits([
  'click-photo', 'load-more', 'batch-delete', 'remove-association', 'add-to-album',
  'remove-from-album', 'set-album-cover', 'retry', 'selection-change', 'transfer',
  'batch-edit-time', 'batch-edit-location', 'update:activeDate',
])

const {
  isSelectionMode,
  selectedIds: localSelectedIds,
  selectionAnchorId,
  enterSelectionMode,
  exitSelectionMode,
  toggleSelect: toggleSelectionId,
  selectAll: selectAllIds,
  selectRange: selectRangeIds,
} = useSelection()

watch(() => Array.from(localSelectedIds), ids => emit('selection-change', ids))

const PAGE_SIZE = 48
const TARGET_CLEARANCE = 12
const rootEl = ref<HTMLElement | null>(null)
const contentEl = ref<HTMLElement | null>(null)
let scrollContainer: HTMLElement | Window = window
const scrollTop = ref(0)
const contentOffset = ref(0)
const containerWidth = ref(1200)
const viewportHeight = ref(window.innerHeight)
const mounted = ref(false)

const gap = computed(() => containerWidth.value < 640 ? 4 : props.viewSize === 'lg' ? 12 : 8)
const columns = computed(() => getPhotoColumns(containerWidth.value, props.viewSize))
const targetHeight = computed(() => (containerWidth.value - gap.value * (columns.value - 1)) / (1.5 * columns.value))

const remoteStore = computed(() => props.store?.timelineStats === props.timelineStats && props.store?.loadPhotoChunk
  ? props.store : null)

interface FlowPhoto { photo: AlbumImage; width: number }
interface FlowRow { key: string; top: number; height: number; photos: FlowPhoto[]; startIndex: number }
interface FlowPage {
  key: string
  year: number
  month: number
  skip: number
  count: number
  start: number
  photos?: AlbumImage[]
}
interface FlowBlock extends FlowPage { top: number; height: number; rows: FlowRow[] | null }

const timeline = computed(() => {
  if (!remoteStore.value) return []
  const entries = [...(props.timelineStats?.timeline ?? [])]
    .filter(item => item.count > 0)
    .sort((a, b) => b.year - a.year || b.month - a.month || b.day - a.day)
  let start = 0
  return entries.map(item => {
    const day = { ...item, start }
    start += item.count
    return day
  })
})

const pages = computed<FlowPage[]>(() => {
  const result: FlowPage[] = []
  if (!remoteStore.value) {
    const list = props.photos
    let start = 0
    while (start < list.length) {
      const { year, month } = timelineParts(list[start].timestamp)
      let end = start + 1
      while (end < list.length && end - start < PAGE_SIZE) {
        const next = timelineParts(list[end].timestamp)
        if (next.year !== year || next.month !== month) break
        end++
      }
      result.push({ key: `local:${start}`, year, month, start, skip: 0, count: end - start, photos: list.slice(start, end) })
      start = end
    }
    return result
  }

  const months = new Map<string, { year: number; month: number; start: number; count: number }>()
  for (const day of timeline.value) {
    const key = `${day.year}-${day.month}`
    const month = months.get(key)
    if (month) month.count += day.count
    else months.set(key, { year: day.year, month: day.month, start: day.start, count: day.count })
  }
  for (const [key, month] of months) {
    for (let skip = 0; skip < month.count; skip += PAGE_SIZE) {
      result.push({
        year: month.year, month: month.month, key: `${key}:${skip}`, skip,
        start: month.start + skip, count: Math.min(PAGE_SIZE, month.count - skip),
      })
    }
  }
  return result
})

// 每页独立排版。新页到达时只计算这一页，滚动只查找和渲染视口附近的行。
const layoutPage = computed(() => {
  const width = containerWidth.value
  const space = gap.value
  const target = targetHeight.value
  const cache = new WeakMap<AlbumImage[], { rows: FlowRow[]; height: number }>()
  const perRow = columns.value
  const estimateHeight = (count: number) => Math.ceil(count / perRow) * (target + space)

  const arrange = (photos: AlbumImage[]) => {
    const cached = cache.get(photos)
    if (cached) return cached

    const rows: FlowRow[] = []
    let top = 0
    for (let startIndex = 0; startIndex < photos.length; startIndex += perRow) {
      const items = photos.slice(startIndex, startIndex + perRow).map(photo => ({
        photo,
        width: photo.width && photo.height ? Math.min(3, Math.max(.55, photo.width / photo.height)) : 1.5,
      }))
      const aspectSum = items.reduce((sum, item) => sum + item.width, 0)
      const height = (width - space * (items.length - 1)) / aspectSum
      const rowHeight = items.length === perRow ? height : Math.min(height, target * 1.35)
      for (const item of items) item.width *= rowHeight
      rows.push({ key: items[0].photo.id, top, height: rowHeight, photos: items, startIndex })
      top += rowHeight + space
    }
    const layout = { rows, height: top }
    cache.set(photos, layout)
    return layout
  }
  return { arrange, estimateHeight }
})

const blocks = computed<FlowBlock[]>(() => {
  const cache = remoteStore.value?.photoChunks
  const sizing = layoutPage.value
  let top = 0
  return pages.value.map(page => {
    const photos = page.photos ?? cache?.get(page.key)
    const layout = photos ? sizing.arrange(photos) : null
    const height = layout?.height ?? sizing.estimateHeight(page.count)
    const block = { ...page, top, height, rows: layout?.rows ?? null }
    top += height
    return block
  })
})
const blocksByKey = computed(() => new Map(blocks.value.map(block => [block.key, block])))
const totalHeight = computed(() => {
  const last = blocks.value.at(-1)
  return last ? last.top + last.height : 0
})
const monthMarkers = computed(() => {
  const offsets = new Map<string, number>()
  for (const block of blocks.value) {
    const key = `${block.year}-${block.month}`
    if (!offsets.has(key)) offsets.set(key, block.top)
  }
  return Array.from(offsets, ([key, top]) => ({ key, top }))
})

const findAt = <T,>(items: T[], value: number, position: (item: T) => number): number => {
  let low = 0
  let high = items.length
  while (low < high) {
    const mid = (low + high) >>> 1
    if (position(items[mid]) <= value) low = mid + 1
    else high = mid
  }
  return Math.max(0, low - 1)
}
const relativeTop = computed(() => scrollTop.value - contentOffset.value)
const visibleBlocks = computed(() => {
  const list = blocks.value
  const start = findAt(list, relativeTop.value - 300, block => block.top)
  const bottom = relativeTop.value + viewportHeight.value + 400
  const visible: FlowBlock[] = []
  for (let i = start; i < list.length && list[i].top < bottom; i++) visible.push(list[i])
  return visible
})
const visibleRows = computed(() => {
  const top = relativeTop.value - 300
  const bottom = relativeTop.value + viewportHeight.value + 400
  const result: FlowRow[] = []
  for (const block of visibleBlocks.value) {
    if (!block.rows) continue
    const first = findAt(block.rows, top - block.top, row => row.top)
    for (let i = first; i < block.rows.length; i++) {
      const row = block.rows[i]
      if (block.top + row.top >= bottom) break
      result.push({ ...row, top: block.top + row.top })
    }
  }
  return result
})
const visiblePlaceholders = computed(() => visibleBlocks.value.filter(block => !block.rows))

const adjacentPhotoPage = (id: string, direction: -1 | 1) => {
  const store = remoteStore.value
  if (!store) return undefined

  for (const page of pages.value) {
    const index = store.photoChunks.get(page.key)?.findIndex(photo => photo.id === id) ?? -1
    if (index < 0) continue
    const target = page.start + index + direction
    const targetPage = pages.value[findAt(pages.value, target, item => item.start)]
    if (!targetPage || target < targetPage.start || target >= targetPage.start + targetPage.count) return null
    return { page: targetPage, offset: target - targetPage.start }
  }
  return null
}

const hasAdjacentPhoto = (id: string, direction: -1 | 1) => {
  const target = adjacentPhotoPage(id, direction)
  return target === undefined ? undefined : target !== null
}

const loadAdjacentPhoto = async (id: string, direction: -1 | 1) => {
  const target = adjacentPhotoPage(id, direction)
  const store = remoteStore.value
  if (!target || !store) return null
  const { page, offset } = target
  const stats = props.timelineStats
  if (!await store.loadPhotoChunk(page.year, page.month, page.skip, page.count)
    || props.timelineStats !== stats || remoteStore.value !== store) return null
  return store.photoChunks.get(page.key)?.[offset] ?? null
}

const headerInset = ref(80)
const targetIndex = ref<number | null>(null)
const currentPosition = computed(() => {
  const probe = relativeTop.value + Math.min(headerInset.value + TARGET_CLEARANCE + 8, viewportHeight.value / 2)
  const block = blocks.value[findAt(blocks.value, probe, item => item.top)]
  if (!block) return null
  const index = findAt(block.rows ?? [], probe - block.top, row => row.top)
  const row = block.rows?.[index]
  if (row) {
    const offset = targetIndex.value === null ? 0 : targetIndex.value - block.start - row.startIndex
    const photo = (row.photos[offset] ?? row.photos[0]).photo
    return { ...timelineParts(photo.timestamp), photo }
  }
  const fraction = Math.max(0, Math.min(.999, (probe - block.top) / Math.max(1, block.height)))
  return timeline.value[findAt(timeline.value, block.start + Math.floor(fraction * block.count), day => day.start)] ?? null
})
const dateLabel = computed(() => {
  const date = currentPosition.value
  if (!date) return ''
  if (!date.year) return '时间未知'
  return `${date.year}-${String(date.month).padStart(2, '0')}-${String(date.day).padStart(2, '0')}`
})
const currentDay = computed(() => {
  const date = currentPosition.value
  if (!date?.year) return { day: '—', monthLabel: date ? '时间未知' : '', place: '' }
  const weekday = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][new Date(date.year, date.month - 1, date.day).getDay()]
  const photo = 'photo' in date ? date.photo : undefined
  return {
    day: String(date.day).padStart(2, '0'),
    monthLabel: `${date.year} 年 ${date.month} 月 · ${weekday}`,
    place: photo?.metadata_info?.city || photo?.metadata_info?.district || '',
  }
})
const showDateLabel = computed(() => !!dateLabel.value && relativeTop.value > 64)

const readScrollTop = () => scrollContainer === window ? window.scrollY : (scrollContainer as HTMLElement).scrollTop
const viewportTop = () => scrollContainer === window ? 0 : (scrollContainer as HTMLElement).getBoundingClientRect().top
const measure = () => {
  if (!mounted.value || !props.active || !contentEl.value || !rootEl.value?.clientWidth) return
  containerWidth.value = rootEl.value.clientWidth
  viewportHeight.value = scrollContainer === window ? window.innerHeight : (scrollContainer as HTMLElement).clientHeight
  contentOffset.value = contentEl.value.getBoundingClientRect().top - viewportTop() + readScrollTop()
  headerInset.value = Number.parseFloat(getComputedStyle(rootEl.value).getPropertyValue('--photo-page-header-height')) || 80
  scrollTop.value = readScrollTop()
}

let frame = 0
const handleScroll = () => {
  if (frame || !mounted.value || !props.active) return
  frame = requestAnimationFrame(() => {
    frame = 0
    scrollTop.value = readScrollTop()
  })
}

const failedPages = reactive(new Set<string>())
let pendingLoad = false
let requestedCount = -1
let dateJump: { key: string; index: number } | null = null
const cancelDateJump = () => {
  dateJump = null
  targetIndex.value = null
}

const loadVisiblePage = async () => {
  if (!mounted.value || !props.active || props.error || props.loading || pendingLoad) return
  const store = remoteStore.value
  if (!store) {
    if (props.hasMore && requestedCount !== props.photos.length && relativeTop.value + viewportHeight.value + 500 >= totalHeight.value) {
      requestedCount = props.photos.length
      emit('load-more')
    }
    return
  }

  const middle = relativeTop.value + viewportHeight.value / 2
  const preferred = dateJump && blocksByKey.value.get(dateJump.key)
  const block = preferred && !preferred.rows && !failedPages.has(preferred.key) ? preferred
    : visiblePlaceholders.value.filter(item => !failedPages.has(item.key))
      .sort((a, b) => Math.abs(a.top + a.height / 2 - middle) - Math.abs(b.top + b.height / 2 - middle))[0]
  if (!block) return
  const stats = props.timelineStats
  pendingLoad = true
  try {
    const ok = await store.loadPhotoChunk(block.year, block.month, block.skip, block.count)
    if (!ok && props.timelineStats === stats && remoteStore.value === store) failedPages.add(block.key)
  } finally {
    pendingLoad = false
    void loadVisiblePage()
  }
}

const retryPage = (key: string) => {
  failedPages.delete(key)
  void loadVisiblePage()
}

const scrollToBlock = (block: FlowBlock, index: number, behavior: ScrollBehavior) => {
  const row = block.rows?.[findAt(block.rows, index, item => item.startIndex)]
  const estimate = Math.max(0, block.height - targetHeight.value) * index / Math.max(1, block.count)
  const top = Math.max(0, contentOffset.value + block.top + (row?.top ?? estimate) - headerInset.value - TARGET_CLEARANCE)
  const nearby = Math.abs(top - readScrollTop()) < viewportHeight.value * 3
  const smooth = nearby && !matchMedia('(prefers-reduced-motion: reduce)').matches
  scrollContainer.scrollTo({ top, behavior: smooth ? behavior : 'auto' })
  handleScroll()
}

watch(blocks, (next, previous) => {
  if (!mounted.value || !props.active || !previous.length || !next.length) return
  const jump = dateJump
  const jumpBlock = jump && blocksByKey.value.get(jump.key)
  if (jump && jumpBlock?.rows) {
    dateJump = null
    void nextTick(() => {
      measure()
      if (mounted.value && props.active) scrollToBlock(jumpBlock, jump.index, 'auto')
    })
    return
  }

  // 替换视口上方的占位时保住当前页，不让内容随估算高度变化而跳动。
  const originalTop = readScrollTop()
  const probe = originalTop - contentOffset.value + headerInset.value + TARGET_CLEARANCE + 8
  const old = previous[findAt(previous, probe, block => block.top)]
  const current = blocksByKey.value.get(old.key)
  if (!current) return
  const delta = current.top - old.top
  if (!delta) return
  void nextTick(() => {
    if (!mounted.value || !props.active || Math.abs(readScrollTop() - originalTop) > 1) return
    scrollContainer.scrollBy({ top: delta, behavior: 'auto' })
    measure()
  })
})

watch([visibleBlocks, () => props.loading, () => props.active, mounted], () => {
  void loadVisiblePage()
}, { flush: 'post' })
watch(() => props.timelineStats, () => {
  cancelDateJump()
  failedPages.clear()
  requestedCount = -1
})
watch([dateLabel, () => props.active, mounted], ([label, active, ready]) => {
  if (active && ready && !dateJump && label && props.activeDate !== label) emit('update:activeDate', label)
}, { flush: 'post' })

const findScrollParent = (element?: HTMLElement | null): HTMLElement | Window => {
  let parent = element?.parentElement
  while (parent) {
    if (['auto', 'scroll'].includes(getComputedStyle(parent).overflowY)) return parent
    parent = parent.parentElement
  }
  return window
}

let resizeObserver: ResizeObserver | undefined
const attachScroll = () => {
  if (mounted.value) return
  scrollContainer = findScrollParent(rootEl.value)
  mounted.value = true
  measure()
  scrollContainer.addEventListener('scroll', handleScroll, { passive: true })
  resizeObserver = new ResizeObserver(measure)
  if (rootEl.value) resizeObserver.observe(rootEl.value)
  if (scrollContainer !== window) resizeObserver.observe(scrollContainer as HTMLElement)
  const header = rootEl.value?.closest('.unified-photo-page')?.querySelector('[data-photo-header]')
  if (header) resizeObserver.observe(header)
  window.addEventListener('resize', measure)
}
const detachScroll = () => {
  mounted.value = false
  cancelDateJump()
  cancelSwipeSelect()
  if (suppressGridClickTimer) clearTimeout(suppressGridClickTimer)
  scrollContainer.removeEventListener('scroll', handleScroll)
  resizeObserver?.disconnect()
  window.removeEventListener('resize', measure)
  if (frame) cancelAnimationFrame(frame)
  frame = 0
}
onMounted(attachScroll)
onActivated(attachScroll)
onDeactivated(detachScroll)
onUnmounted(detachScroll)
watch(() => props.active, active => {
  if (active) measure()
  else cancelDateJump()
}, { flush: 'post' })

const onImageLoad = (event: Event) => (event.currentTarget as HTMLImageElement).classList.add('is-developed')

/* ---------------------------------------------------------------------------
 * Interaction
 * ------------------------------------------------------------------------- */
const toggleSelection = (photo: AlbumImage) => {
  toggleSelectionId(photo.id)
  // 普通点击移动 Shift 范围选择的锚点
  selectionAnchorId.value = photo.id
  if (localSelectedIds.size > 0 && !isSelectionMode.value) enterSelectionMode()
}

// 瀑布流的视觉顺序：photos 数组顺序（blocks/rows 按同一顺序切分排版）
const orderedPhotoIds = computed(() => props.photos.map(photo => photo.id))

// PC 端 Shift 点击范围选择/取消选择：整段置为与目标端相反的单一状态。
// Shift 点击不移动锚点（与 macOS Finder 一致），普通点击才移动。
const handleRangeClick = (photo: AlbumImage) => {
  const targetSelected = localSelectedIds.has(photo.id)
  if (!isSelectionMode.value && !targetSelected) enterSelectionMode()
  selectRangeIds(orderedPhotoIds.value, photo.id)
  return true
}

// 移动端滑选：长按进入选择模式，不松手拖动按视觉顺序整段选择/取消。
// 滑选/长按结束后的合成 click 抑制（350ms 内点击被吞掉）
const suppressGridClick = ref(false)
let suppressGridClickTimer: ReturnType<typeof setTimeout> | null = null
const suppressClickAfterGesture = () => {
  suppressGridClick.value = true
  if (suppressGridClickTimer) clearTimeout(suppressGridClickTimer)
  suppressGridClickTimer = setTimeout(() => {
    suppressGridClick.value = false
    suppressGridClickTimer = null
  }, 350)
}

const {
  onTouchstart: startSwipeSelect,
  cancel: cancelSwipeSelect,
} = useSwipeSelect({
  canStart: () => containerWidth.value < 640,
  canSweep: () => true,
  isSelected: (id) => localSelectedIds.has(id),
  onLongPressActivate: (photoId) => {
    const photo = props.photos.find(item => item.id === photoId)
    if (!photo) return
    toggleSelection(photo)
    navigator.vibrate?.(10)
  },
  onSwipePhoto: (photoId, shouldSelect) => {
    if (shouldSelect) localSelectedIds.add(photoId)
    else localSelectedIds.delete(photoId)
    if (localSelectedIds.size > 0 && !isSelectionMode.value) enterSelectionMode()
  },
  onSuppressClick: suppressClickAfterGesture,
})

const handleGridClickCapture = (event: MouseEvent) => {
  if (!suppressGridClick.value) return
  event.preventDefault()
  event.stopPropagation()
}

const handlePhotoClick = (photo: AlbumImage, event?: Event) => {
  if (isSelectionMode.value) {
    if ((event as MouseEvent | undefined)?.shiftKey && handleRangeClick(photo)) return
    toggleSelection(photo)
    return
  }
  if ((event as MouseEvent | undefined)?.shiftKey && handleRangeClick(photo)) return
  if (photo.file_type && photo.file_type !== 'image' && photo.file_type !== 'live_photo') {
    emit('click-photo', photo)
    return
  }
  flyPhotoIntoViewer(event?.currentTarget as HTMLElement | null, aspectOf(photo.width, photo.height), () => emit('click-photo', photo))
}

const isAllSelected = computed(() => props.photos.length > 0 && props.photos.every(photo => localSelectedIds.has(photo.id)))

const toggleSelectAll = () => {
  if (isAllSelected.value) {
    exitSelectionMode()
    return
  }
  selectAllIds(props.photos.map(photo => photo.id))
  enterSelectionMode()
}

const contextMenu = ref<InstanceType<typeof PhotoContextMenu> | null>(null)
const { isDownloading, isAddingPerson, showPersonSelector, openPersonSelector, handlePersonSelected, handleDownload, downloadPhotos } = usePhotoBatchActions({
  selectedIds: () => localSelectedIds,
  photos: () => props.photos,
  clearSelection: () => exitSelectionMode(),
  exitAfterDownload: true,
})

const handleDelete = () => {
  if (localSelectedIds.size === 0) return
  const ids = Array.from(localSelectedIds)
  if (props.deleteLabel.includes('移除')) emit('remove-from-album', ids)
  else emit('batch-delete', ids)
}

const formatTime = (timestamp: number) => Number.isFinite(timestamp) ? format(new Date(timestamp), 'yyyy-MM-dd HH:mm') : '时间未知'
const timeOf = (photo: AlbumImage) => {
  const stamp = photo.timestamp
  if (!Number.isFinite(stamp)) return ''
  return format(new Date(stamp), 'MM-dd HH:mm')
}

const scrollToDate = (date: string, behavior: ScrollBehavior = 'smooth'): boolean => {
  const match = date.match(/^(\d+)(?:年|-)(\d+)(?:月|-(\d+))?$/)
  if (!match && date !== '时间未知') return false
  const year = match ? Number(match[1]) : 0
  const month = match ? Number(match[2]) : 0
  const day = match?.[3] ? Number(match[3]) : null
  const matches = (parts: { year: number; month: number; day: number }) =>
    parts.year === year && parts.month === month && (day === null || parts.day === day)
  const index = remoteStore.value
    ? timeline.value.find(matches)?.start ?? -1
    : props.photos.findIndex(photo => matches(timelineParts(photo.timestamp)))
  return jumpToIndex(index, behavior)
}

const jumpToIndex = (index: number, behavior: ScrollBehavior): boolean => {
  if (index < 0) return false
  const block = blocks.value[findAt(blocks.value, index, item => item.start)]
  if (!block || index >= block.start + block.count) return false

  targetIndex.value = index
  dateJump = block.rows ? null : { key: block.key, index: index - block.start }
  failedPages.delete(block.key)
  scrollToBlock(block, index - block.start, block.rows ? behavior : 'auto')
  void loadVisiblePage()
  return true
}

const scrollToPhoto = async (photo: AlbumImage, anchorTop?: number) => {
  await nextTick()
  measure()
  const findRow = (block: FlowBlock) => block.rows?.find(row => row.photos.some(item => item.photo.id === photo.id))
  const block = blocks.value.find(item => findRow(item))
  const row = block && findRow(block)
  if (!block || !row) {
    const parts = timelineParts(photo.timestamp)
    const month = timeline.value.find(item => item.year === parts.year && item.month === parts.month)
    if (month && !remoteStore.value?.isPartialPhotoMonth(parts.year, parts.month)) {
      const index = props.photos.filter(item => {
        const date = timelineParts(item.timestamp)
        return date.year === parts.year && date.month === parts.month
      }).findIndex(item => item.id === photo.id)
      if (index >= 0) {
        jumpToIndex(month.start + index, 'auto')
        return
      }
    }
    scrollToDate(parts.year ? parts.dayKey : '时间未知', 'auto')
    return
  }

  targetIndex.value = block.start + row.startIndex + row.photos.findIndex(item => item.photo.id === photo.id)
  scrollToBlock(block, row.startIndex, 'auto')
  if (anchorTop !== undefined) {
    const delta = (contentOffset.value + block.top + row.top - readScrollTop() + viewportTop())
      - Math.max(anchorTop, viewportTop() + headerInset.value)
    scrollContainer.scrollBy({ top: delta, behavior: 'auto' })
  }
  handleScroll()
}

defineExpose({
  isSelectionMode,
  enterSelectionMode,
  exitSelectionMode,
  scrollToDate,
  scrollToPhoto,
  hasAdjacentPhoto,
  loadAdjacentPhoto,
  updateVisibleBlocks: measure,
  checkAndLoadVisibleMonths: loadVisiblePage,
})
</script>

<style scoped>
.photo-flow { position: relative; }
@media (min-width: 768px) {
  /* 右侧给年份导航条留出通路，照片墙有干净的右边缘 */
  .photo-flow { margin-right: 68px; }
}

.pf-content { position: relative; width: 100%; overflow-anchor: none; }
.pf-month-marker { position: absolute; left: 0; width: 1px; height: 1px; }

.pf-placeholder {
  position: absolute;
  inset-inline: 0;
  display: grid;
  align-content: center;
  justify-content: center;
  border-radius: var(--ts-radius-photo);
  background: var(--ts-color-surface-muted);
}
.pf-row {
  position: absolute;
  left: 0;
  display: flex;
  width: 100%;
  align-items: stretch;
}

.pf-photo {
  position: relative;
  height: 100%;
  overflow: hidden;
  border-radius: var(--ts-radius-photo);
  background: var(--ts-color-surface-muted);
  box-shadow: var(--ts-shadow-photo);
  cursor: pointer;
  isolation: isolate;
  transition: transform 320ms var(--ts-ease-paper), box-shadow 320ms var(--ts-ease-paper);
}

.pf-photo img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0;
  transform: scale(1.02);
  transition: opacity 520ms var(--ts-ease-enter), transform 900ms var(--ts-ease-paper);
}
.pf-photo img.is-developed { opacity: 1; transform: scale(1); }

/* 还没显影的相框用一条缓慢流动的高光表示「正在取图」，不要显示成一块空白 */
.pf-photo::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 0;
  background: linear-gradient(100deg, rgb(255 255 255 / 0%) 12%, rgb(255 255 255 / 52%) 50%, rgb(255 255 255 / 0%) 88%) 0 0 / 220% 100%;
  animation: pf-shimmer 1.5s linear infinite;
  pointer-events: none;
}
html.dark .pf-photo::before {
  background-image: linear-gradient(100deg, rgb(255 255 255 / 0%) 12%, rgb(255 255 255 / 14%) 50%, rgb(255 255 255 / 0%) 88%);
}
.pf-photo:has(img.is-developed)::before { display: none; }
@keyframes pf-shimmer {
  from { background-position: 120% 0; }
  to { background-position: -120% 0; }
}
@media (prefers-reduced-motion: reduce) {
  .pf-photo::before { animation: none; background: none; }
}

@media (hover: hover) and (pointer: fine) {
  .pf-photo:hover { transform: translate3d(0, -3px, 0); box-shadow: var(--ts-shadow-floating); z-index: 3; }
  .pf-photo:hover img { transform: scale(1.045); }
}
.pf-photo:active { transform: scale(.994); }
.pf-photo:focus-visible { outline: 2px solid var(--ts-journal-focus); outline-offset: 3px; }
.pf-photo.is-selected { box-shadow: 0 0 0 2px var(--theme-primary), var(--ts-shadow-photo); }
.pf-photo.is-pending { filter: grayscale(1); opacity: .6; }

/* 指针掠过时的一层柔光 */
.pf-shine {
  position: absolute;
  inset: 0;
  opacity: 0;
  pointer-events: none;
  background: linear-gradient(115deg, transparent 30%, rgb(255 255 255 / 16%) 48%, transparent 66%);
  transition: opacity 300ms ease;
}
.pf-photo:hover .pf-shine { opacity: 1; }

.pf-meta {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 2;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  padding: 26px 12px 10px;
  background: linear-gradient(to top, rgb(6 8 12 / 74%), transparent);
  color: #fff;
  opacity: 0;
  transform: translateY(6px);
  transition: opacity 240ms ease, transform 300ms var(--ts-ease-paper);
  pointer-events: none;
}
.pf-photo:hover .pf-meta { opacity: 1; transform: translateY(0); }
.pf-meta-name {
  overflow: hidden;
  font-size: 12px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pf-meta-date { flex-shrink: 0; color: rgb(255 255 255 / 72%); font-size: 11px; }

.pf-check {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 3;
  display: none;
  width: 22px;
  height: 22px;
  align-items: center;
  justify-content: center;
  border: 1.5px solid rgb(255 255 255 / 80%);
  border-radius: 999px;
  background: rgb(10 12 16 / 22%);
  color: #fff;
  box-shadow: 0 1px 4px rgb(0 0 0 / 24%);
  -webkit-backdrop-filter: var(--ts-photo-check-filter, blur(6px));
  backdrop-filter: var(--ts-photo-check-filter, blur(6px));
  transition: background-color 160ms ease, border-color 160ms ease, transform 160ms var(--ts-ease-spring);
}
.pf-check.is-visible { display: flex; }
.pf-check:hover { transform: scale(1.08); }
.pf-check.is-checked { background: var(--theme-primary); border-color: var(--theme-primary); }

.pf-badge {
  position: absolute;
  bottom: 10px;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border-radius: 999px;
  padding: 3px 8px;
  background: rgb(10 12 16 / 52%);
  color: #fff;
  font-size: 10.5px;
  font-weight: 650;
  line-height: 1.2;
  pointer-events: none;
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
}
.pf-badge--left { left: 10px; bottom: auto; top: 10px; }
.pf-badge--right { right: 10px; bottom: auto; top: 10px; }

/* 悬浮日期标签 */
.pf-datebar {
  position: sticky;
  top: calc(var(--photo-page-header-height, 80px) + 4px);
  z-index: 6;
  height: 0;
  pointer-events: none;
  opacity: 0;
  transform: translateY(-6px);
  transition: opacity 240ms ease, transform 320ms var(--ts-ease-paper);
}
.pf-datebar.is-visible { opacity: 1; transform: none; }
.pf-datelabel {
  position: absolute;
  top: 0;
  left: 0;
  display: inline-flex;
  align-items: center;
  gap: 9px;
  border-radius: 999px;
  padding: 4px 14px 4px 10px;
}
.pf-date-day {
  color: var(--ts-color-text);
  font-family: var(--lm-font-display);
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -.05em;
  line-height: 1;
}
.pf-date-copy { display: grid; gap: 1px; }
.pf-date-copy strong {
  color: var(--ts-color-text);
  font-size: 11px;
  font-weight: 650;
  letter-spacing: .08em;
  white-space: nowrap;
}
.pf-date-copy span {
  color: var(--ts-color-text-secondary);
  font-size: 10.5px;
  white-space: nowrap;
}

@media (max-width: 767px) {
  .pf-photo { border-radius: 10px; }
  .pf-meta { display: none; }
  .pf-datelabel { padding: 3px 10px 3px 8px; }
  .pf-date-day { font-size: 17px; }
  .pf-date-copy strong { font-size: 10px; }
  .pf-date-copy span { display: none; }
}

@media (prefers-reduced-motion: reduce) {
  .pf-photo, .pf-photo img, .pf-meta, .pf-shine { transition: none !important; animation: none !important; }
}
</style>
