<template>
  <div class="charts-grid">
    <article class="panel chart-card trend-card">
      <div class="chart-head">
        <h2>近 30 天新增趋势</h2>
        <el-button size="small" text @click="showTrendTable = !showTrendTable">{{ showTrendTable ? '图表' : '明细' }}</el-button>
      </div>
      <div v-show="!showTrendTable" ref="trendWrap" class="trend-wrap" @pointerleave="hoverIndex = null">
        <svg
          v-if="trendWidth > 0"
          :width="trendWidth"
          :height="trendHeight"
          class="trend-svg"
          tabindex="0"
          role="img"
          :aria-label="trendAria"
          @pointermove="onTrendMove"
          @keydown.left.prevent="moveHover(-1)"
          @keydown.right.prevent="moveHover(1)"
          @keydown.esc="hoverIndex = null"
        >
          <g>
            <line v-for="tick in ticks" :key="`g-${tick}`" :x1="padL" :x2="trendWidth - padR" :y1="yTick(tick)" :y2="yTick(tick)" class="gridline" />
            <text v-for="tick in ticks" :key="`t-${tick}`" :x="padL - 8" :y="yTick(tick)" dy="4" text-anchor="end" class="tick-label">{{ tick }}</text>
          </g>
          <g>
            <text
              v-for="i in xLabelIndices"
              :key="`x-${i}`"
              :x="xAt(i)"
              :y="trendHeight - 8"
              text-anchor="middle"
              class="tick-label"
            >{{ points[i]?.date.slice(5) }}</text>
          </g>
          <path :d="areaPath" class="trend-area" />
          <path :d="linePath" class="trend-line" />
          <text v-if="lastCount > 0" :x="xAt(points.length - 1) - 6" :y="yAt(lastCount) - 10" text-anchor="end" class="end-label">{{ lastCount }}</text>
          <g v-if="hoverIndex !== null && points[hoverIndex]">
            <line :x1="xAt(hoverIndex)" :x2="xAt(hoverIndex)" :y1="padT" :y2="trendHeight - padB" class="crosshair" />
            <circle :cx="xAt(hoverIndex)" :cy="yAt(points[hoverIndex]!.count)" r="4.5" class="hover-dot" />
          </g>
        </svg>
        <div v-if="hoverIndex !== null && points[hoverIndex]" class="chart-tip" :style="tipStyle">
          <strong>{{ points[hoverIndex]!.count }}</strong>
          <span>{{ points[hoverIndex]!.date }}</span>
        </div>
      </div>
      <div v-show="showTrendTable" class="trend-table-wrap">
        <table class="trend-table">
          <thead><tr><th>日期</th><th>新增需求</th></tr></thead>
          <tbody>
            <tr v-for="point in points" :key="point.date">
              <td>{{ point.date }}</td>
              <td>{{ point.count }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </article>

    <article class="panel chart-card">
      <h2>状态分布</h2>
      <div v-for="row in statusRows" :key="row.key" class="hbar-row" :title="`${row.label}：${row.count}`">
        <span class="hbar-label">{{ row.label }}</span>
        <div class="hbar-track"><div class="hbar-fill" :style="{ width: `${row.pct}%` }"></div></div>
        <span class="hbar-value">{{ row.count }}</span>
      </div>
    </article>

    <article class="panel chart-card">
      <h2>类型分布</h2>
      <div v-for="row in typeRows" :key="row.key" class="hbar-row" :title="`${row.label}：${row.count}`">
        <span class="hbar-label">{{ row.label }}</span>
        <div class="hbar-track"><div class="hbar-fill" :style="{ width: `${row.pct}%` }"></div></div>
        <span class="hbar-value">{{ row.count }}</span>
      </div>
    </article>

    <article class="panel chart-card">
      <h2>提交人排行</h2>
      <template v-if="data.top_contributors.length">
        <div v-for="(person, index) in data.top_contributors" :key="person.user_id" class="hbar-row contrib-row" :title="`${person.name}：${person.count}`">
          <span class="hbar-label contrib-label">
            <span class="avatar contrib-avatar" :style="{ width: '22px', height: '22px', fontSize: '11px', ...avatarColor(person.name) }">{{ person.name.slice(0, 1) }}</span>
            <span class="contrib-name">{{ index + 1 }}. {{ person.name }}</span>
          </span>
          <div class="hbar-track"><div class="hbar-fill" :style="{ width: `${contributorPct(person.count)}%` }"></div></div>
          <span class="hbar-value">{{ person.count }}</span>
        </div>
      </template>
      <p v-else class="chart-empty">暂无提交人数据</p>
      <p v-if="data.anonymous" class="anon-note">另有 {{ data.anonymous }} 条匿名提交</p>
    </article>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElButton } from 'element-plus'
