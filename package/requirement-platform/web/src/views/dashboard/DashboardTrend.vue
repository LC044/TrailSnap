<template>
  <article class="panel trend-card">
    <div class="card-head">
      <div class="card-title"><h2>新增趋势</h2><p>近 {{ range }} 天 · 共 {{ sumCount }} 条新增需求</p></div>
      <div class="card-actions">
        <div class="seg" role="group" aria-label="图表类型">
          <button v-for="item in modes" :key="item.key" type="button" :class="{ active: mode === item.key }"
            :disabled="item.key === 'stack' && !hasTypes" :aria-pressed="mode === item.key" @click="setMode(item.key)">{{ item.label }}</button>
        </div>
        <el-button size="small" text :disabled="!sliced.length" @click="exportCsv">导出</el-button>
        <el-button size="small" text @click="showTable = !showTable">{{ showTable ? '看图' : '明细' }}</el-button>
      </div>
    </div>

    <div class="trend-stats">
      <span>日均 <strong>{{ average }}</strong> 条</span>
      <span>峰值 <strong>{{ peak.count }}</strong> 条<small v-if="peak.date"> · {{ shortDate(peak.date) }}</small></span>
      <span v-if="deltaPct !== null">较前 {{ range }} 天 <strong :class="deltaPct >= 0 ? 'up' : 'down'">{{ deltaPct >= 0 ? '+' : '' }}{{ deltaPct }}%</strong></span>
      <span v-else class="muted">暂无上期数据</span>
    </div>

    <div v-show="!showTable" ref="wrap" class="trend-wrap" @pointerleave="hoverIndex = null">
      <svg v-if="width > 0 && sliced.length" :width="width" :height="height" class="trend-svg" tabindex="0" role="img"
        :aria-label="`近 ${range} 天每日新增需求趋势图，共 ${sumCount} 条，日均 ${average} 条`"
        @pointermove="onMove" @pointerdown="onMove" @keydown.left.prevent="moveHover(-1)" @keydown.right.prevent="moveHover(1)" @keydown.esc="hoverIndex = null">
        <defs>
          <linearGradient id="rp-trend-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#2563eb" stop-opacity=".24" />
            <stop offset="100%" stop-color="#2563eb" stop-opacity="0" />
          </linearGradient>
        </defs>
        <g>
          <line v-for="tick in ticks" :key="`grid-${tick}`" :x1="padL" :x2="width - padR" :y1="yAt(tick)" :y2="yAt(tick)" class="gridline" />
          <text v-for="tick in ticks" :key="`tick-${tick}`" :x="padL - 8" :y="yAt(tick)" dy="4" text-anchor="end" class="tick-label">{{ tick }}</text>
        </g>
        <g>
          <text v-for="index in xLabelIndices" :key="`x-${index}`" :x="xAt(index)" :y="height - 8" text-anchor="middle" class="tick-label">{{ shortDate(sliced[index]!.date) }}</text>
        </g>
        <template v-if="mode === 'area'">
          <path :d="areaPath" fill="url(#rp-trend-fill)" />
          <path :d="linePath" class="trend-line" />
          <template v-if="range <= 14">
            <circle v-for="(point, index) in sliced" :key="`dot-${point.date}`" :cx="xAt(index)" :cy="yAt(point.count)" r="3" class="trend-dot" />
          </template>
        </template>
        <template v-else-if="mode === 'bar'">
          <rect v-for="bar in bars" :key="bar.key" :x="bar.x" :y="bar.y" :width="barWidth" :height="bar.h" rx="3"
            class="trend-bar" :class="{ dim: hoverIndex !== null && hoverIndex !== bar.index }" fill="#2563eb" />
        </template>
        <template v-else>
          <rect v-for="seg in stackBars" :key="seg.key" :x="seg.x" :y="seg.y" :width="barWidth" :height="seg.h" rx="2"
            :fill="seg.color" class="trend-seg" :opacity="hoverIndex !== null && hoverIndex !== seg.index ? .45 : 1" />
        </template>
        <g v-if="hoverIndex !== null && sliced[hoverIndex]">
          <line :x1="xAt(hoverIndex)" :x2="xAt(hoverIndex)" :y1="padT" :y2="height - padB" class="crosshair" />
          <circle v-if="mode === 'area'" :cx="xAt(hoverIndex)" :cy="yAt(sliced[hoverIndex]!.count)" r="5" class="hover-dot" />
        </g>
      </svg>
      <p v-else class="chart-empty">暂无趋势数据</p>

      <div v-if="hoverIndex !== null && sliced[hoverIndex]" class="chart-tip" :style="tipStyle">
        <strong>{{ sliced[hoverIndex]!.date }}</strong>
        <span class="tip-total">新增 <b>{{ mode === 'stack' ? stackValue(sliced[hoverIndex]!) : sliced[hoverIndex]!.count }}</b> 条</span>
        <template v-if="mode === 'stack' && hasTypes">
          <span v-for="key in typeKeys" :key="key" class="tip-row" :style="{ opacity: visible[key] ? 1 : .35 }">
            <i :style="{ background: typeColor(key) }"></i>{{ typeLabel(key) }}：{{ typeValue(hoverIndex, key) }}
          </span>
        </template>
      </div>
    </div>

    <div v-if="mode === 'stack' && !showTable" class="chart-legend">
      <button v-for="key in typeKeys" :key="key" type="button" class="legend-item" :class="{ off: !visible[key] }" :aria-pressed="visible[key]" @click="visible[key] = !visible[key]">
        <span class="legend-swatch" :style="{ background: typeColor(key) }"></span>{{ typeLabel(key) }}
      </button>
      <span class="legend-hint">点击图例可隐藏/显示分类</span>
    </div>

    <div v-show="showTable" class="trend-table-wrap">
      <table class="trend-table">
        <thead><tr><th>日期</th><th>新增</th><th v-if="hasTypes">新功能</th><th v-if="hasTypes">体验优化</th><th v-if="hasTypes">问题修复</th><th v-if="hasTypes">其他</th></tr></thead>
        <tbody>
          <tr v-for="point in sliced" :key="point.date">
            <td>{{ point.date }}</td><td>{{ point.count }}</td>
            <template v-if="hasTypes"><td>{{ point.feature ?? 0 }}</td><td>{{ point.improvement ?? 0 }}</td><td>{{ point.bug ?? 0 }}</td><td>{{ point.other ?? 0 }}</td></template>
          </tr>
        </tbody>
      </table>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElButton } from 'element-plus'
