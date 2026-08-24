<template>
  <div
    ref="containerRef"
    data-testid="album-timeline"
    class="fixed right-0 z-40 select-none touch-none transition-opacity duration-200"
    :class="isMobile
      ? ['top-0 h-[100dvh] max-h-none w-14 cursor-ns-resize', mobileVisible || mobileDragging ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none']
      : 'right-2 top-1/2 h-[min(80vh,720px)] w-28 -translate-y-1/2 cursor-pointer opacity-100'"
    @mousemove="handleMouseMove"
    @mouseleave="handleMouseLeave"
    @touchstart="handleTouchStart"
    @touchmove="handleTouchMove"
    @touchend="handleTouchEnd"
    @click="handleItemClick"
  >
    <!-- A fixed proportional track keeps long timelines readable. Pointer selection
         still covers every month, including visually omitted ticks. -->
    <template v-if="!isMobile">
      <div class="absolute bottom-4 right-2 top-4 w-px rounded-full bg-gray-200 dark:bg-gray-700" />
      <div
        v-for="tick in desktopTicks"
        :key="tick.item.key"
        class="group absolute right-2 flex h-5 -translate-y-1/2 items-center justify-end"
        :style="{ top: tick.top }"
      >
        <span
          v-if="tick.showYear"
          class="absolute right-7 whitespace-nowrap font-mono text-xs font-bold transition-colors"
          :class="tick.item.isActiveYear ? 'text-primary-500' : 'text-gray-400 dark:text-gray-500'"
        >{{ tick.item.year }}</span>
        <span
          v-else
          class="absolute right-7 whitespace-nowrap font-mono text-[9px] text-gray-400 opacity-0 transition-opacity group-hover:opacity-100 dark:text-gray-500"
        >{{ tick.item.month }}月</span>
        <span
          class="block h-1 rounded-full transition-all duration-200"
          :class="[
            tick.item.isYearStart ? 'w-4 bg-gray-400 dark:bg-gray-500' : 'w-2 bg-gray-300 dark:bg-gray-600',
            tick.item.isActive ? '!w-6 !bg-primary-500 shadow-primary-500/40 shadow-md' : '',
          ]"
        />
      </div>
    </template>

    <!-- The mobile scrubber travels across the entire viewport. -->
    <div
      v-if="isMobile"
      data-testid="mobile-timeline-thumb"
      class="absolute right-[-4px] flex h-16 w-12 flex-col items-center justify-center gap-1 rounded-l-2xl rounded-r-md border border-r-0 border-gray-200/80 bg-white/95 text-gray-600 shadow-[-4px_2px_14px_rgba(0,0,0,0.14)] backdrop-blur-md transition-[top,transform] duration-100 dark:border-gray-700/80 dark:bg-gray-800/95 dark:text-gray-200"
      :class="mobileDragging ? '!duration-0 scale-105 shadow-[-6px_3px_18px_rgba(0,0,0,0.2)]' : ''"
      :style="{ top: `${mobileThumbTop}px` }"
      aria-label="拖动浏览照片日期"
    >
      <ChevronUp class="h-5 w-5 stroke-[3]" aria-hidden="true" />
      <ChevronDown class="h-5 w-5 stroke-[3]" aria-hidden="true" />
    </div>

    <div
      v-show="!isMobile && isHovering"
      class="pointer-events-none absolute right-2 z-50 h-px w-12 bg-primary-500 shadow-primary-500/40 shadow-md"
      :style="{ top: `${pointerTop}px` }"
    >
      <div class="absolute right-0 top-1/2 h-1.5 w-1.5 -translate-y-1/2 rounded-full bg-primary-500 shadow-sm" />
    </div>
  </div>

  <teleport to="body">
    <div
      v-show="(isHovering || mobileDragging) && hoveredDate"
      class="pointer-events-none fixed z-[9999] whitespace-nowrap rounded bg-gray-900/90 px-2 py-1 text-[10px] text-white shadow-lg backdrop-blur-sm"
      :style="tooltipStyle"
    >{{ hoveredDate }}</div>
  </teleport>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ChevronDown, ChevronUp } from 'lucide-vue-next'
import type { TimelineItem as ApiTimelineItem } from '@/types/album'

const props = defineProps<{ items: ApiTimelineItem[]; activeDate: string }>()
const emit = defineEmits<{ (event: 'select', date: string, behavior?: ScrollBehavior): void }>()

