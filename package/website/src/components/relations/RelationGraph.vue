<template>
  <div class="relative" :class="fullscreen ? 'h-full min-h-0' : 'h-[590px]'">
    <svg
      ref="canvas"
      class="h-full w-full cursor-grab touch-none select-none active:cursor-grabbing"
      :style="{ '--graph-primary': theme.currentTheme.value.primary, '--graph-rgb': theme.currentTheme.value.rgb }"
      role="img"
      aria-label="可平移缩放的关系画布。点击节点展开下一层关系，按 Tab 可逐个选择节点。"
      @pointerdown="startDrag"
      @pointermove="drag"
      @pointerup="stopDrag"
      @pointercancel="stopDrag"
      @wheel.prevent="wheel"
    >
      <defs>
        <clipPath id="relation-person-portrait"><circle cx="0" cy="0" r="27" /></clipPath>
        <clipPath id="relation-photo-crop"><rect x="-27" y="-27" width="54" height="54" rx="8" /></clipPath>
        <filter id="relation-node-glow" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="7" />
        </filter>
      </defs>
      <g :transform="`translate(${width / 2 + panX} ${height / 2 + panY}) scale(${zoom})`">
        <g v-for="edge in visibleEdges" :key="`${edge.source}|${edge.target}`">
          <line
            :x1="positions[edge.source]?.x || 0" :y1="positions[edge.source]?.y || 0"
            :x2="positions[edge.target]?.x || 0" :y2="positions[edge.target]?.y || 0"
            :stroke="theme.currentTheme.value.primary"
            :stroke-width="edgeWidth(edge)"
            :stroke-opacity="edgeOpacity(edge)"
            :stroke-dasharray="edge.photo_count ? undefined : '5 5'"
            stroke-linecap="round"
          />
        </g>
        <g
          v-for="node in nodes" :key="node.id"
          :transform="`translate(${positions[node.id]?.x || 0} ${positions[node.id]?.y || 0})`"
          class="graph-node cursor-pointer outline-none"
          :class="{ 'is-focused': focusId === node.id }"
          role="button" tabindex="0"
          :aria-label="`${node.label}，${expanded.includes(node.id) ? (cursors[node.id] ? '继续展开' : '已展开') : '点击展开关系'}`"
          @click.stop="pick(node)"
          @keydown.enter.prevent="pick(node)"
          @keydown.space.prevent="pick(node)"
          @mouseenter="emit('inspect', node)"
          @focus="emit('inspect', node)"
        >
          <circle v-if="focusId === node.id || node.id === rootId" r="37" fill="none" :stroke="theme.currentTheme.value.primary" :stroke-width="node.id === rootId ? 3 : 2" opacity="0.95" />
          <template v-if="node.type === 'place'">
            <path :d="node.id === rootId ? 'M 0 -28 L 28 0 L 0 28 L -28 0 Z' : 'M 0 -19 L 19 0 L 0 19 L -19 0 Z'" :fill="node.id === rootId ? theme.currentTheme.value.primary : '#112438'" :stroke="theme.currentTheme.value.primary" stroke-width="2" />
            <text v-if="node.id === rootId" text-anchor="middle" dominant-baseline="middle" fill="white" font-size="11">地点</text>
          </template>
          <template v-else-if="node.type === 'person'">
            <circle r="29" fill="#223044" :stroke="theme.currentTheme.value.primary" stroke-width="3" />
            <image v-if="node.photo_id && !failedImages.has(node.id)" :href="thumbnailUrl(node.photo_id, 'small')" x="-27" y="-27" width="54" height="54" preserveAspectRatio="xMidYMid slice" clip-path="url(#relation-person-portrait)" @error="failedImages.add(node.id)" />
            <text v-else text-anchor="middle" dominant-baseline="middle" fill="white" font-size="24">◉</text>
          </template>
          <template v-else>
            <rect x="-29" y="-29" width="58" height="58" rx="9" fill="#223044" :stroke="theme.currentTheme.value.primary" stroke-width="2" />
            <image v-if="node.photo_id && !failedImages.has(node.id)" :href="thumbnailUrl(node.photo_id, 'small')" x="-27" y="-27" width="54" height="54" preserveAspectRatio="xMidYMid slice" clip-path="url(#relation-photo-crop)" @error="failedImages.add(node.id)" />
            <text v-else text-anchor="middle" dominant-baseline="middle" fill="white" font-size="24">{{ node.type === 'memory' ? '✧' : '▧' }}</text>
          </template>
          <circle v-if="loadingId === node.id" r="34" fill="none" :stroke="theme.currentTheme.value.primary" stroke-width="2" stroke-dasharray="5 5" class="loading-ring" />
          <circle v-if="expanded.includes(node.id) && !cursors[node.id]" cx="28" cy="-28" r="7" :fill="theme.currentTheme.value.primary" />
          <text class="node-label" text-anchor="middle" y="49" fill="white" font-size="12" :font-weight="node.id === rootId ? 700 : 500">{{ nodeLabel(node) }}</text>
        </g>
      </g>
    </svg>
    <div class="absolute bottom-3 left-0 z-10 flex flex-wrap items-center gap-2">
      <button class="graph-button" aria-label="缩小关系图" @click="scale(0.8)">−</button>
      <button class="graph-button" aria-label="放大关系图" @click="scale(1.25)">＋</button>
      <button class="graph-button" @click="fit">适应画布</button>
    </div>
    <p class="pointer-events-none absolute bottom-4 right-0 hidden text-xs text-white/60 xl:block">
      拖动探索 · 滚轮缩放 · 点击节点展开下一层
    </p>
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { injectTheme } from '@/composables/useTheme'
import { thumbnailUrl } from '@/utils/mediaUrl'
import type { CanvasPoint } from '@/stores/relationStore'
import type { RelationEdge, RelationNode } from '@/types/relations'

