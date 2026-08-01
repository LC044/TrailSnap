<template>
  <div ref="containerRef" class="relative w-full h-full overflow-hidden">
    <canvas
      ref="canvasRef"
      :class="[
        'block',
        interactive ? (hoverRegion ? 'cursor-pointer' : 'cursor-default') : 'cursor-default',
      ]"
      @mousemove="handlePointerMove"
      @mouseleave="handlePointerLeave"
      @click="handleClick"
    />

    <!-- hover 提示浮层 -->
    <div
      v-if="hoverRegion && tooltip.visible"
      class="pointer-events-none absolute z-20 px-2.5 py-1.5 rounded-lg bg-gray-900/90 dark:bg-gray-800/95 text-white text-xs font-medium shadow-lg whitespace-nowrap"
      :style="{ left: `${tooltip.x}px`, top: `${tooltip.y}px`, transform: 'translate(-50%, -130%)' }"
    >
      {{ hoverRegion }}
      <span class="text-gray-300 dark:text-gray-400">
        · {{ regionCounts.get(hoverRegion) ?? 0 }} 张
      </span>
    </div>

    <!-- 加载进度 -->
    <div
      v-if="showProgress"
      class="absolute bottom-3 left-1/2 -translate-x-1/2 z-20 px-3 py-1.5 rounded-full bg-white/90 dark:bg-gray-800/90 backdrop-blur-sm shadow-md text-xs text-gray-600 dark:text-gray-300 flex items-center gap-2"
    >
      <span class="w-3 h-3 rounded-full border-2 border-primary-500 border-t-transparent animate-spin" />
      正在加载照片 {{ loader.loadedCount.value }} / {{ loader.totalCount.value }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { findRegionAt, type RegionGeometry } from '@/utils/mapPuzzle/geoPath'
import type { PuzzleCell } from '@/utils/mapPuzzle/gridFill'
import {
  DARK_THEME,
  LIGHT_THEME,
  renderPuzzle,
  setupCanvas,
  type RenderTheme,
} from '@/utils/mapPuzzle/renderer'
import { usePuzzleImageLoader } from '@/composables/usePuzzleImageLoader'
import { injectTheme } from '@/composables/useTheme'
import type { PuzzleScope } from '@/composables/useMapPuzzle'

const props = defineProps<{
  geometries: RegionGeometry[]
  cells: PuzzleCell[]
  assignments: (string | null)[]
  regionCounts: Map<string, number>
  showLabel: boolean
  /** 当前层级：全国图点省下钻，单省图点格子编辑 */
  scope: PuzzleScope
  /** 是否响应 hover / 点击（全国图开启，单省图用于换图） */
  interactive?: boolean
  /** 缩略图尺寸：全国图用 small，单省用 medium */
  thumbnailSize?: 'small' | 'medium'
}>()

const emit = defineEmits<{
  (e: 'select-region', name: string): void
  (e: 'select-cell', index: number): void
  (e: 'resize', width: number, height: number): void
}>()

const containerRef = ref<HTMLDivElement | null>(null)
const canvasRef = ref<HTMLCanvasElement | null>(null)
const ctxRef = ref<CanvasRenderingContext2D | null>(null)

const hoverRegion = ref<string | null>(null)
const tooltip = reactive({ visible: false, x: 0, y: 0 })

const size = reactive({ width: 0, height: 0 })

const loader = usePuzzleImageLoader({
  concurrency: 8,
  size: props.thumbnailSize ?? 'small',
})

const showProgress = computed(
  () => loader.totalCount.value > 0 && loader.loadedCount.value < loader.totalCount.value
)

// 暗色模式跟随 html.dark，与项目其他地方保持一致
const isDark = ref(document.documentElement.classList.contains('dark'))
let darkObserver: MutationObserver | null = null

// 主题色用于描边跟随用户选择的主题
const { currentTheme } = injectTheme()

const theme = computed<RenderTheme>(() => {
  const base = isDark.value ? DARK_THEME : LIGHT_THEME
  return {
    ...base,
    // 轮廓描边使用主题色，比纯白更有辨识度
    stroke: currentTheme.value?.primary ?? base.stroke,
    glow: `rgba(${currentTheme.value?.rgb ?? '56,189,248'},0.45)`,
  }
})

/**
 * 已点亮（有格子且分到照片）的区域集合。
 * 由 cells + assignments 反推，无需父组件额外传参。
 */
const litRegions = computed(() => {
  const set = new Set<string>()
  for (let i = 0; i < props.cells.length; i++) {
    if (props.assignments[i]) set.add(props.cells[i].regionName)
  }
  return set
})

/** 执行绘制 */
const draw = () => {
  const ctx = ctxRef.value
  if (!ctx) return
  renderPuzzle({
    ctx,
    width: size.width,
    height: size.height,
    geometries: props.geometries,
    cells: props.cells,
    assignments: props.assignments,
    resolveImage: loader.resolveImage,
    options: {
      showLabel: props.showLabel,
      hoverRegion: hoverRegion.value,
      litRegions: litRegions.value,
      theme: theme.value,
    },
  })
}

/** 初始化 / 重建画布（尺寸或 dpr 变化时） */
const setup = () => {
  const canvas = canvasRef.value
  if (!canvas || size.width <= 0 || size.height <= 0) return
  ctxRef.value = setupCanvas(canvas, size.width, size.height)
  draw()
}

/** 请求当前分配用到的照片，到货后批量重绘 */
const requestImages = () => {
  if (!props.assignments.length) return
  loader.request(props.assignments, draw)
}

const handlePointerMove = (e: MouseEvent) => {
  if (!props.interactive) return
  const canvas = canvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const x = e.clientX - rect.left
  const y = e.clientY - rect.top

  const hit = findRegionAt(x, y, props.geometries)
  // 只对已点亮的省份响应 hover —— 没去过的省点进去是空拼图，没有意义
  const nextName = hit && litRegions.value.has(hit.name) ? hit.name : null

  tooltip.x = x
  tooltip.y = y
  tooltip.visible = !!nextName

  if (nextName !== hoverRegion.value) {
    hoverRegion.value = nextName
    draw()
  }
}

const handlePointerLeave = () => {
  tooltip.visible = false
  if (hoverRegion.value !== null) {
    hoverRegion.value = null
    draw()
  }
}

const handleClick = (e: MouseEvent) => {
  if (!props.interactive) return
  const canvas = canvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const x = e.clientX - rect.left
  const y = e.clientY - rect.top

  // 全国图：点省下钻（格子太小不做编辑）。
  // 单省图：整省都是点亮的，findRegionAt 必然命中本省；要让格子可点，
  // 必须先判格子命中，点中格子就走编辑，否则才按区域处理。
  if (props.scope === 'province') {
    const index = props.cells.findIndex(
      (c) => x >= c.x && x <= c.x + c.size && y >= c.y && y <= c.y + c.size
    )
    if (index >= 0) {
      emit('select-cell', index)
      return
    }
  }

  const hit = findRegionAt(x, y, props.geometries)
  // 未点亮的省份不允许下钻（进去必然是空拼图）
  if (hit && litRegions.value.has(hit.name)) {
    emit('select-region', hit.name)
  }
}

let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  const container = containerRef.value
  if (!container) return

  resizeObserver = new ResizeObserver((entries) => {
    const entry = entries[0]
    if (!entry) return
    const { width, height } = entry.contentRect
    if (width <= 0 || height <= 0) return
    size.width = width
    size.height = height
    setup()
    emit('resize', width, height)
  })
  resizeObserver.observe(container)

  // 监听 html.dark 变化以切换主题
  darkObserver = new MutationObserver(() => {
    const next = document.documentElement.classList.contains('dark')
    if (next !== isDark.value) {
      isDark.value = next
      draw()
    }
  })
  darkObserver.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['class'],
  })
})

onUnmounted(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  darkObserver?.disconnect()
  darkObserver = null
})

// 几何/格子变化 → 重绘 + 拉图
watch(
  () => [props.geometries, props.cells, props.assignments],
  () => {
    draw()
    requestImages()
  },
  { deep: false }
)

// 纯样式参数变化 → 只重绘，不重新拉图
watch(() => props.showLabel, draw)

// 主题色变化 → 重绘（JS 驱动的绘制不会自动响应主题类）
watch(currentTheme, draw)

defineExpose({
  /** 供父组件导出图片时取用（后续导出功能预留） */
  getCanvas: () => canvasRef.value,
  redraw: draw,
})
</script>
