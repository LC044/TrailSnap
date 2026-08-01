<template>
  <div ref="containerRef" class="relative w-full h-full overflow-hidden">
    <canvas
      ref="canvasRef"
      :class="[
        'block touch-none select-none',
        interactive
          ? hoverRegion
            ? 'cursor-pointer'
            : zoom > 1
              ? 'cursor-grab'
              : 'cursor-default'
          : 'cursor-default',
      ]"
      @mousemove="handlePointerMove"
      @mouseleave="handlePointerLeave"
      @pointerdown="onPointerDown"
      @click="handleClick"
      @touchstart="onTouchStart"
      @wheel.prevent="onWheel"
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

/* ----------------------- 缩放 / 平移（自建手势层） ----------------------- */
// zoom/pan 是 screen↔world 映射的独立变换层，不改世界坐标（geometries/cells），
// 也不触发 useMapPuzzle.resize()（那是容器 CSS 尺寸变化用的重投影）。
// 仅在 draw() 里用 ctx.translate/scale 包住 renderPuzzle 应用变换。
const DPR = window.devicePixelRatio || 1
const MIN_ZOOM = 1
const MAX_ZOOM = 5
const zoom = ref(1)
const panX = ref(0)
const panY = ref(0)

const clampZoom = (z: number) => Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, z))

/** 屏幕坐标（canvas CSS 像素）→ 世界坐标（renderPuzzle 绘制空间） */
const screenToWorld = (sx: number, sy: number) => ({
  x: (sx - panX.value) / zoom.value,
  y: (sy - panY.value) / zoom.value,
})

/**
 * 以给定屏幕锚点缩放：保持锚点指向的世界点在缩放后仍位于该屏幕位置。
 * 公式 world = (anchor - pan) / oldZoom；pan_new = anchor - world * newZoom。
 */
const zoomAt = (newZoom: number, anchorScreenX: number, anchorScreenY: number) => {
  const z = clampZoom(newZoom)
  const world = screenToWorld(anchorScreenX, anchorScreenY)
  panX.value = anchorScreenX - world.x * z
  panY.value = anchorScreenY - world.y * z
  zoom.value = z
  // 缩回 1× 时归位，禁用平移
  if (z === MIN_ZOOM) {
    panX.value = 0
    panY.value = 0
  }
}

/**
 * 全国图与单省图各自维护独立的缩放/平移状态。
 * 否则在全国图放大后下钻进省，省图会继承全国的缩放率与平移量，
 * 而两者的世界坐标空间完全不同 → 画面跑偏、体验割裂。
 * 切换 scope 时存当前状态、恢复目标状态（未访问过则归 1×）。
 */
const scopeZoomState = new Map<string, { zoom: number; panX: number; panY: number }>()

/** 保存指定 scope 的缩放/平移状态。必须传 prev：watch 回调触发时 props.scope 已是 next。 */
const saveScopeZoom = (scope: string) => {
  scopeZoomState.set(scope, {
    zoom: zoom.value,
    panX: panX.value,
    panY: panY.value,
  })
}

const restoreScopeZoom = (nextScope: string) => {
  const saved = scopeZoomState.get(nextScope)
  zoom.value = saved?.zoom ?? MIN_ZOOM
  panX.value = saved?.panX ?? 0
  panY.value = saved?.panY ?? 0
}

// scope 切换（全国↔单省）：存上一级状态、恢复目标级状态（未访问过则归 1×），再重绘
watch(
  () => props.scope,
  (next, prev) => {
    if (prev) saveScopeZoom(prev)
    restoreScopeZoom(next)
    draw()
  }
)

/** 执行绘制 */
const draw = () => {
  const ctx = ctxRef.value
  if (!ctx) return
  // setupCanvas 会 setTransform(dpr,...)，resize 后变换被抹掉；此处每次重置并重应用 zoom/pan。
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0)
  ctx.clearRect(0, 0, size.width, size.height)
  if (theme.value.background) {
    ctx.fillStyle = theme.value.background
    ctx.fillRect(0, 0, size.width, size.height)
  }
  ctx.save()
  ctx.translate(panX.value, panY.value)
  ctx.scale(zoom.value, zoom.value)
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
  ctx.restore()
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

  // 命中测试用世界坐标（逆变换）；tooltip 是 DOM overlay，仍用屏幕坐标定位
  const w = screenToWorld(x, y)
  const hit = findRegionAt(w.x, w.y, props.geometries)
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
  // 拖动产生的位移不触发点击（平移 vs 下钻/选格区分）
  if (dragMoved.value) {
    dragMoved.value = false
    return
  }
  const canvas = canvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const x = e.clientX - rect.left
  const y = e.clientY - rect.top
  // 命中测试用世界坐标（逆变换），保证放大/平移后点视觉指向的区域
  const w = screenToWorld(x, y)

  // 全国图：点省下钻（格子太小不做编辑）。
  // 单省图：整省都是点亮的，findRegionAt 必然命中本省；要让格子可点，
  // 必须先判格子命中，点中格子就走编辑，否则才按区域处理。
  if (props.scope === 'province') {
    const index = props.cells.findIndex(
      (c) => w.x >= c.x && w.x <= c.x + c.size && w.y >= c.y && w.y <= c.y + c.size
    )
    if (index >= 0) {
      emit('select-cell', index)
      return
    }
  }

  const hit = findRegionAt(w.x, w.y, props.geometries)
  // 未点亮的省份不允许下钻（进去必然是空拼图）
  if (hit && litRegions.value.has(hit.name)) {
    emit('select-region', hit.name)
  }
}

