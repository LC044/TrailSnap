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
        <el-button v-if="manager" :icon="Refresh" @click="reloadAll(true)">刷新</el-button>
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
          <span class="summary-icon">$</span>
          <div class="summary-content">
            <div class="summary-label">总成本 (USD)</div>
            <div class="summary-value">${{ fmtCost(overview.total.total_cost_usd) }}</div>
            <div class="summary-sub">统计周期内累计成本</div>
          </div>
        </div>
        <div class="panel summary-card token-total">
          <div class="token-total-main">
            <span class="summary-icon">T</span>
            <div class="summary-content">
              <div class="summary-label" title="新增输入、输出、缓存创建和缓存命中互不重叠后相加">真实消耗 Tokens</div>
              <div class="summary-value total-token-value">{{ overview.total.real_total_tokens.toLocaleString() }}</div>
              <div class="summary-sub">≈ {{ fmtTokens(overview.total.real_total_tokens) }} · 新增输入 + 输出 + 缓存</div>
            </div>
          </div>
          <div class="token-breakdown">
            <div class="token-breakdown-row input-row">
              <span class="breakdown-dot"></span><span class="breakdown-label">新增输入</span>
              <strong>{{ fmtTokens(overview.total.input_tokens) }}</strong>
              <span class="breakdown-cache">缓存命中 {{ fmtTokens(overview.total.cache_read_tokens) }}</span>
            </div>
            <div class="token-breakdown-row output-row">
              <span class="breakdown-dot"></span><span class="breakdown-label">输出</span>
              <strong>{{ fmtTokens(overview.total.output_tokens) }}</strong>
              <span class="breakdown-cache">缓存创建 {{ fmtTokens(overview.total.cache_creation_tokens) }}</span>
            </div>
          </div>
        </div>
        <div class="panel summary-card requests">
          <span class="summary-icon">次</span>
          <div class="summary-content">
            <div class="summary-label">请求数</div>
            <div class="summary-value">{{ overview.total.requests.toLocaleString() }}</div>
            <div class="summary-sub">缓存命中率 {{ fmtPercent(overview.total.cache_hit_rate) }} · {{ overview.device_count }} 台设备</div>
          </div>
        </div>
      </div>

      <UsageCharts :overview="overview" :daily="daily" />
    </template>

    <UsageImportPanel v-if="manager" @changed="onImportsChanged" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElButton, ElDatePicker, ElIcon, ElOption, ElSelect } from 'element-plus'
import { Coin, Refresh, TrendCharts } from '@element-plus/icons-vue'
import { api, type UsageOverview, type UsageDailyPoint } from './api'
import UsageCharts from './components/usage/UsageCharts.vue'
import UsageImportPanel from './components/usage/UsageImportPanel.vue'

const props = defineProps<{ manager: boolean }>()

const overview = ref<UsageOverview | null>(null)
const daily = ref<UsageDailyPoint[]>([])
const loading = ref(false)
const CACHE_TTL_MS = 5 * 60 * 1000
const CACHE_PREFIX = 'rp_usage_cache:'

// 筛选
const filterRange = ref<[string, string] | null>(null)
const filterModel = ref('')
const filterApp = ref('')
const appTypeLabels: Record<string, string> = { claude: 'Claude Code', 'claude-desktop': 'Claude Desktop', codex: 'Codex', gemini: 'Gemini' }
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
function fmtPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}
function cacheKey(query: string) { return `${CACHE_PREFIX}${props.manager ? 'manager' : 'viewer'}:${query}` }
function clearUsageCache() {
  for (let index = sessionStorage.length - 1; index >= 0; index -= 1) {
    const key = sessionStorage.key(index)
    if (key?.startsWith(CACHE_PREFIX)) sessionStorage.removeItem(key)
  }
}
async function reloadAll(force = false) {
  loading.value = true
  try {
    const query = buildParams()
    if (!force) {
      try {
        const cached = JSON.parse(sessionStorage.getItem(cacheKey(query)) || 'null')
        if (cached && Date.now() - cached.savedAt < CACHE_TTL_MS) {
          overview.value = cached.overview
          daily.value = cached.daily
          filterOptions.value = cached.filterOptions
          return
        }
      } catch { sessionStorage.removeItem(cacheKey(query)) }
    }
    const [overviewData, dailyData] = await Promise.all([api.usageOverview(query), api.usageDaily(query)])
    overview.value = overviewData
    daily.value = dailyData
    filterOptions.value = await api.usageFilters()
    try {
      sessionStorage.setItem(cacheKey(query), JSON.stringify({ savedAt: Date.now(), overview: overview.value,
        daily: daily.value, filterOptions: filterOptions.value }))
    } catch { /* storage may be disabled; data is still available in memory */ }
  } finally {
    loading.value = false
  }
}

