<template>
  <div 
    ref="containerRef"
    data-testid="album-timeline"
    class="fixed cursor-pointer right-1 md:right-2 top-1/2 transform -translate-y-1/2 z-40 flex flex-col items-end select-none py-4 pr-1 md:pr-2 touch-none max-h-[80vh] no-scrollbar transition-opacity duration-200"
    :class="isMobile
      ? (mobileVisible || mobileDragging ? 'opacity-100 pointer-events-auto h-[52vh] w-12' : 'opacity-0 pointer-events-none h-[52vh] w-12')
      : 'opacity-100 overflow-y-auto'"
    @mousemove="handleMouseMove"
    @mouseleave="handleMouseLeave"
    @touchstart="handleTouchStart"
    @touchmove="handleTouchMove"
    @touchend="handleTouchEnd"
    @click="handleItemClick"
  >
    <div
      v-for="item in displayItems"
      :key="item.key"
      :ref="el => setItemRef(el, item.key)"
      class="hidden md:flex items-center justify-end group relative transition-all duration-200 w-12 md:w-24"
      :class="[
        item.isYearStart ? 'mt-4 mb-1' : 'my-[2px]'
      ]"
    >

      <!-- Year Label -->
      <div
        v-if="item.isYearStart"
        class="absolute right-6 md:right-8 text-[10px] md:text-xs font-bold font-mono transition-all duration-300"
        :class="[
          item.isActiveYear ? 'text-primary-500 scale-110' : 'text-gray-400 dark:text-gray-500'
        ]"
      >
        {{ item.year }}
      </div>

      <!-- Month Label (Hover) -->
      <div
        v-if="!item.isYearStart"
        class="absolute right-6 md:right-8 text-[9px] font-mono text-gray-300 dark:text-gray-600 opacity-0 group-hover:opacity-100 transition-opacity"
      >
        {{ item.month }}
      </div>

      <!-- Marker Line -->
      <div 
        class="h-1 rounded-full transition-all duration-300"
        :class="[
          item.isYearStart
            ? 'w-2 md:w-4 bg-gray-400 dark:bg-gray-400'
            : 'w-1 md:w-2 bg-gray-300 dark:bg-gray-600',
          item.isActive ? '!w-3 !md:w-6 !bg-primary-500 shadow-[0_0_8px_rgba(var(--primary-500),0.6)]' : '',
        ]"
      ></div>
    </div>

    <!-- Mobile: a transient scrubber replaces the dense desktop year/month rail. -->
    <div v-if="isMobile" class="absolute right-2 inset-y-4 w-1 rounded-full bg-gray-300/70 dark:bg-gray-600/70">
      <div
        data-testid="mobile-timeline-thumb"
        class="absolute right-1/2 translate-x-1/2 w-3 h-10 rounded-full bg-primary-500 shadow-lg shadow-primary-500/30 transition-[top] duration-100"
        :class="{ '!duration-0 scale-110': mobileDragging }"
        :style="{ top: `${mobileThumbTop}px` }"
      ></div>
    </div>

    <!-- Independent Pointer -->
    <div 
      v-show="isHovering"
      class="absolute right-1 md:right-2 h-px bg-primary-500 w-8 md:w-12 pointer-events-none z-50 shadow-[0_0_8px_rgba(var(--primary-500),0.6)]"
      :style="pointerStyle"
    >
      <div class="absolute right-0 top-1/2 -translate-y-1/2 w-1.5 h-1.5 bg-primary-500 rounded-full shadow-sm"></div>
    </div>
  </div>

  <!-- Tooltip (teleported to body) -->
  <teleport to="body">
    <div 
      v-show="(isHovering || mobileDragging) && hoveredDate"
      class="fixed bg-gray-900/90 text-white text-[10px] px-2 py-1 rounded whitespace-nowrap pointer-events-none z-[9999] backdrop-blur-sm shadow-lg transition-transform duration-50"
      :style="tooltipStyle"
    >
      {{ hoveredDate }}
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import type { TimelineItem as ApiTimelineItem } from '@/types/album'

const props = defineProps<{
  items: ApiTimelineItem[]
  activeDate: string
}>()

const emit = defineEmits<{
  (event: 'select', date: string, behavior?: ScrollBehavior): void
}>()