import type { Dashboard } from './api'
import { avatarColor, statusLabel, typeLabel } from './labels'

const props = defineProps<{ data: Dashboard }>()

const showTrendTable = ref(false)
const trendWrap = ref<HTMLDivElement | null>(null)
const trendWidth = ref(0)
const trendHeight = 240
const padL = 40
const padR = 14
const padT = 16
const padB = 28
let observer: ResizeObserver | null = null

onMounted(() => {
  observer = new ResizeObserver(entries => {
    const entry = entries[0]
    trendWidth.value = Math.max(0, Math.floor(entry ? entry.contentRect.width : 0))
  })
  if (trendWrap.value) observer.observe(trendWrap.value)
})
onBeforeUnmount(() => observer?.disconnect())

const points = computed(() => props.data.daily_new_30d)
const lastCount = computed(() => points.value[points.value.length - 1]?.count ?? 0)
const maxValue = computed(() => {
  const max = Math.max(1, ...points.value.map(point => point.count))
  return max <= 4 ? 4 : Math.max(10, Math.ceil(max / 10) * 10)
})
const ticks = computed(() => [0, maxValue.value / 2, maxValue.value])

const innerW = computed(() => Math.max(1, trendWidth.value - padL - padR))
const innerH = computed(() => trendHeight - padT - padB)
const xAt = (index: number) => padL + (index / Math.max(1, points.value.length - 1)) * innerW.value
const yAt = (value: number) => padT + (1 - value / maxValue.value) * innerH.value
const yTick = (value: number) => yAt(value)

const linePath = computed(() =>
  points.value.map((point, index) => `${index ? 'L' : 'M'}${xAt(index).toFixed(1)},${yAt(point.count).toFixed(1)}`).join(' '),
)
const areaPath = computed(() => {
  if (!points.value.length) return ''
  const baseline = yAt(0).toFixed(1)
  return `${linePath.value} L${xAt(points.value.length - 1).toFixed(1)},${baseline} L${xAt(0).toFixed(1)},${baseline} Z`
})
const xLabelIndices = computed(() => {
  const last = points.value.length - 1
  const indices = points.value.map((_, index) => index).filter(index => index % 7 === 0)
  if (last >= 0 && !indices.includes(last) && last - indices[indices.length - 1]! >= 3) indices.push(last)
  return indices
})
const trendAria = computed(() => `近 30 天每日新增需求折线图，最新一天新增 ${lastCount.value} 条`)

const hoverIndex = ref<number | null>(null)
const tipStyle = computed(() => {
  const index = hoverIndex.value
  const point = index === null ? undefined : points.value[index]
  if (!point) return {}
  const x = xAt(index!)
  const flip = x > trendWidth.value - 110
  const top = Math.max(4, yAt(point.count) - 52)
  return { left: `${flip ? x - 96 : x + 12}px`, top: `${top}px` }
})

function onTrendMove(event: PointerEvent) {
  const target = event.currentTarget as SVGSVGElement
  const rect = target.getBoundingClientRect()
  const px = event.clientX - rect.left
  const index = Math.round(((px - padL) / innerW.value) * (points.value.length - 1))
  hoverIndex.value = Math.min(points.value.length - 1, Math.max(0, index))
}
function moveHover(delta: number) {
  const current = hoverIndex.value ?? points.value.length - 1
  hoverIndex.value = Math.min(points.value.length - 1, Math.max(0, current + delta))
}

