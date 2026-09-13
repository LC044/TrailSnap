<template>
<div class="analytics-grid">
<!-- 日趋势：五条曲线同图，双 Y 轴 -->
<article class="panel chart-card trend-card">
  <div class="chart-head">
    <div><h2>用量趋势</h2><p>成本与 Token 用量的变化趋势</p></div>
    <el-button size="small" text @click="showTrendTable = !showTrendTable">{{ showTrendTable ? '图表' : '明细' }}</el-button>
  </div>
  <div v-show="!showTrendTable" ref="trendWrap" class="trend-wrap" @pointerleave="hoverIndex = null">
    <svg
      v-if="trendWidth > 0 && points.length"
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
      <!-- 网格 + 左轴（token）/ 右轴（成本）刻度 -->
      <g>
        <line v-for="tick in ticks" :key="`g-${tick}`" :x1="padL" :x2="trendWidth - padR" :y1="yTick(tick)" :y2="yTick(tick)" class="gridline" />
        <text v-for="tick in ticks" :key="`lt-${tick}`" :x="padL - 8" :y="yTick(tick)" dy="4" text-anchor="end" class="tick-label">{{ fmtTokens(tick) }}</text>
        <text v-for="tick in ticks" :key="`rt-${tick}`" :x="trendWidth - padR + 8" :y="yTick(tick)" dy="4" text-anchor="start" class="tick-label cost-tick">{{ costTickLabel(tick) }}</text>
      </g>
      <g>
        <text v-for="i in xLabelIndices" :key="`x-${i}`" :x="xAt(i)" :y="trendHeight - 8" text-anchor="middle" class="tick-label">{{ points[i]?.date.slice(5) }}</text>
      </g>
      <!-- 成本面积（右轴） -->
      <path v-if="seriesVisible.cost" :d="costAreaPath" class="trend-area cost-area" />
      <!-- token 曲线（左轴） -->
      <path v-for="s in visibleTokenSeries" :key="s.key" :d="tokenPaths[s.key]" :class="`trend-line series-${s.key}`" />
      <!-- 悬浮 -->
      <g v-if="hoverIndex !== null && points[hoverIndex]">
        <line :x1="xAt(hoverIndex)" :x2="xAt(hoverIndex)" :y1="padT" :y2="trendHeight - padB" class="crosshair" />
        <circle v-if="seriesVisible.cost" :cx="xAt(hoverIndex)" :cy="yAtCost(points[hoverIndex]!.total_cost_usd)" r="4.5" class="hover-dot series-cost" />
        <circle v-for="s in visibleTokenSeries" :key="`h-${s.key}`" :cx="xAt(hoverIndex)" :cy="yAtToken(points[hoverIndex]![s.key as 'input_tokens'])" r="4" :class="`hover-dot series-${s.key}`" />
      </g>
    </svg>
    <!-- 图例：点击切换显示 -->
    <div class="chart-legend">
      <button
        v-for="s in legendSeries"
        :key="s.key"
        type="button"
        class="legend-item"
        :class="{ off: !seriesVisible[s.key] }"
        @click="toggleSeries(s.key)"
      >
        <span :class="`legend-swatch series-${s.key}`"></span>
        <span class="legend-name">{{ s.label }}</span>
        <span v-if="hoverIndex !== null && points[hoverIndex]" class="legend-value">{{ formatSeriesValue(s.key, seriesValueOf(s.key)(points[hoverIndex]!)) }}</span>
      </button>
    </div>
    <div v-if="hoverIndex !== null && points[hoverIndex]" class="chart-tip" :style="tipStyle">
      <strong>{{ points[hoverIndex]!.date }}</strong>
      <span v-for="s in legendSeries" :key="`tip-${s.key}`" class="tip-row" :style="{ opacity: seriesVisible[s.key] ? 1 : 0.35 }">
        <i :class="`legend-swatch series-${s.key}`"></i>{{ s.label }}：{{ formatSeriesValue(s.key, seriesValueOf(s.key)(points[hoverIndex]!)) }}
      </span>
    </div>
  </div>
  <div v-show="showTrendTable" class="trend-table-wrap">
    <table class="trend-table">
      <thead><tr><th>日期</th><th>请求</th><th>新增输入</th><th>输出</th><th>缓存命中</th><th>缓存创建</th><th>成本 (USD)</th></tr></thead>
      <tbody>
        <tr v-for="point in points" :key="point.date">
          <td>{{ point.date }}</td>
          <td>{{ point.requests }}</td>
          <td>{{ point.input_tokens.toLocaleString() }}</td>
          <td>{{ point.output_tokens.toLocaleString() }}</td>
          <td>{{ point.cache_read_tokens.toLocaleString() }}</td>
          <td>{{ point.cache_creation_tokens.toLocaleString() }}</td>
          <td>{{ fmtCost(point.total_cost_usd) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</article>

<article class="panel chart-card cost-card">
  <div class="chart-head"><div><h2>成本构成</h2><p>按模型的成本占比</p></div></div>
  <div v-if="modelRows.length" class="cost-breakdown">
    <div class="donut" :style="donutStyle" role="img" :aria-label="`总成本 ${fmtCost(overview.total.total_cost_usd)} 美元，按模型构成`">
      <div class="donut-hole"><strong>${{ fmtCost(overview.total.total_cost_usd) }}</strong><span>总成本</span></div>
    </div>
    <div class="cost-legend">
      <div v-for="(row, index) in modelRows.slice(0, 5)" :key="row.key" class="cost-legend-row">
        <span class="cost-dot" :style="{ background: donutColors[index % donutColors.length] }"></span>
        <span class="cost-name" :title="row.label">{{ row.label }}</span>
        <strong>${{ fmtCost(row.total_cost_usd) }}</strong>
        <span>{{ costPct(row.total_cost_usd) }}%</span>
      </div>
    </div>
  </div>
  <p v-else class="chart-empty">暂无数据</p>
</article>
</div>

<!-- 分布 -->
<div class="charts-grid">
  <article class="panel chart-card">
    <h2>模型分布</h2>
    <template v-if="overview.by_model.length">
      <div v-for="row in modelRows" :key="row.key" class="hbar-row" :title="`${row.label}：$${fmtCost(row.total_cost_usd)}（${row.requests} 次）`">
        <span class="hbar-label">{{ row.label }}</span>
        <div class="hbar-track"><div class="hbar-fill" :style="{ width: `${row.pct}%` }"></div></div>
        <span class="hbar-value">${{ fmtCost(row.total_cost_usd) }}</span>
      </div>
    </template>
    <p v-else class="chart-empty">暂无数据</p>
  </article>

  <article class="panel chart-card">
    <h2>供应商分布</h2>
    <template v-if="overview.by_provider.length">
      <div v-for="row in providerRows" :key="row.key" class="hbar-row" :title="`${row.label}：$${fmtCost(row.total_cost_usd)}（${row.requests} 次）`">
        <span class="hbar-label">{{ row.label }}</span>
        <div class="hbar-track"><div class="hbar-fill" :style="{ width: `${row.pct}%` }"></div></div>
        <span class="hbar-value">${{ fmtCost(row.total_cost_usd) }}</span>
      </div>
    </template>
    <p v-else class="chart-empty">暂无数据</p>
  </article>

  <article class="panel chart-card">
    <h2>应用分布</h2>
    <template v-if="overview.by_app_type.length">
      <div v-for="row in appTypeRows" :key="row.key" class="hbar-row" :title="`${row.label}：$${fmtCost(row.total_cost_usd)}（${row.requests} 次）`">
        <span class="hbar-label">{{ row.label }}</span>
        <div class="hbar-track"><div class="hbar-fill" :style="{ width: `${row.pct}%` }"></div></div>
        <span class="hbar-value">${{ fmtCost(row.total_cost_usd) }}</span>
      </div>
    </template>
    <p v-else class="chart-empty">暂无数据</p>
  </article>

  <article v-if="overview.by_device.length > 1" class="panel chart-card">
    <h2>设备分布</h2>
    <div v-for="row in deviceRows" :key="row.key" class="hbar-row" :title="`${row.label}：$${fmtCost(row.total_cost_usd)}（${row.requests} 次）`">
      <span class="hbar-label">{{ row.label }}</span>
      <div class="hbar-track"><div class="hbar-fill" :style="{ width: `${row.pct}%` }"></div></div>
      <span class="hbar-value">${{ fmtCost(row.total_cost_usd) }}</span>
    </div>
  </article>
</div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import type { UsageBreakdownItem, UsageDailyPoint, UsageOverview } from '../../api'

const props = defineProps<{ overview: UsageOverview; daily: UsageDailyPoint[] }>()
const overview = computed(() => props.overview)
const daily = computed(() => props.daily)
const showTrendTable = ref(false)

function fmtCost(value: number): string {
  if (value >= 1000) return value.toLocaleString('en-US', { maximumFractionDigits: 0 })
  if (value >= 1) return value.toFixed(2)
  return value.toFixed(value < 0.01 ? 4 : 2)
}
function fmtTokens(value: number): string {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(2)}B`
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`
  return String(value)
}

// 趋势图五条曲线：cost 走右轴（美元），其余走左轴（token）
type TokenSeriesKey = 'cache_creation_tokens' | 'cache_read_tokens' | 'input_tokens' | 'output_tokens'
type SeriesKey = 'cost' | TokenSeriesKey
const legendSeries: Array<{ key: SeriesKey; label: string }> = [
  { key: 'cost', label: '成本' },
  { key: 'cache_creation_tokens', label: '缓存创建' },
  { key: 'cache_read_tokens', label: '缓存命中' },
  { key: 'input_tokens', label: '新增输入' },
  { key: 'output_tokens', label: '输出' },
]
const seriesVisible = reactive<Record<SeriesKey, boolean>>({
  cost: true, cache_creation_tokens: true, cache_read_tokens: true, input_tokens: true, output_tokens: true,
})
const tokenSeries = legendSeries.filter(s => s.key !== 'cost') as Array<{ key: TokenSeriesKey; label: string }>
const visibleTokenSeries = computed(() => tokenSeries.filter(s => seriesVisible[s.key]))
function toggleSeries(key: SeriesKey) {
  seriesVisible[key] = !seriesVisible[key]
}
function seriesValueOf(key: SeriesKey): (point: UsageDailyPoint) => number {
  return key === 'cost' ? (point => point.total_cost_usd) : (point => point[key])
}
function formatSeriesValue(key: SeriesKey, value: number) {
  return key === 'cost' ? `$${fmtCost(value)}` : fmtTokens(value)
}

// ---------- 趋势图：五条曲线同图，双 Y 轴 ----------
const trendWrap = ref<HTMLDivElement | null>(null)
const trendWidth = ref(0)
const trendHeight = 260
const padL = 68
const padR = 56
const padT = 16
const padB = 28
let observer: ResizeObserver | null = null

onMounted(() => {
  observer = new ResizeObserver(entries => {
    const entry = entries[0]
    trendWidth.value = Math.max(0, Math.floor(entry ? entry.contentRect.width : 0))
  })
  // 趋势卡片在 overview 加载完成后才渲染，等 DOM 就绪再 observe
  watch(trendWrap, node => {
    if (node) observer?.observe(node)
  }, { immediate: true })
})
onBeforeUnmount(() => observer?.disconnect())

const points = computed(() => {
  // 大范围时按周聚合避免点过密
  const raw = daily.value
  if (raw.length <= 120) return raw
  const weekly: UsageDailyPoint[] = []
  for (let index = 0; index < raw.length; index += 7) {
    const chunk = raw.slice(index, index + 7)
    weekly.push({
      date: chunk[chunk.length - 1]!.date,
      requests: chunk.reduce((sum, item) => sum + item.requests, 0),
      input_tokens: chunk.reduce((sum, item) => sum + item.input_tokens, 0),
      output_tokens: chunk.reduce((sum, item) => sum + item.output_tokens, 0),
      cache_read_tokens: chunk.reduce((sum, item) => sum + item.cache_read_tokens, 0),
      cache_creation_tokens: chunk.reduce((sum, item) => sum + item.cache_creation_tokens, 0),
      total_cost_usd: chunk.reduce((sum, item) => sum + item.total_cost_usd, 0),
    })
  }
  return weekly
})

// 左轴（token）：取可见 token 曲线的最大值；右轴（成本）：成本最大值。
// 右轴刻度 = 左轴刻度位置 × 成本最大值 / token 最大值，保持网格线对齐。
const maxToken = computed(() => Math.max(1, ...visibleTokenSeries.value.map(s => Math.max(1, ...points.value.map(p => p[s.key as 'input_tokens'])))))
const maxCost = computed(() => Math.max(1e-9, ...points.value.map(p => p.total_cost_usd)))
const ticks = computed(() => {
  const max = maxToken.value
  // 取整刻度：1/2/5 × 10^n
  const magnitude = 10 ** Math.floor(Math.log10(max))
  const unit = ([1, 2, 5, 10].map(u => u * magnitude).find(v => v >= max)) ?? 10 * magnitude
  return [0, unit / 2, unit]
})
const costTickLabel = (tick: number) => {
  const cost = (tick / maxToken.value) * maxCost.value
  return `$${fmtCost(cost)}`
}
const trendAria = computed(() => `按天用量趋势图：成本、缓存创建、缓存命中、输入、输出五条曲线，左轴为 token 量，右轴为成本`)

const innerW = computed(() => Math.max(1, trendWidth.value - padL - padR))
const innerH = computed(() => trendHeight - padT - padB)
const xAt = (index: number) => padL + (index / Math.max(1, points.value.length - 1)) * innerW.value
const yTick = (tick: number) => padT + (1 - tick / maxToken.value) * innerH.value
const yAtToken = (value: number) => padT + (1 - value / maxToken.value) * innerH.value
const yAtCost = (value: number) => padT + (1 - value / maxCost.value) * innerH.value

// Catmull-Rom 样条 → 三次贝塞尔：平滑曲线，端点用相邻点补齐；控制点钳制在绘图区内防止过冲
function smoothPath(values: number[], scale: (value: number) => number): string {
  const count = values.length
  if (!count) return ''
  const clampY = (y: number) => Math.min(trendHeight - padB, Math.max(padT, y))
  if (count === 1) return `M${xAt(0).toFixed(1)},${scale(values[0]!).toFixed(1)}`
  const at = (index: number) => {
    const clamped = Math.min(count - 1, Math.max(0, index))
    return { x: xAt(clamped), y: scale(values[clamped]!) }
  }
  let path = `M${at(0).x.toFixed(1)},${at(0).y.toFixed(1)}`
  for (let index = 0; index < count - 1; index += 1) {
    const p0 = at(index - 1)
    const p1 = at(index)
    const p2 = at(index + 1)
    const p3 = at(index + 2)
    const c1x = p1.x + (p2.x - p0.x) / 6
    const c1y = clampY(p1.y + (p2.y - p0.y) / 6)
    const c2x = p2.x - (p3.x - p1.x) / 6
    const c2y = clampY(p2.y - (p3.y - p1.y) / 6)
    path += ` C${c1x.toFixed(1)},${c1y.toFixed(1)} ${c2x.toFixed(1)},${c2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`
  }
  return path
}

const tokenPaths = computed(() => {
  const paths: Partial<Record<SeriesKey, string>> = {}
  for (const s of tokenSeries) {
    paths[s.key] = smoothPath(points.value.map(p => p[s.key as 'input_tokens']), yAtToken)
  }
  return paths as Record<SeriesKey, string>
})
const costLinePath = computed(() => smoothPath(points.value.map(p => p.total_cost_usd), yAtCost))
const costAreaPath = computed(() => {
  if (!points.value.length) return ''
  const baseline = yAtCost(0).toFixed(1)
  return `${costLinePath.value} L${xAt(points.value.length - 1).toFixed(1)},${baseline} L${xAt(0).toFixed(1)},${baseline} Z`
})
const xLabelIndices = computed(() => {
  const last = points.value.length - 1
  const step = points.value.length > 60 ? 14 : 7
  const indices = points.value.map((_, index) => index).filter(index => index % step === 0)
  if (last >= 0 && !indices.includes(last) && last - indices[indices.length - 1]! >= 3) indices.push(last)
  return indices
})

const hoverIndex = ref<number | null>(null)
const tipStyle = computed(() => {
  const index = hoverIndex.value
  const point = index === null ? undefined : points.value[index]
  if (!point) return {}
  const x = xAt(index!)
  const flip = x > trendWidth.value - 130
  const top = Math.max(4, yAtCost(point.total_cost_usd) - 90)
  return { left: `${flip ? x - 146 : x + 12}px`, top: `${top}px` }
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

// ---------- 分布 ----------
function toRows(items: UsageBreakdownItem[], labelMap?: Record<string, string>) {
  const max = Math.max(1, ...items.map(item => item.total_cost_usd))
  return items.map(item => ({
    key: item.key,
    label: (labelMap?.[item.key] ?? item.label ?? item.key) || '未知',
    total_cost_usd: item.total_cost_usd,
    requests: item.requests,
    pct: (item.total_cost_usd / max) * 100,
  }))
}
const modelRows = computed(() => toRows(overview.value?.by_model ?? []).slice(0, 12))
const providerRows = computed(() => toRows(overview.value?.by_provider ?? []).slice(0, 10))
const appTypeLabels: Record<string, string> = { claude: 'Claude Code', 'claude-desktop': 'Claude Desktop', codex: 'Codex', gemini: 'Gemini' }
const appTypeRows = computed(() => toRows(overview.value?.by_app_type ?? [], appTypeLabels))
const deviceRows = computed(() => toRows(overview.value?.by_device ?? []))
const donutColors = ['#ff8747', '#2f74ef', '#8b5cf6', '#10a59c', '#cbd5e1']
const costPct = (value: number) => {
  const total = overview.value?.total.total_cost_usd || 0
  return total ? ((value / total) * 100).toFixed(1) : '0.0'
}
const donutStyle = computed(() => {
  const rows = modelRows.value.slice(0, 5)
  const total = rows.reduce((sum, row) => sum + row.total_cost_usd, 0)
  if (!total) return { background: '#eef2f7' }
  let start = 0
  const stops = rows.map((row, index) => {
    const end = start + (row.total_cost_usd / total) * 100
    const stop = `${donutColors[index % donutColors.length]} ${start.toFixed(2)}% ${end.toFixed(2)}%`
    start = end
    return stop
  })
  return { background: `conic-gradient(${stops.join(', ')})` }
})

</script>