// State
const containerRef = ref<HTMLElement | null>(null)
const itemRefs = ref<Map<string, HTMLElement>>(new Map())
const hoveredDate = ref<string | null>(null)
const isHovering = ref(false)
const pointerTop = ref(0)
const tooltipTop = ref(0)
const isMobile = ref(typeof window !== 'undefined' && window.innerWidth < 768)
const mobileVisible = ref(false)
const mobileDragging = ref(false)
let mobileHideTimer: ReturnType<typeof setTimeout> | null = null
let scrollElement: HTMLElement | Window | null = null

// Collect refs
const setItemRef = (el: any, key: string) => {
  if (el) itemRefs.value.set(key, el as HTMLElement)
  else itemRefs.value.delete(key)
}

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

// Build items (Group by Month)
const displayItems = computed(() => {
  if (!props.items?.length) return []

  // Parse active date (format: "YYYY年MM月" or "YYYY-MM")
  const activeMatch = props.activeDate ? (props.activeDate.match(/(\d+)年(\d+)月/) || props.activeDate.match(/(\d+)-(\d+)/)) : null
  const activeYear = activeMatch ? parseInt(activeMatch[1]) : null
  const activeMonth = activeMatch ? parseInt(activeMatch[2]) : null

  if (isMobile.value) {
    const dayMap = new Map<string, { year: number; month: number; day: number }>()
    props.items.forEach(item => {
      const key = `${item.year}-${item.month}-${item.day}`
      if (!dayMap.has(key)) dayMap.set(key, { year: item.year, month: item.month, day: item.day })
    })
    return Array.from(dayMap.values())
      .sort((a, b) => b.year - a.year || b.month - a.month || b.day - a.day)
      .map((item, index, list) => ({
        key: `${item.year}-${item.month}-${item.day}`,
        year: item.year,
        month: item.month,
        day: item.day,
        dateStr: `${item.year}-${String(item.month).padStart(2, '0')}-${String(item.day).padStart(2, '0')}`,
        isYearStart: index === 0 || list[index - 1].year !== item.year,
        isActive: activeYear === item.year && activeMonth === item.month,
        isActiveYear: activeYear === item.year,
      }))
  }
  
  // Aggregate by Month
  const monthMap = new Map<string, { year: number, month: number }>()
  
  props.items.forEach(item => {
      const key = `${item.year}-${item.month}`
      if (!monthMap.has(key)) {
          monthMap.set(key, { year: item.year, month: item.month })
      }
  })

  // Sort Descending
  const sortedMonths = Array.from(monthMap.values()).sort((a, b) => {
      if (a.year !== b.year) return b.year - a.year
      return b.month - a.month
  })

  const items: DisplayItem[] = []
  let lastYear = -1

  sortedMonths.forEach((p) => {
      const isYearStart = p.year !== lastYear
      if (isYearStart) lastYear = p.year

      const dateStr = `${p.year}年${String(p.month).padStart(2, '0')}月`
      
      items.push({
        key: dateStr,
        year: p.year,
        month: p.month,
        dateStr: dateStr,
        isYearStart: isYearStart,
        isActive: activeYear === p.year && activeMonth === p.month,
        isActiveYear: activeYear === p.year
      })
  })

  return items
})

const activeItemIndex = computed(() => {
  const index = displayItems.value.findIndex(item => item.isActive)
  return index < 0 ? 0 : index
})

const mobileTrackHeight = computed(() => Math.max(1, (containerRef.value?.clientHeight ?? 400) - 72))
const mobileThumbTop = computed(() => {
  const count = displayItems.value.length
  return count <= 1 ? 16 : 16 + activeItemIndex.value / (count - 1) * mobileTrackHeight.value
})

// Click logic
const handleItemClick = (e: MouseEvent) => {
  if (isMobile.value) return
  updatePosition(e.clientY)
  if (hoveredDate.value) {
    emit('select', hoveredDate.value)
  }
}

// Pointer / Tooltip style
const pointerStyle = computed(() => ({
  transform: `translateY(${pointerTop.value-15}px)`
}))

const tooltipStyle = computed(() => ({
  top: `${tooltipTop.value}px`,
  left: `calc(100vw - 140px)`,
}))

