<template>
  <div class="usage-page">
    <div class="page-head">
      <div class="page-head-left">
        <div class="page-head-icon"><el-icon :size="26"><TrendCharts /></el-icon></div>
        <div>
          <h1>Token 用量</h1>
          <p class="sub">行影集开发用量与成本统计</p>
        </div>
      </div>
      <div v-if="overview" class="page-head-actions usage-filters">
        <el-date-picker
          v-model="filterRange"
          type="daterange"
          unlink-panels
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          value-format="YYYY-MM-DD"
          size="default"
          style="width: 260px"
          :shortcuts="dateShortcuts"
          :clearable="true"
        />
        <el-select v-model="filterModel" clearable filterable placeholder="全部模型" style="width: 180px" @change="reloadAll">
          <el-option v-for="m in filterOptions.models" :key="m" :label="m" :value="m" />
        </el-select>
        <el-select v-model="filterApp" clearable placeholder="全部应用" style="width: 150px" @change="reloadAll">
          <el-option v-for="a in filterOptions.app_types" :key="a" :label="appTypeLabels[a] ?? a" :value="a" />
        </el-select>
        <el-button v-if="filterActive" link type="primary" @click="resetFilters">重置</el-button>
      </div>
      <div v-else class="page-head-actions">
        <el-button v-if="manager" :icon="Refresh" @click="reloadAll">刷新</el-button>
      </div>
    </div>

    <div v-if="!overview && loading" class="panel empty">正在加载用量数据…</div>
    <div v-else-if="!overview" class="panel empty">
      <el-icon><Coin /></el-icon>
      <div>暂无用量数据</div>
      <p v-if="manager" class="empty-hint">在下方导入 cc-switch 导出的 SQL 备份文件</p>
    </div>
    <template v-else>
      <!-- 总览卡片 -->
      <div class="summary-grid">
        <div class="panel summary-card cost">
          <div class="summary-label">总成本 (USD)</div>
          <div class="summary-value">${{ fmtCost(overview.total.total_cost_usd) }}</div>
          <div class="summary-sub">{{ overview.total.requests.toLocaleString() }} 次请求</div>
        </div>
        <div class="panel summary-card">
          <div class="summary-label">输入 Tokens</div>
          <div class="summary-value">{{ fmtTokens(overview.total.input_tokens) }}</div>
          <div class="summary-sub">缓存读 {{ fmtTokens(overview.total.cache_read_tokens) }}</div>
        </div>
        <div class="panel summary-card">
          <div class="summary-label">输出 Tokens</div>
          <div class="summary-value">{{ fmtTokens(overview.total.output_tokens) }}</div>
          <div class="summary-sub">缓存写 {{ fmtTokens(overview.total.cache_creation_tokens) }}</div>
        </div>
        <div class="panel summary-card">
          <div class="summary-label">设备数</div>
          <div class="summary-value">{{ overview.device_count }}</div>
          <div class="summary-sub">{{ deviceLabels }}</div>
        </div>
      </div>

      <!-- 日趋势：五条曲线同图，双 Y 轴 -->
      <article class="panel chart-card trend-card">
        <div class="chart-head">
          <h2>用量趋势</h2>
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
            <thead><tr><th>日期</th><th>请求</th><th>输入 Tokens</th><th>输出 Tokens</th><th>缓存命中</th><th>缓存创建</th><th>成本 (USD)</th></tr></thead>
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

    <!-- 导入管理（仅管理员） -->
    <template v-if="manager">
      <article class="panel import-panel">
        <h2>导入管理</h2>
        <div class="import-form">
          <el-input v-model="deviceLabel" placeholder="设备名称，如：办公本 / 家里台式机" style="width: 240px" maxlength="40" />
          <input ref="fileInput" type="file" accept=".sql" class="file-hidden" @change="onFileChange" />
          <el-button type="primary" :icon="Upload" :loading="uploading" :disabled="!deviceLabel.trim()" @click="fileInput?.click()">上传 cc-switch 备份</el-button>
          <span class="import-hint">在 cc-switch「用量统计」页导出 SQLite 备份（.sql）后上传；同设备重复导出会自动去重合并。</span>
        </div>

        <div v-if="importResult" class="import-result">
          <el-alert type="success" :closable="false" show-icon>
            <template #title>
              导入成功：新增明细 {{ importResult.detail_new }} 条（跳过重复 {{ importResult.detail_dup }}、清理过期 {{ importResult.detail_aged_out }}），日聚合 {{ importResult.rollup_rows }} 行，覆盖 {{ importResult.date_min }} ~ {{ importResult.date_max }}
            </template>
          </el-alert>
        </div>

        <div v-if="imports.length" class="imports-table-wrap">
          <table class="trend-table">
            <thead><tr><th>设备</th><th>文件</th><th>明细新增/重复</th><th>日聚合</th><th>数据范围</th><th>导入时间</th><th></th></tr></thead>
            <tbody>
              <tr v-for="row in imports" :key="row.id">
                <td>{{ row.device_label }}</td>
                <td class="file-cell" :title="row.file_name">{{ row.file_name }}</td>
                <td>{{ row.detail_new }} / {{ row.detail_dup }}</td>
                <td>{{ row.rollup_rows }}</td>
                <td>{{ row.date_min }} ~ {{ row.date_max }}</td>
                <td>{{ fmtTime(row.imported_at) }}</td>
                <td><el-button size="small" type="danger" plain @click="removeImport(row)">删除</el-button></td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="chart-empty">还没有导入记录</p>

        <div v-if="devices.length" class="device-list">
          <span class="device-list-label">按设备删除全部数据：</span>
          <el-tag v-for="device in devices" :key="device.id" closable class="device-tag" @close="removeDevice(device)">{{ device.label }}</el-tag>
        </div>
      </article>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElAlert, ElButton, ElDatePicker, ElIcon, ElInput, ElMessage, ElMessageBox, ElOption, ElSelect, ElTag } from 'element-plus'