import { downloadCsv, palette, shortDate, typeMeta, type TrendPoint } from './dashboardData'

type Mode = 'area' | 'bar' | 'stack'
const typeKeys = ['feature', 'improvement', 'bug', 'other'] as const
type TypeKey = typeof typeKeys[number]

const props = defineProps<{ points: TrendPoint[]; range: number }>()
const modes: Array<{ key: Mode; label: string }> = [
  { key: 'area', label: '折线' }, { key: 'bar', label: '柱状' }, { key: 'stack', label: '按类型' },
]
const mode = ref<Mode>('area')
const showTable = ref(false)
const visible = reactive<Record<TypeKey, boolean>>({ feature: true, improvement: true, bug: true, other: true })
const hoverIndex = ref<number | null>(null)
const wrap = ref<HTMLDivElement | null>(null)
const width = ref(0)
const height = 256
const padL = 38, padR = 14, padT = 18, padB = 28
let observer: ResizeObserver | null = null

onMounted(() => {
  observer = new ResizeObserver(entries => {
    width.value = Math.max(0, Math.floor(entries[0]?.contentRect.width ?? 0))
  })
  if (wrap.value) observer.observe(wrap.value)
})
onBeforeUnmount(() => observer?.disconnect())
watch(() => props.range, () => { hoverIndex.value = null })

const sliced = computed(() => props.points.slice(-props.range))
const hasTypes = computed(() => sliced.value.some(point => point.feature !== undefined))
const sumCount = computed(() => sliced.value.reduce((sum, point) => sum + point.count, 0))
const average = computed(() => sliced.value.length ? (sumCount.value / sliced.value.length).toFixed(1) : '0.0')
const peak = computed(() => sliced.value.reduce((best, point) => point.count > best.count ? point : best, { date: '', count: 0 }))
const previousCount = computed(() => props.points.slice(-props.range * 2, -props.range).reduce((sum, point) => sum + point.count, 0))
const deltaPct = computed(() => {
  const previous = previousCount.value
  if (!previous || props.points.length < props.range * 2) return null
  return Math.round(((sumCount.value - previous) / previous) * 100)
})

function setMode(next: Mode) {
  if (next === 'stack' && !hasTypes.value) return
  mode.value = next
  hoverIndex.value = null
}
const stackValue = (point: TrendPoint) => typeKeys.reduce((sum, key) => sum + (visible[key] ? (point[key] ?? 0) : 0), 0)
const valueAt = (point: TrendPoint) => mode.value === 'stack' ? stackValue(point) : point.count
const typeColor = (key: TypeKey) => typeMeta[key]?.color ?? palette.slate
const typeLabel = (key: TypeKey) => typeMeta[key]?.label ?? key
const typeValue = (index: number | null, key: TypeKey) => index === null ? 0 : (sliced.value[index]?.[key] ?? 0)