const props = defineProps<{
  nodes: RelationNode[]
  edges: RelationEdge[]
  positions: Record<string, CanvasPoint>
  expanded: string[]
  cursors: Record<string, string | null>
  rootId: string
  loadingId: string
  zoom: number
  pan: number[] | null
  focusId: string | null
  fullscreen: boolean
}>()
const emit = defineEmits<{
  choose: [node: RelationNode]
  inspect: [node: RelationNode]
  zoom: [value: number]
  pan: [value: number[]]
}>()
const theme = injectTheme()
const canvas = ref<SVGSVGElement>()
const width = ref(800)
const height = ref(590)
const failedImages = ref(new Set<string>())
let observer: ResizeObserver | null = null
let fittedOnMount = false
let pointer: { id: number; x: number; y: number; panX: number; panY: number; moved: boolean } | null = null
const panX = computed(() => props.pan?.[0] || 0)
const panY = computed(() => props.pan?.[1] || 0)
const zoom = computed(() => props.zoom)
const visibleEdges = computed(() => props.edges.filter((edge) => props.positions[edge.source] && props.positions[edge.target]))
function edgeWidth(edge: RelationEdge) { return Math.min(3.5, 1 + Math.log2(1 + edge.photo_count + edge.memory_count) * 0.4) }
function edgeOpacity(edge: RelationEdge) {
  return props.focusId
    ? edge.source === props.focusId || edge.target === props.focusId ? 0.95 : 0.16
    : Math.min(0.68, 0.24 + Math.log2(1 + edge.photo_count + edge.memory_count) * 0.08)
}
function shortLabel(label: string) { return label.length > 12 ? `${label.slice(0, 11)}…` : label }
function nodeLabel(node: RelationNode) {
  if (node.type === 'photo') {
    const date = node.subtitle.match(/(\d{4})年(\d{1,2})月(\d{1,2})日/)
    return date ? `${date[1]}.${date[2].padStart(2, '0')}.${date[3].padStart(2, '0')}` : '照片'
  }
  return shortLabel(node.label)
}
function pick(node: RelationNode) { if (!pointer?.moved) emit('choose', node) }
function startDrag(event: PointerEvent) {
  if (event.button !== 0 || !canvas.value || (event.target as Element).closest('.graph-node')) return
  pointer = { id: event.pointerId, x: event.clientX, y: event.clientY, panX: panX.value, panY: panY.value, moved: false }
  canvas.value.setPointerCapture(event.pointerId)
}
function drag(event: PointerEvent) {
  if (!pointer || pointer.id !== event.pointerId) return
  const dx = event.clientX - pointer.x, dy = event.clientY - pointer.y
  if (Math.abs(dx) + Math.abs(dy) > 3) pointer.moved = true
  emit('pan', [pointer.panX + dx, pointer.panY + dy])
}
function stopDrag(event: PointerEvent) {
  if (pointer?.id === event.pointerId) pointer = null
}
function scale(factor: number) { emit('zoom', Math.max(0.25, Math.min(3, zoom.value * factor))) }
function wheel(event: WheelEvent) {
  if (!canvas.value) return
  const rect = canvas.value.getBoundingClientRect()
  const x = event.clientX - rect.left - width.value / 2
  const y = event.clientY - rect.top - height.value / 2
  const next = Math.max(0.25, Math.min(3, zoom.value * (event.deltaY < 0 ? 1.12 : 1 / 1.12)))
  emit('pan', [x - ((x - panX.value) / zoom.value) * next, y - ((y - panY.value) / zoom.value) * next])
  emit('zoom', next)
}
function fit() {
  const points = Object.values(props.positions)
  if (!points.length) return
  const xs = points.map((point) => point.x), ys = points.map((point) => point.y)
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys)
  const next = Math.max(0.25, Math.min(1.35, Math.min((width.value - 80) / Math.max(1, maxX - minX + 70), (height.value - 80) / Math.max(1, maxY - minY + 70))))
  emit('zoom', next)
  emit('pan', [-(minX + maxX) * next / 2, -(minY + maxY) * next / 2])
}
onMounted(() => {
  if (!canvas.value) return
  observer = new ResizeObserver(([entry]) => {
    width.value = entry.contentRect.width
    height.value = entry.contentRect.height
    if (!fittedOnMount) {
      fittedOnMount = true
      if (props.zoom === 1 && (!props.pan || props.pan.every((value) => value === 0))) fit()
    }
  })
  observer.observe(canvas.value)
})
onBeforeUnmount(() => observer?.disconnect())
</script>
<style scoped>
.graph-button { @apply min-h-10 rounded-xl border border-white/20 bg-white/10 px-3 text-sm text-white backdrop-blur transition hover:bg-white/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white; }
.graph-node:hover .node-label, .graph-node.is-focused .node-label, .graph-node:focus-visible .node-label { fill: var(--graph-primary); }
.graph-node:focus-visible { outline: none; }
.loading-ring { animation: spin 1.2s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