interface DisplayItem {
  key: string
  year: number
  month: number
  day?: number
  dateStr: string
  isYearStart: boolean
  isActive: boolean
  isActiveYear: boolean
}

const containerRef = ref<HTMLElement | null>(null)
const containerHeight = ref(0)
const hoveredDate = ref<string | null>(null)
const isHovering = ref(false)
const pointerTop = ref(0)
const tooltipTop = ref(0)
const isMobile = ref(typeof window !== 'undefined' && window.innerWidth < 768)
const mobileVisible = ref(false)
const mobileDragging = ref(false)
let mobileHideTimer: ReturnType<typeof setTimeout> | null = null
let scrollElement: HTMLElement | Window | null = null
let resizeObserver: ResizeObserver | null = null
let rafId: number | null = null
let lastMobileIndex = -1

const activeParts = computed(() => {
  const match = props.activeDate?.match(/(\d{4})(?:年|-)(\d{1,2})(?:月|-)?(\d{1,2})?/)
  return {
    year: match ? Number(match[1]) : null,
    month: match ? Number(match[2]) : null,
    day: match?.[3] ? Number(match[3]) : null,
  }
})

const displayItems = computed<DisplayItem[]>(() => {
  if (!props.items?.length) return []
  if (isMobile.value) {
    const days = new Map<string, { year: number; month: number; day: number }>()
    props.items.forEach((item) => {
      const key = `${item.year}-${item.month}-${item.day}`
      if (!days.has(key)) days.set(key, { year: item.year, month: item.month, day: item.day })
    })
    return Array.from(days.values())
      .sort((a, b) => b.year - a.year || b.month - a.month || b.day - a.day)
      .map((item, index, list) => ({
        key: `${item.year}-${item.month}-${item.day}`,
        ...item,
        dateStr: `${item.year}-${String(item.month).padStart(2, '0')}-${String(item.day).padStart(2, '0')}`,
        isYearStart: index === 0 || list[index - 1].year !== item.year,
        isActive: activeParts.value.year === item.year && activeParts.value.month === item.month
          && (activeParts.value.day == null || activeParts.value.day === item.day),
        isActiveYear: activeParts.value.year === item.year,
      }))
  }

  const months = new Map<string, { year: number; month: number }>()
  props.items.forEach((item) => {
    const key = `${item.year}-${item.month}`
    if (!months.has(key)) months.set(key, { year: item.year, month: item.month })
  })
  return Array.from(months.values())
    .sort((a, b) => b.year - a.year || b.month - a.month)
    .map((item, index, list) => ({
      key: `${item.year}-${item.month}`,
      ...item,
      dateStr: `${item.year}年${String(item.month).padStart(2, '0')}月`,
      isYearStart: index === 0 || list[index - 1].year !== item.year,
      isActive: activeParts.value.year === item.year && activeParts.value.month === item.month,
      isActiveYear: activeParts.value.year === item.year,
    }))
})

const activeItemIndex = computed(() => {
  const index = displayItems.value.findIndex(item => item.isActive)
  return index < 0 ? 0 : index
})

const itemTop = (index: number, count: number) => {
  if (count <= 1) return '50%'
  const ratio = index / (count - 1)
  return `calc(16px + ${ratio * 100}% - ${ratio * 32}px)`
}

const desktopTicks = computed(() => {
  const items = displayItems.value
  if (!items.length) return []
  const capacity = Math.max(12, Math.floor(Math.max(containerHeight.value - 32, 320) / 8))
  const selected = new Set<number>()
  const step = Math.max(1, Math.ceil(items.length / capacity))
  for (let index = 0; index < items.length; index += step) selected.add(index)
  selected.add(items.length - 1)
  items.forEach((item, index) => {
    if (item.isYearStart || item.isActive) selected.add(index)
  })

  let lastLabelPosition = -Infinity
  return Array.from(selected).sort((a, b) => a - b).map((index) => {
    const item = items[index]
    const ratio = items.length <= 1 ? 0.5 : index / (items.length - 1)
    const pixelPosition = 16 + ratio * Math.max(1, containerHeight.value - 32)
    const showYear = item.isYearStart && (item.isActiveYear || pixelPosition - lastLabelPosition >= 28)
    if (showYear) lastLabelPosition = pixelPosition
    return { item, top: itemTop(index, items.length), showYear }
  })
})