function niceMax(value: number) {
  if (value <= 4) return 4
  const magnitude = 10 ** Math.floor(Math.log10(value))
  const step = [1, 2, 2.5, 5, 10].map(item => item * magnitude).find(item => value / item <= 4) ?? 10 * magnitude
  return Math.max(4, Math.ceil(value / step) * step)
}
const maxValue = computed(() => niceMax(Math.max(0, ...sliced.value.map(valueAt))))
const ticks = computed(() => [0, .25, .5, .75, 1].map(fraction => {
  const value = fraction * maxValue.value
  return Number.isInteger(value) ? value : Number(value.toFixed(1))
}))

const innerW = computed(() => Math.max(1, width.value - padL - padR))
const innerH = height - padT - padB
const bandWidth = computed(() => innerW.value / Math.max(1, sliced.value.length))
const barWidth = computed(() => Math.max(2, Math.min(22, bandWidth.value * .62)))
const xAt = (index: number) => padL + (index + .5) * bandWidth.value
const yAt = (value: number) => padT + (1 - value / maxValue.value) * innerH
const baseline = computed(() => yAt(0))

const linePath = computed(() => {
  const values = sliced.value.map(point => point.count)
  const points = values.map((value, index) => ({ x: xAt(index), y: yAt(value) }))
  const clampY = (y: number) => Math.min(baseline.value, Math.max(padT, y))
  if (!points.length) return ''
  if (points.length === 1) return `M${points[0]!.x},${points[0]!.y}`
  const at = (index: number) => points[Math.min(points.length - 1, Math.max(0, index))]!
  let path = `M${at(0).x.toFixed(1)},${at(0).y.toFixed(1)}`
  for (let index = 0; index < points.length - 1; index += 1) {
    const p0 = at(index - 1), p1 = at(index), p2 = at(index + 1), p3 = at(index + 2)
    const c1x = p1.x + (p2.x - p0.x) / 6, c1y = clampY(p1.y + (p2.y - p0.y) / 6)
    const c2x = p2.x - (p3.x - p1.x) / 6, c2y = clampY(p2.y - (p3.y - p1.y) / 6)
    path += ` C${c1x.toFixed(1)},${c1y.toFixed(1)} ${c2x.toFixed(1)},${c2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`
  }
  return path
})
const areaPath = computed(() => {
  if (!sliced.value.length) return ''
  return `${linePath.value} L${xAt(sliced.value.length - 1).toFixed(1)},${baseline.value.toFixed(1)} L${xAt(0).toFixed(1)},${baseline.value.toFixed(1)} Z`
})
const bars = computed(() => sliced.value.map((point, index) => ({
  key: point.date, index, x: xAt(index) - barWidth.value / 2,
  y: yAt(point.count), h: Math.max(0, baseline.value - yAt(point.count)),
})))
const stackBars = computed(() => sliced.value.flatMap((point, index) => {
  let base = 0
  return typeKeys.filter(key => visible[key]).map(key => {
    const value = point[key] ?? 0
    const top = yAt(base + value), bottom = yAt(base)
    base += value
    return { key: `${point.date}-${key}`, index, x: xAt(index) - barWidth.value / 2, y: top, h: Math.max(0, bottom - top), color: typeMeta[key]!.color }
  }).filter(segment => segment.h > 0)
}))
const xLabelIndices = computed(() => {
  const step = props.range <= 7 ? 1 : props.range <= 30 ? 5 : 14
  const indices = sliced.value.map((_, index) => index).filter(index => index % step === 0)
  const last = sliced.value.length - 1
  if (last >= 0 && !indices.includes(last) && last - (indices[indices.length - 1] ?? 0) >= 3) indices.push(last)
  return indices
})

const tipStyle = computed(() => {
  const index = hoverIndex.value
  if (index === null || !sliced.value[index]) return {}
  const x = xAt(index)
  const flip = x > width.value - 150
  return { left: `${flip ? x - 142 : x + 12}px`, top: `${Math.min(height - 96, Math.max(2, yAt(valueAt(sliced.value[index]!)) - 30))}px` }
})
function onMove(event: PointerEvent) {
  const rect = (event.currentTarget as SVGSVGElement).getBoundingClientRect()
  const index = Math.floor((event.clientX - rect.left - padL) / bandWidth.value)
  hoverIndex.value = Math.min(sliced.value.length - 1, Math.max(0, index))
}
function moveHover(delta: number) {
  const current = hoverIndex.value ?? sliced.value.length - 1
  hoverIndex.value = Math.min(sliced.value.length - 1, Math.max(0, current + delta))
}