function onImportsChanged() {
  clearUsageCache()
  void reloadAll(true)
}

// 日期范围面板关闭/清空后触发重新加载（select 已在 @change 中处理）
watch(filterRange, (_value, old) => {
  const now = _value ? `${_value[0]}~${_value[1]}` : ''
  const before = old ? `${old[0]}~${old[1]}` : ''
  if (now !== before) void reloadAll()
})

onMounted(reloadAll)
defineExpose({ reloadAll })

</script>

<style>
.usage-page { max-width: 1376px; margin: 0 auto; }
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

.summary-grid { display: grid; grid-template-columns: minmax(220px, .9fr) minmax(460px, 2fr) minmax(220px, .9fr); gap: 14px; margin-bottom: 16px; }
.summary-card { --summary-color: #ff6b2c; --summary-soft: #fff0e8; min-height: 124px; margin-bottom: 0; padding: 20px; display: flex; align-items: flex-start; gap: 15px; overflow: hidden; position: relative; }
.summary-card::after { content: ''; position: absolute; right: -16px; bottom: -24px; width: 90px; height: 90px; border-radius: 50%; background: var(--summary-soft); opacity: .55; }
.summary-card.token-total { --summary-color: #2563eb; --summary-soft: #eaf2ff; align-items: center; justify-content: space-between; gap: 24px; }
.summary-card.requests { --summary-color: #8b5cf6; --summary-soft: #f2ecff; }
.summary-icon { width: 42px; height: 42px; display: inline-flex; align-items: center; justify-content: center; flex: none; border-radius: 13px; background: var(--summary-soft); color: var(--summary-color); font-size: 14px; font-weight: 800; }
.summary-content { min-width: 0; position: relative; z-index: 1; }
.summary-label { font-size: 13px; color: var(--rp-text-2); }
.summary-value { font-size: 28px; font-weight: 800; margin-top: 5px; line-height: 1.1; letter-spacing: -.02em; font-variant-numeric: tabular-nums; color: var(--rp-text); }
.total-token-value { font-size: clamp(22px, 2vw, 28px); }
.summary-card.cost { border-color: rgba(255,107,44,.42); background: linear-gradient(135deg, #fff 30%, #fff9f5); }
.summary-card.cost .summary-value { color: #ef5b1b; }
.summary-sub { font-size: 12px; color: var(--rp-text-3); margin-top: 7px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.token-total-main { display: flex; align-items: flex-start; gap: 15px; flex: none; }
.token-breakdown { min-width: 290px; display: grid; gap: 9px; padding-left: 20px; border-left: 1px solid var(--rp-border); }
.token-breakdown-row { display: grid; grid-template-columns: 8px 34px minmax(58px, auto) minmax(104px, auto); align-items: center; gap: 7px; font-size: 12px; }
.breakdown-dot { width: 7px; height: 7px; border-radius: 50%; background: #2563eb; }
.output-row .breakdown-dot { background: #10b981; }
.breakdown-label { color: var(--rp-text-2); }
.token-breakdown-row strong { color: var(--rp-text); font-size: 13px; font-variant-numeric: tabular-nums; }
.breakdown-cache { color: var(--rp-text-3); white-space: nowrap; }

.analytics-grid { display: grid; grid-template-columns: minmax(0, 2fr) minmax(330px, .92fr); gap: 16px; margin-bottom: 16px; }
.charts-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin-bottom: 16px; }
.chart-card { margin-bottom: 0; min-width: 0; }
.chart-card h2 { margin: 0 0 14px; font-size: 17px; }
.chart-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; gap: 10px; flex-wrap: wrap; }
.chart-head h2 { margin: 0; }
.chart-head p { margin: 4px 0 0; color: var(--rp-text-3); font-size: 12.5px; }
.trend-card { min-width: 0; }
.trend-wrap { position: relative; }
.trend-svg { display: block; }
.trend-svg:focus-visible { outline: 2px solid var(--rp-primary); outline-offset: 2px; border-radius: 8px; }
.trend-svg text { font-size: 11.5px; fill: var(--rp-text-3); font-variant-numeric: tabular-nums; }
.trend-svg .gridline { stroke: var(--rp-border); stroke-width: 1; }
.trend-svg .tick-label { fill: var(--rp-text-3); }
.trend-svg .cost-tick { fill: #ea580c; }
/* 主数据使用高辨识度冷色，成本使用暖橙色区分量纲。 */
.series-cost { stroke: #f97316; fill: none; stroke-width: 2.5; }
.cost-area { fill: rgba(249, 115, 22, .075); }
.series-cache_creation_tokens { stroke: #8b5cf6; }
.series-cache_read_tokens { stroke: #06b6d4; }
.series-input_tokens { stroke: #2563eb; stroke-width: 2.6; }
.series-output_tokens { stroke: #10b981; stroke-width: 2.35; }
.trend-line { stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; fill: none; }
.trend-svg .crosshair { stroke: var(--rp-text-3); stroke-width: 1; }
.trend-svg .hover-dot { stroke: var(--rp-card); stroke-width: 2; }
.hover-dot.series-cost { fill: #f97316; }
.hover-dot.series-cache_creation_tokens { fill: #8b5cf6; }
.hover-dot.series-cache_read_tokens { fill: #06b6d4; }
.hover-dot.series-input_tokens { fill: #2563eb; }
.hover-dot.series-output_tokens { fill: #10b981; }
/* 图例 */
.chart-legend { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; padding: 10px 0 0; }
.legend-item { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--rp-border); background: transparent; border-radius: 999px; padding: 3px 10px; font-size: 12.5px; color: var(--rp-text-2); cursor: pointer; transition: opacity .15s, border-color .15s; }
.legend-item:hover { border-color: var(--rp-primary); }
.legend-item:focus-visible { outline: 2px solid var(--rp-primary); outline-offset: 2px; }
.legend-item.off { opacity: .4; }
.legend-swatch { width: 10px; height: 10px; border-radius: 3px; display: inline-block; flex: none; }
.legend-swatch.series-cost { background: #f97316; }
.legend-swatch.series-cache_creation_tokens { background: #8b5cf6; }
.legend-swatch.series-cache_read_tokens { background: #06b6d4; }
.legend-swatch.series-input_tokens { background: #2563eb; }
.legend-swatch.series-output_tokens { background: #10b981; }
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

.cost-card { min-height: 372px; }
.cost-breakdown { min-height: 285px; display: grid; align-content: center; gap: 24px; }
.donut { width: 174px; height: 174px; margin: 2px auto 0; padding: 20px; border-radius: 50%; box-shadow: 0 10px 28px -18px rgba(15,23,42,.4); }
.donut-hole { width: 100%; height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; border-radius: 50%; background: var(--rp-card); box-shadow: inset 0 0 0 1px rgba(226,232,240,.8); }
.donut-hole strong { font-size: 20px; letter-spacing: -.02em; }
.donut-hole span { margin-top: 4px; color: var(--rp-text-3); font-size: 11.5px; }
.cost-legend { display: grid; gap: 8px; }
.cost-legend-row { display: grid; grid-template-columns: 9px minmax(0,1fr) auto 44px; align-items: center; gap: 8px; font-size: 12px; }
.cost-dot { width: 8px; height: 8px; border-radius: 50%; }
.cost-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--rp-text-2); }
.cost-legend-row strong { font-variant-numeric: tabular-nums; }
.cost-legend-row > span:last-child { color: var(--rp-text-3); text-align: right; font-variant-numeric: tabular-nums; }

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
  .summary-card.cost { grid-column: 1; grid-row: 1; }
  .summary-card.requests { grid-column: 2; grid-row: 1; }
  .summary-card.token-total { grid-column: 1 / -1; grid-row: 2; }
  .analytics-grid { grid-template-columns: 1fr; }
  .charts-grid { grid-template-columns: 1fr; }
  .hbar-row { grid-template-columns: 92px minmax(0, 1fr) 68px; }
  .page-head-actions.usage-filters { width: 100%; justify-content: flex-start; }
}
@media (max-width: 560px) {
  .summary-grid { gap: 10px; }
  .summary-card { min-height: 112px; padding: 14px; gap: 10px; }
  .summary-card.token-total { align-items: stretch; flex-direction: column; gap: 14px; }
  .token-total-main { gap: 10px; }
  .token-breakdown { min-width: 0; padding: 12px 0 0; border-left: 0; border-top: 1px solid var(--rp-border); }
  .token-breakdown-row { grid-template-columns: 7px 58px minmax(58px, auto) 1fr; gap: 5px; }
  .breakdown-cache { text-align: right; }
  .summary-icon { width: 34px; height: 34px; border-radius: 10px; }
  .summary-value { font-size: 22px; }
  .usage-filters > * { width: 100% !important; }
  .cost-card { min-height: 0; }
  .chart-card { padding: 15px; }
  .trend-wrap { overflow-x: auto; }
}
</style>