import { Coin, Refresh, TrendCharts, Upload } from '@element-plus/icons-vue'
import { api, type UsageBreakdownItem, type UsageImportRecord, type UsageImportResult, type UsageOverview, type UsageDailyPoint } from './api'

const props = defineProps<{ manager: boolean }>()

const overview = ref<UsageOverview | null>(null)
const daily = ref<UsageDailyPoint[]>([])
const imports = ref<UsageImportRecord[]>([])
const loading = ref(false)

// 趋势图五条曲线：cost 走右轴（美元），其余走左轴（token）
type TokenSeriesKey = 'cache_creation_tokens' | 'cache_read_tokens' | 'input_tokens' | 'output_tokens'
type SeriesKey = 'cost' | TokenSeriesKey
const legendSeries: Array<{ key: SeriesKey; label: string }> = [
  { key: 'cost', label: '成本' },
  { key: 'cache_creation_tokens', label: '缓存创建' },
  { key: 'cache_read_tokens', label: '缓存命中' },
  { key: 'input_tokens', label: '输入' },
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

// 筛选
const filterRange = ref<[string, string] | null>(null)
const filterModel = ref('')
const filterApp = ref('')
const filterOptions = ref<{ models: string[]; app_types: string[] }>({ models: [], app_types: [] })
const filterActive = computed(() => !!filterRange.value || !!filterModel.value || !!filterApp.value)

// 日期快捷选项（以数据最后日期为基准往前推，避免"今天"截断最近数据）
const dataMaxDate = computed(() => {
  const last = daily.value[daily.value.length - 1]?.date
  return last ?? new Date().toISOString().slice(0, 10)
})
const dateShortcuts = computed(() => {
  const days = (count: number): [string, string] => {
    const end = new Date(dataMaxDate.value)
    const start = new Date(end)
    start.setDate(start.getDate() - (count - 1))
    return [start.toISOString().slice(0, 10), end.toISOString().slice(0, 10)]
  }
  return [
    { text: '近 7 天', value: days(7) },
    { text: '近 30 天', value: days(30) },
    { text: '近 90 天', value: days(90) },
    { text: '近 180 天', value: days(180) },
  ]
})
function buildParams(): string {
  const params = new URLSearchParams()
  if (filterRange.value) {
    params.set('date_from', filterRange.value[0])
    params.set('date_to', filterRange.value[1])
  }
  if (filterModel.value) params.set('model', filterModel.value)
  if (filterApp.value) params.set('app_type', filterApp.value)
  const query = params.toString()
  return query ? `?${query}` : ''
}
function resetFilters() {
  filterRange.value = null
  filterModel.value = ''
  filterApp.value = ''
  void reloadAll()
}
const showTrendTable = ref(false)
const deviceLabel = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const importResult = ref<UsageImportResult | null>(null)

const devices = computed(() => {
  const seen = new Map<string, { id: string; label: string }>()
  for (const row of imports.value) seen.set(row.device_id, { id: row.device_id, label: row.device_label })
  return [...seen.values()]
})

const deviceLabels = computed(() => {
  const items = overview.value?.by_device ?? []
  if (items.length) return items.map(item => item.label).join('、')
  return devices.value.map(device => device.label).join('、') || '—'
})
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
function fmtTime(value?: string): string {
  if (!value) return '—'
  return value.replace('T', ' ').slice(0, 16)
}

async function reloadAll() {
  loading.value = true
  try {
    const query = buildParams()
    const [overviewData, dailyData] = await Promise.all([api.usageOverview(query), api.usageDaily(query)])
    overview.value = overviewData
    daily.value = dailyData
    filterOptions.value = await api.usageFilters()
    if (props.manager) imports.value = await api.usageImports()
  } finally {
    loading.value = false
  }
}

// 日期范围面板关闭/清空后触发重新加载（select 已在 @change 中处理）
watch(filterRange, (_value, old) => {
  const now = _value ? `${_value[0]}~${_value[1]}` : ''
  const before = old ? `${old[0]}~${old[1]}` : ''
  if (now !== before) void reloadAll()
})

onMounted(reloadAll)
defineExpose({ reloadAll })

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

// ---------- 导入 ----------
function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  void upload(file)
  input.value = ''
}
async function upload(file: File) {
  if (!deviceLabel.value.trim()) return
  uploading.value = true
  importResult.value = null
  try {
    importResult.value = await api.uploadUsageImport(deviceLabel.value.trim(), file)
    ElMessage.success('导入成功')
    await reloadAll()
  } catch (e) {
    if ((e as { response?: { status?: number } })?.response?.status === 409) ElMessage.warning('该文件之前已导入过')
    else ElMessage.error(((e as { response?: { data?: { msg?: string } } })?.response?.data?.msg) || '导入失败，请检查文件格式')
  } finally {
    uploading.value = false
  }
}
async function removeImport(row: UsageImportRecord) {
  try {
    await ElMessageBox.confirm(`删除「${row.file_name}」的 ${row.detail_new} 条明细？日聚合数据保留。`, '删除导入', { type: 'warning' })
  } catch { return }
  try {
    await api.deleteUsageImport(row.id)
    ElMessage.success('已删除')
    await reloadAll()
  } catch (e) { ElMessage.error(String(e)) }
}
async function removeDevice(device: { id: string; label: string }) {
  try {
    await ElMessageBox.confirm(`删除设备「${device.label}」及其全部用量数据？此操作不可恢复。`, '删除设备', { type: 'warning' })
  } catch { return }
  try {
    await api.deleteUsageDevice(device.id)
    ElMessage.success('已删除')
    await reloadAll()
  } catch (e) { ElMessage.error(String(e)) }
}
</script>