// Find closest item
const findClosestItem = (y: number) => {
  let closestKey: string | null = null
  let minDistance = Infinity

  for (const [key, el] of itemRefs.value.entries()) {
    const rect = el.getBoundingClientRect()
    const containerRect = containerRef.value!.getBoundingClientRect()
    const itemCenter = (rect.top - containerRect.top) + rect.height / 2

    const dist = Math.abs(y - itemCenter)
    if (dist < minDistance) {
      minDistance = dist
      closestKey = key
    }
  }
  return { key: closestKey }
}

// Instant update hovered date
const updateHoveredDate = (key: string | null) => {
  if (!key) {
    hoveredDate.value = null
    return
  }
  const item = displayItems.value.find(i => i.key === key)
  hoveredDate.value = item ? item.dateStr : null
}

let rafId: number | null = null

const updatePosition = (clientY: number) => {
  if (!containerRef.value) return

  const containerRect = containerRef.value.getBoundingClientRect()
  const y = clientY - containerRect.top

  if (y < 0 || y > containerRect.height) {
    isHovering.value = false
    return
  }

  isHovering.value = true
  pointerTop.value = y
  tooltipTop.value = clientY - 10

  const { key } = findClosestItem(y)
  updateHoveredDate(key)
}

const handleMouseMove = (e: MouseEvent) => {
  if (rafId) cancelAnimationFrame(rafId)
  rafId = requestAnimationFrame(() => updatePosition(e.clientY))
}

const handleMouseLeave = () => {
  isHovering.value = false
  hoveredDate.value = null
  if (rafId) cancelAnimationFrame(rafId)
}

const handleTouchStart = (e: TouchEvent) => {
  e.preventDefault()
  mobileDragging.value = isMobile.value
  if (e.touches.length > 0) {
    if (isMobile.value) updateMobilePosition(e.touches[0].clientY, true)
    else updatePosition(e.touches[0].clientY)
  }
}

const handleTouchMove = (e: TouchEvent) => {
  e.preventDefault()
  if (rafId) cancelAnimationFrame(rafId)
  rafId = requestAnimationFrame(() => {
    if (e.touches.length > 0) {
      if (isMobile.value) updateMobilePosition(e.touches[0].clientY, true)
      else updatePosition(e.touches[0].clientY)
    }
  })
}

const handleTouchEnd = (e: TouchEvent) => {
  e.preventDefault()
  if (!isMobile.value && hoveredDate.value) {
    emit('select', hoveredDate.value)
  }
  mobileDragging.value = false
  
  // Small delay before hiding to provide visual feedback
  setTimeout(() => {
    isHovering.value = false
    hoveredDate.value = null
  }, 200)
}

const updateMobilePosition = (clientY: number, select: boolean) => {
  const rect = containerRef.value?.getBoundingClientRect()
  if (!rect || !displayItems.value.length) return
  const ratio = Math.max(0, Math.min(1, (clientY - rect.top - 16) / Math.max(1, rect.height - 32)))
  const index = Math.round(ratio * (displayItems.value.length - 1))
  const item = displayItems.value[index]
  hoveredDate.value = item.dateStr
  tooltipTop.value = Math.max(20, Math.min(window.innerHeight - 40, clientY - 12))
  if (select) emit('select', item.dateStr, 'auto')
}

const showMobileTimeline = () => {
  if (!isMobile.value || mobileDragging.value) return
  mobileVisible.value = true
  if (mobileHideTimer) clearTimeout(mobileHideTimer)
  mobileHideTimer = setTimeout(() => {
    if (!mobileDragging.value) mobileVisible.value = false
  }, 900)
}

const handleResize = () => {
  isMobile.value = window.innerWidth < 768
}

onMounted(() => {
  const main = document.querySelector<HTMLElement>('main')
  scrollElement = main && getComputedStyle(main).overflowY === 'auto' ? main : window
  scrollElement.addEventListener('scroll', showMobileTimeline, { passive: true })
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  if (rafId) cancelAnimationFrame(rafId)
  if (mobileHideTimer) clearTimeout(mobileHideTimer)
  scrollElement?.removeEventListener('scroll', showMobileTimeline)
  window.removeEventListener('resize', handleResize)
})
</script>

<style scoped>
.no-scrollbar::-webkit-scrollbar {
  display: none;
}
.no-scrollbar {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
</style>