const statusOrder = [
  'submitted', 'triaging', 'pending_review', 'needs_information', 'candidate', 'scheduled', 'developing',
  'testing', 'release_ready', 'released', 'deferred', 'rejected', 'duplicate', 'withdrawn', 'closed',
]
const statusRows = computed(() => {
  const entries = Object.entries(props.data.by_status)
  const max = Math.max(1, ...entries.map(([, count]) => count))
  return entries
    .map(([key, count]) => ({ key, label: statusLabel(key), count, pct: (count / max) * 100 }))
    .sort((a, b) => {
      const ia = statusOrder.indexOf(a.key)
      const ib = statusOrder.indexOf(b.key)
      return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib)
    })
})
const typeRows = computed(() => {
  const entries = ['feature', 'improvement', 'bug']
    .filter(kind => kind in props.data.by_type)
    .map(kind => [kind, props.data.by_type[kind]] as [string, number])
  const max = Math.max(1, ...entries.map(([, count]) => count))
  return entries.map(([key, count]) => ({ key, label: typeLabel(key), count, pct: (count / max) * 100 }))
})
const contributorPct = (count: number) => {
  const max = Math.max(1, ...props.data.top_contributors.map(person => person.count))
  return (count / max) * 100
}
</script>

<style scoped>
.charts-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin-bottom: 16px; }
.chart-card { margin-bottom: 0; min-width: 0; }
.chart-card h2 { margin: 0 0 14px; font-size: 17px; }
.chart-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.chart-head h2 { margin: 0; }
.trend-card { grid-column: 1 / -1; }
.trend-wrap { position: relative; }
.trend-svg { display: block; }
.trend-svg:focus-visible { outline: 2px solid var(--rp-primary); outline-offset: 2px; border-radius: 8px; }
.trend-svg text { font-size: 11.5px; fill: var(--rp-text-3); font-variant-numeric: tabular-nums; }
.trend-svg .gridline { stroke: var(--rp-border); stroke-width: 1; }
.trend-svg .tick-label { fill: var(--rp-text-3); }
.trend-svg .end-label { fill: var(--rp-text); font-weight: 600; font-size: 12px; }
.trend-area { fill: var(--rp-primary-soft); stroke: none; }
.trend-line { fill: none; stroke: var(--rp-primary); stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.trend-svg .crosshair { stroke: var(--rp-text-3); stroke-width: 1; }
.trend-svg .hover-dot { fill: var(--rp-primary); stroke: var(--rp-card); stroke-width: 2; }
.chart-tip { position: absolute; pointer-events: none; background: #0f172a; color: #fff; border-radius: 8px; padding: 5px 10px; display: flex; flex-direction: column; gap: 1px; box-shadow: 0 4px 12px rgba(15, 23, 42, .2); z-index: 5; }
.chart-tip strong { font-size: 14px; line-height: 1.2; }
.chart-tip span { font-size: 11.5px; opacity: .75; }
.trend-table-wrap { max-height: 248px; overflow: auto; }
.trend-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.trend-table th, .trend-table td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--rp-border); }
.trend-table th { color: var(--rp-text-3); font-weight: 600; position: sticky; top: 0; background: var(--rp-card); }
.trend-table td:last-child { font-variant-numeric: tabular-nums; }
.hbar-row { display: grid; grid-template-columns: 72px minmax(0, 1fr) 34px; align-items: center; gap: 10px; padding: 6px 0; }
.hbar-label { font-size: 13px; color: var(--rp-text-2); text-align: right; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.hbar-track { height: 14px; background: var(--rp-primary-soft); border-radius: 0 4px 4px 0; }
.hbar-fill { height: 100%; background: var(--rp-primary); border-radius: 0 4px 4px 0; }
.hbar-value { font-size: 13px; color: var(--rp-text); font-variant-numeric: tabular-nums; text-align: right; }
.contrib-row { grid-template-columns: 116px minmax(0, 1fr) 34px; }
.contrib-label { display: flex; align-items: center; gap: 6px; justify-content: flex-start; }
.contrib-avatar { flex: none; }
.contrib-name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.chart-empty { color: var(--rp-text-3); font-size: 13px; margin: 8px 0; }
.anon-note { color: var(--rp-text-3); font-size: 12.5px; margin: 10px 0 0; }
@media (max-width: 960px) {
  .charts-grid { grid-template-columns: 1fr; }
  .contrib-row { grid-template-columns: 96px minmax(0, 1fr) 34px; }
}
</style>