function exportCsv() {
  const header = hasTypes.value ? ['日期', '新增', '新功能', '体验优化', '问题修复', '其他'] : ['日期', '新增']
  const rows = sliced.value.map(point => hasTypes.value
    ? [point.date, point.count, point.feature ?? 0, point.improvement ?? 0, point.bug ?? 0, point.other ?? 0]
    : [point.date, point.count])
  downloadCsv(`需求新增趋势_近${props.range}天.csv`, [header, ...rows])
}
</script>

<style scoped>
.trend-card { margin-bottom: 0; min-width: 0; }
.card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.card-title h2 { margin: 0; font-size: 17px; }
.card-title p { margin: 4px 0 0; font-size: 12px; color: var(--rp-text-3); }
.card-actions { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.seg { display: inline-flex; padding: 3px; margin-right: 4px; border-radius: 9px; background: #f1f5f9; }
.seg button { min-height: 26px; padding: 0 10px; border: 0; border-radius: 7px; background: transparent; color: var(--rp-text-2); font-size: 12px; cursor: pointer; transition: background .15s, color .15s, box-shadow .15s; }
.seg button.active { background: #fff; color: var(--rp-primary); font-weight: 700; box-shadow: 0 1px 4px rgba(15,23,42,.1); }
.seg button:disabled { opacity: .4; cursor: not-allowed; }
.seg button:focus-visible { outline: 2px solid var(--rp-primary); outline-offset: 1px; }
.trend-stats { display: flex; flex-wrap: wrap; gap: 6px 18px; margin: 14px 0 6px; font-size: 12px; color: var(--rp-text-3); }
.trend-stats strong { color: var(--rp-text); font-size: 13px; font-variant-numeric: tabular-nums; }
.trend-stats strong.up { color: #16a36a; }
.trend-stats strong.down { color: #dc2626; }
.trend-stats small { font-size: 11px; }
.trend-stats .muted { color: #b6c0cf; }
.trend-wrap { position: relative; min-height: 256px; }
.trend-svg { display: block; }
.trend-svg:focus-visible { outline: 2px solid var(--rp-primary); outline-offset: 2px; border-radius: 8px; }
.trend-svg .gridline { stroke: var(--rp-border); stroke-width: 1; }
.trend-svg .tick-label { fill: var(--rp-text-3); font-size: 11px; font-variant-numeric: tabular-nums; }
.trend-svg .trend-line { fill: none; stroke: var(--rp-primary); stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round; }
.trend-svg .trend-dot { fill: #fff; stroke: var(--rp-primary); stroke-width: 2; }
.trend-svg .trend-bar, .trend-svg .trend-seg { transition: opacity .15s, fill .15s; }
.trend-svg .trend-bar:hover { fill: #1d4ed8; }
.trend-svg .trend-bar.dim { opacity: .38; }
.trend-svg .crosshair { stroke: #94a3b8; stroke-width: 1; stroke-dasharray: 3 3; }
.trend-svg .hover-dot { fill: var(--rp-primary); stroke: #fff; stroke-width: 2.5; }
.chart-tip { position: absolute; z-index: 5; min-width: 116px; pointer-events: none; display: grid; gap: 3px; padding: 8px 10px; border-radius: 10px; background: #0f172a; color: #fff; font-size: 11.5px; box-shadow: 0 8px 20px rgba(15,23,42,.25); }
.chart-tip strong { font-size: 12px; }
.chart-tip .tip-total b { font-size: 14px; }
.chart-tip .tip-row { display: flex; align-items: center; gap: 5px; opacity: .85; }
.chart-tip .tip-row i { width: 7px; height: 7px; border-radius: 2px; }
.chart-empty { margin: 90px 0; text-align: center; color: var(--rp-text-3); font-size: 13px; }
.chart-legend { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; margin-top: 4px; }
.legend-item { display: inline-flex; align-items: center; gap: 5px; padding: 3px 6px; border: 0; border-radius: 6px; background: transparent; color: var(--rp-text-2); font-size: 12px; cursor: pointer; }
.legend-item:hover { background: var(--rp-primary-soft); }
.legend-item.off { opacity: .4; text-decoration: line-through; }
.legend-swatch { width: 9px; height: 9px; border-radius: 3px; }
.legend-hint { margin-left: auto; color: #b6c0cf; font-size: 11px; }
.trend-table-wrap { max-height: 262px; overflow: auto; }
.trend-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.trend-table th, .trend-table td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--rp-border); }
.trend-table th { position: sticky; top: 0; z-index: 1; background: #fff; color: var(--rp-text-3); font-weight: 600; }
.trend-table td { color: var(--rp-text-2); font-variant-numeric: tabular-nums; }
.trend-table td:first-child { color: var(--rp-text); }
@media (max-width: 720px) {
  .card-actions { width: 100%; }
  .seg { margin-right: auto; }
  .legend-hint { display: none; }
}
</style>