const mobileThumbTop = computed(() => {
  const count = displayItems.value.length
  const ratio = count <= 1 ? 0 : activeItemIndex.value / (count - 1)
  return 8 + ratio * Math.max(1, containerHeight.value - 80)
})

const tooltipStyle = computed(() => ({
  top: `${tooltipTop.value}px`,
  right: isMobile.value ? '60px' : '120px',
}))

const itemAtClientY = (clientY: number) => {
  const rect = containerRef.value?.getBoundingClientRect()
  const items = displayItems.value
  if (!rect || !items.length) return null
  const padding = isMobile.value ? 8 : 16
  const ratio = Math.max(0, Math.min(1, (clientY - rect.top - padding) / Math.max(1, rect.height - padding * 2)))
  const index = Math.round(ratio * (items.length - 1))
  return { item: items[index], index, rect }
}

const updateDesktopPosition = (clientY: number) => {
  const result = itemAtClientY(clientY)
  if (!result) return
  isHovering.value = true
  pointerTop.value = Math.max(16, Math.min(result.rect.height - 16, clientY - result.rect.top))
  tooltipTop.value = Math.max(12, Math.min(window.innerHeight - 36, clientY - 12))
  hoveredDate.value = result.item.dateStr
}

const updateMobilePosition = (clientY: number, select: boolean) => {
  const result = itemAtClientY(clientY)
  if (!result) return
  hoveredDate.value = result.item.dateStr
  tooltipTop.value = Math.max(12, Math.min(window.innerHeight - 36, clientY - 12))
  if (select && result.index !== lastMobileIndex) {
    lastMobileIndex = result.index
    emit('select', result.item.dateStr, 'auto')
  }
}

const handleItemClick = (event: MouseEvent) => {
  if (isMobile.value) return
  updateDesktopPosition(event.clientY)
  if (hoveredDate.value) emit('select', hoveredDate.value)
}

const handleMouseMove = (event: MouseEvent) => {
  if (rafId) cancelAnimationFrame(rafId)
  rafId = requestAnimationFrame(() => updateDesktopPosition(event.clientY))
}

const handleMouseLeave = () => {
  isHovering.value = false
  hoveredDate.value = null
  if (rafId) cancelAnimationFrame(rafId)
}

const handleTouchStart = (event: TouchEvent) => {
  event.preventDefault()
  mobileDragging.value = isMobile.value
  lastMobileIndex = -1
  const touch = event.touches[0]
  if (!touch) return
  if (isMobile.value) updateMobilePosition(touch.clientY, true)
  else updateDesktopPosition(touch.clientY)
}

const handleTouchMove = (event: TouchEvent) => {
  event.preventDefault()
  const clientY = event.touches[0]?.clientY
  if (clientY == null) return
  if (rafId) cancelAnimationFrame(rafId)
  rafId = requestAnimationFrame(() => {
    if (isMobile.value) updateMobilePosition(clientY, true)
    else updateDesktopPosition(clientY)
  })
}

const handleTouchEnd = (event: TouchEvent) => {
  event.preventDefault()
  if (!isMobile.value && hoveredDate.value) emit('select', hoveredDate.value)
  mobileDragging.value = false
  lastMobileIndex = -1
  window.setTimeout(() => {
    isHovering.value = false
    hoveredDate.value = null
  }, 200)
}

const showMobileTimeline = () => {
  if (!isMobile.value || mobileDragging.value) return
  mobileVisible.value = true
  if (mobileHideTimer) clearTimeout(mobileHideTimer)
  mobileHideTimer = setTimeout(() => {
    if (!mobileDragging.value) mobileVisible.value = false
  }, 1100)
}

const handleResize = () => {
  isMobile.value = window.innerWidth < 768
  containerHeight.value = containerRef.value?.clientHeight ?? window.innerHeight
}

onMounted(() => {
  handleResize()
  resizeObserver = new ResizeObserver(handleResize)
  if (containerRef.value) resizeObserver.observe(containerRef.value)
  const main = document.querySelector<HTMLElement>('main')
  scrollElement = main && getComputedStyle(main).overflowY === 'auto' ? main : window
  scrollElement.addEventListener('scroll', showMobileTimeline, { passive: true })
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  if (rafId) cancelAnimationFrame(rafId)
  if (mobileHideTimer) clearTimeout(mobileHideTimer)
  resizeObserver?.disconnect()
  scrollElement?.removeEventListener('scroll', showMobileTimeline)
  window.removeEventListener('resize', handleResize)
})
</script>