<style scoped>
.usage-page { max-width: 1200px; margin: 0 auto; }
.page-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; margin-bottom: 20px; }
.page-head-left { display: flex; gap: 14px; align-items: center; }
.page-head h1 { margin: 0; font-size: 22px; }
.page-head .sub { margin: 2px 0 0; color: var(--rp-text-2); font-size: 14px; }
.page-head .desc { margin: 4px 0 0; color: var(--rp-text-3); font-size: 13px; }
.page-head-actions { display: flex; align-items: center; gap: 12px; }
.usage-filters { flex-wrap: wrap; justify-content: flex-end; }
.empty { text-align: center; padding: 48px 20px; color: var(--rp-text-3); display: flex; flex-direction: column; align-items: center; gap: 10px; }
.empty .el-icon { font-size: 32px; opacity: .5; }
.empty-hint { font-size: 13px; margin: 0; }

.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin-bottom: 16px; }
.summary-card { margin-bottom: 0; }
.summary-card.cost { border-top: 3px solid var(--rp-primary); }
.summary-label { font-size: 13px; color: var(--rp-text-3); }
.summary-value { font-size: 28px; font-weight: 800; margin-top: 4px; font-variant-numeric: tabular-nums; color: var(--rp-text); }
.summary-card.cost .summary-value { color: var(--rp-primary); }
.summary-sub { font-size: 12.5px; color: var(--rp-text-3); margin-top: 4px; }