/* ----------------------- 手势：单指拖拽 / 双指捏合 / 滚轮 ----------------------- */
// 单指/鼠标用 Pointer Events（统一鼠标+触摸，move 阈值区分点击 vs 拖拽平移）；
// 双指用 Touch Events（仓内多点触控约定 touches.length，passive:false 阻止页面滚动）。
const dragMoved = ref(false)
let activePointerId = -1
let dragOrigin = { x: 0, y: 0, panX: 0, panY: 0 }

const onPointerMove = (e: PointerEvent) => {
  if (activePointerId !== e.pointerId) return
  // 1× 时禁用平移（zoom 归 1 时 pan 已锁 0）
  if (zoom.value <= MIN_ZOOM) return
  const dx = e.clientX - dragOrigin.x
  const dy = e.clientY - dragOrigin.y
  if (Math.abs(dx) > 3 || Math.abs(dy) > 3) dragMoved.value = true
  panX.value = dragOrigin.panX + dx
  panY.value = dragOrigin.panY + dy
  draw()
}

const onPointerUp = (e: PointerEvent) => {
  if (activePointerId !== e.pointerId) return
  activePointerId = -1
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  window.removeEventListener('pointercancel', onPointerUp)
}

const onPointerDown = (e: PointerEvent) => {
  if (e.button !== 0 && e.pointerType === 'mouse') return
  activePointerId = e.pointerId
  dragMoved.value = false
  dragOrigin = { x: e.clientX, y: e.clientY, panX: panX.value, panY: panY.value }
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
  window.addEventListener('pointercancel', onPointerUp)
}

// --- 双指捏合 ---
let pinchInitialDist = 0
let pinchStartZoom = 1
let pinchAnchorScreen = { x: 0, y: 0 }   // 相对 canvas 的屏幕坐标
let canvasRectCache: DOMRect | null = null
const isPinching = ref(false)

const onTouchMove = (e: TouchEvent) => {
  if (!isPinching.value || e.touches.length !== 2) return
  e.preventDefault()
  const a = e.touches[0]
  const b = e.touches[1]
  const dist = Math.hypot(b.clientX - a.clientX, b.clientY - a.clientY)
  if (pinchInitialDist <= 0) return
  const newZoom = clampZoom(pinchStartZoom * (dist / pinchInitialDist))
  // 以手势中点为锚缩放：该世界点保持在屏幕原位
  zoomAt(newZoom, pinchAnchorScreen.x, pinchAnchorScreen.y)
  draw()
}

const onTouchEnd = () => {
  isPinching.value = false
  pinchInitialDist = 0
  window.removeEventListener('touchmove', onTouchMove)
  window.removeEventListener('touchend', onTouchEnd)
  window.removeEventListener('touchcancel', onTouchEnd)
  if (zoom.value === MIN_ZOOM) {
    panX.value = 0
    panY.value = 0
    draw()
  }
}

const onTouchStart = (e: TouchEvent) => {
  if (e.touches.length !== 2) return
  e.preventDefault()
  const a = e.touches[0]
  const b = e.touches[1]
  pinchInitialDist = Math.hypot(b.clientX - a.clientX, b.clientY - a.clientY)
  pinchStartZoom = zoom.value
  const canvas = canvasRef.value
  canvasRectCache = canvas ? canvas.getBoundingClientRect() : null
  const rect = canvasRectCache
  if (rect) {
    pinchAnchorScreen = {
      x: (a.clientX + b.clientX) / 2 - rect.left,
      y: (a.clientY + b.clientY) / 2 - rect.top,
    }
  }
  isPinching.value = true
  window.addEventListener('touchmove', onTouchMove, { passive: false })
  window.addEventListener('touchend', onTouchEnd)
  window.addEventListener('touchcancel', onTouchEnd)
}

// --- 滚轮（桌面）---
const onWheel = (e: WheelEvent) => {
  const canvas = canvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const delta = e.deltaY > 0 ? -0.1 : 0.1
  // 以鼠标位置为锚缩放
  zoomAt(zoom.value + delta, e.clientX - rect.left, e.clientY - rect.top)
  draw()
}

/** 复位缩放/平移（供父组件切省/换一批后调用） */
const resetZoom = () => {
  zoom.value = MIN_ZOOM
  panX.value = 0
  panY.value = 0
  draw()
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
  // 手势监听兜底清理（正常路径在 up/end 时已移除）
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  window.removeEventListener('pointercancel', onPointerUp)
  window.removeEventListener('touchmove', onTouchMove)
  window.removeEventListener('touchend', onTouchEnd)
  window.removeEventListener('touchcancel', onTouchEnd)
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
  /** 复位缩放/平移到 1× */
  resetZoom,
})
</script>