.charts-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin-bottom: 16px; }
.chart-card { margin-bottom: 0; min-width: 0; }
.chart-card h2 { margin: 0 0 14px; font-size: 17px; }
.chart-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; gap: 10px; flex-wrap: wrap; }
.chart-head h2 { margin: 0; }
.trend-card { grid-column: 1 / -1; margin-bottom: 16px; }
.trend-wrap { position: relative; }
.trend-svg { display: block; }
.trend-svg:focus-visible { outline: 2px solid var(--rp-primary); outline-offset: 2px; border-radius: 8px; }
.trend-svg text { font-size: 11.5px; fill: var(--rp-text-3); font-variant-numeric: tabular-nums; }
.trend-svg .gridline { stroke: var(--rp-border); stroke-width: 1; }
.trend-svg .tick-label { fill: var(--rp-text-3); }
.trend-svg .cost-tick { fill: #c2703d; }
/* 五条曲线配色：同一色系的和谐搭配（成本右轴用暖陶色区分量纲） */
.series-cost { stroke: #c2703d; fill: none; stroke-width: 2.5; }
.cost-area { fill: rgba(194, 112, 61, .08); }
.series-cache_creation_tokens { stroke: #9d7bbd; }
.series-cache_read_tokens { stroke: #5b8db8; }
.series-input_tokens { stroke: #4c7fb5; stroke-width: 2.5; }
.series-output_tokens { stroke: #6faf8f; }
.trend-line { stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; fill: none; }
.trend-svg .crosshair { stroke: var(--rp-text-3); stroke-width: 1; }
.trend-svg .hover-dot { stroke: var(--rp-card); stroke-width: 2; }
.hover-dot.series-cost { fill: #c2703d; }
.hover-dot.series-cache_creation_tokens { fill: #9d7bbd; }
.hover-dot.series-cache_read_tokens { fill: #5b8db8; }
.hover-dot.series-input_tokens { fill: #4c7fb5; }
.hover-dot.series-output_tokens { fill: #6faf8f; }
/* 图例 */
.chart-legend { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; padding: 10px 0 0; }
.legend-item { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--rp-border); background: transparent; border-radius: 999px; padding: 3px 10px; font-size: 12.5px; color: var(--rp-text-2); cursor: pointer; transition: opacity .15s, border-color .15s; }
.legend-item:hover { border-color: var(--rp-primary); }
.legend-item:focus-visible { outline: 2px solid var(--rp-primary); outline-offset: 2px; }
.legend-item.off { opacity: .4; }
.legend-swatch { width: 10px; height: 10px; border-radius: 3px; display: inline-block; flex: none; }
.legend-swatch.series-cost { background: #c2703d; }
.legend-swatch.series-cache_creation_tokens { background: #9d7bbd; }
.legend-swatch.series-cache_read_tokens { background: #5b8db8; }
.legend-swatch.series-input_tokens { background: #4c7fb5; }
.legend-swatch.series-output_tokens { background: #6faf8f; }
.legend-value { font-variant-numeric: tabular-nums; color: var(--rp-text); }
.chart-tip { position: absolute; pointer-events: none; background: #0f172a; color: #fff; border-radius: 8px; padding: 6px 10px; display: flex; flex-direction: column; gap: 2px; box-shadow: 0 4px 12px rgba(15, 23, 42, .2); z-index: 5; min-width: 130px; }
.chart-tip strong { font-size: 13px; line-height: 1.3; }
.chart-tip .tip-row { font-size: 11.5px; opacity: .85; display: inline-flex; align-items: center; gap: 6px; }
.chart-tip .tip-row i { width: 8px; height: 8px; border-radius: 2px; }
.trend-table-wrap { max-height: 320px; overflow: auto; }
.trend-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.trend-table th, .trend-table td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--rp-border); }
.trend-table th { color: var(--rp-text-3); font-weight: 600; position: sticky; top: 0; background: var(--rp-card); }
.trend-table td:last-child { font-variant-numeric: tabular-nums; }
.file-cell { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.hbar-row { display: grid; grid-template-columns: 110px minmax(0, 1fr) 72px; align-items: center; gap: 10px; padding: 6px 0; }
.hbar-label { font-size: 13px; color: var(--rp-text-2); text-align: right; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.hbar-track { height: 14px; background: var(--rp-primary-soft); border-radius: 0 4px 4px 0; }
.hbar-fill { height: 100%; background: var(--rp-primary); border-radius: 0 4px 4px 0; }
.hbar-value { font-size: 13px; color: var(--rp-text); font-variant-numeric: tabular-nums; text-align: right; }
.chart-empty { color: var(--rp-text-3); font-size: 13px; margin: 8px 0; }

.import-panel h2 { margin: 0 0 14px; font-size: 17px; }
.import-form { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.import-hint { font-size: 12.5px; color: var(--rp-text-3); }
.file-hidden { display: none; }
.import-result { margin-top: 14px; }
.imports-table-wrap { margin-top: 14px; max-height: 360px; overflow: auto; }
.device-list { margin-top: 14px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.device-list-label { font-size: 13px; color: var(--rp-text-3); }
.device-tag { cursor: pointer; }

@media (max-width: 960px) {
  .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .charts-grid { grid-template-columns: 1fr; }
  .hbar-row { grid-template-columns: 92px minmax(0, 1fr) 68px; }
  .page-head-actions.usage-filters { width: 100%; justify-content: flex-start; }
}
</style>
