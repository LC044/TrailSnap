<template>
  <article class="panel breakdown-card">
    <div class="card-head">
      <div class="card-title"><h2>需求构成</h2><p>切换维度，查看不同口径的分布</p></div>
      <span class="total-chip">共 {{ currentTotal }} 条</span>
    </div>

    <div class="dim-tabs" role="tablist" aria-label="分布维度">
      <button v-for="dim in dimensions" :key="dim.key" type="button" role="tab" class="dim-tab"
        :class="{ active: active === dim.key }" :aria-selected="active === dim.key" :disabled="!dim.rows.length"
        :title="dim.rows.length ? dim.hint : '当前数据版本暂不支持该维度'" @click="select(dim.key)">{{ dim.label }}</button>
    </div>
    <p v-if="dimensions.some(dim => !dim.rows.length)" class="dim-note">灰色维度需要升级服务端后才会展示</p>

    <div v-if="selectedRow" class="selection">
      <span>已选 <b>{{ selectedRow.label }}</b> · {{ selectedRow.count }} 条 · 占 {{ selectedRow.pct.toFixed(1) }}%</span>
      <button type="button" @click="selectedRowKey = null">清除</button>
    </div>

    <div class="dist-rows">
      <button v-for="row in visibleRows" :key="row.key" type="button" class="dist-row"
        :class="{ active: selectedRowKey === row.key, dim: selectedRowKey !== null && selectedRowKey !== row.key }"
        :aria-pressed="selectedRowKey === row.key" :title="`${row.label}：${row.count} 条，占 ${row.pct.toFixed(1)}%`"
        @click="toggle(row.key)">
        <span class="dist-label"><i :style="{ background: row.color }"></i>{{ row.label }}</span>
        <span class="dist-track"><i :style="{ width: `${barWidth(row.count)}%`, background: row.color }"></i></span>
        <strong>{{ row.count }}</strong>
        <span class="dist-pct">{{ row.pct.toFixed(0) }}%</span>
      </button>
      <p v-if="!current.rows.length" class="chart-empty">暂无该维度数据</p>
    </div>

    <div class="dist-foot">
      <button v-if="current.rows.length > 8" type="button" class="more-btn" @click="expanded = !expanded">
        {{ expanded ? '收起' : `展开全部 ${current.rows.length} 项` }}
      </button>
      <span v-if="current.rows.length" class="summary">{{ current.rows[0]!.label }}占比最高 · {{ current.rows[0]!.pct.toFixed(1) }}%</span>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Dashboard } from '../../api'
import {
  palette, priorityMeta, severityMeta, sourceMeta, statusMeta, toRows, typeMeta, visibilityMeta,
  type BreakdownRow,
} from './dashboardData'

type DimensionKey = 'status' | 'type' | 'priority' | 'severity' | 'source' | 'visibility'
type Dimension = { key: DimensionKey; label: string; hint: string; rows: BreakdownRow[] }

const props = defineProps<{ data: Dashboard }>()
const active = ref<DimensionKey>('status')
const selectedRowKey = ref<string | null>(null)
const expanded = ref(false)

const fallback = (key: string) => ({ label: key, color: palette.slate })
const dimensions = computed<Dimension[]>(() => [
  { key: 'status', label: '状态', hint: '按处理阶段拆分', rows: toRows(props.data.by_status, statusMeta) },
  { key: 'type', label: '类型', hint: '按需求类型拆分', rows: toRows(props.data.by_type, key => typeMeta[key] ?? fallback(key)) },
  { key: 'priority', label: '优先级', hint: '按处理优先级拆分', rows: toRows(props.data.by_priority, key => priorityMeta[key] ?? fallback(key)) },
  { key: 'severity', label: '严重程度', hint: '按影响程度拆分', rows: toRows(props.data.by_severity, key => severityMeta[key] ?? fallback(key)) },
  { key: 'source', label: '来源', hint: '按提交渠道拆分', rows: toRows(props.data.by_source, key => sourceMeta[key] ?? fallback(key)) },
  { key: 'visibility', label: '公开范围', hint: '按可见范围拆分', rows: toRows(props.data.by_visibility, key => visibilityMeta[key] ?? fallback(key)) },
])
const current = computed(() => dimensions.value.find(dim => dim.key === active.value) ?? dimensions.value[0]!)
const currentTotal = computed(() => current.value.rows.reduce((sum, row) => sum + row.count, 0))
const maxCount = computed(() => Math.max(1, ...current.value.rows.map(row => row.count)))
const barWidth = (count: number) => (count / maxCount.value) * 100
const visibleRows = computed(() => expanded.value ? current.value.rows : current.value.rows.slice(0, 8))
const selectedRow = computed(() => current.value.rows.find(row => row.key === selectedRowKey.value) ?? null)

function select(key: DimensionKey) {
  active.value = key
  selectedRowKey.value = null
  expanded.value = false
}
function toggle(key: string) {
  selectedRowKey.value = selectedRowKey.value === key ? null : key
}
</script>

<style scoped>
.breakdown-card { margin-bottom: 0; min-width: 0; }
.card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.card-title h2 { margin: 0; font-size: 17px; }
.card-title p { margin: 4px 0 0; font-size: 12px; color: var(--rp-text-3); }
.total-chip { padding: 4px 10px; border-radius: 999px; background: var(--rp-primary-soft); color: var(--rp-primary); font-size: 11.5px; font-weight: 700; white-space: nowrap; }
.dim-tabs { display: flex; flex-wrap: wrap; gap: 4px; margin: 14px 0 4px; padding: 3px; border-radius: 10px; background: #f1f5f9; }
.dim-tab { flex: 1 0 auto; min-width: 62px; min-height: 28px; padding: 0 9px; border: 0; border-radius: 8px; background: transparent; color: var(--rp-text-2); font-size: 12px; cursor: pointer; transition: background .15s, color .15s, box-shadow .15s; }
.dim-tab.active { background: #fff; color: var(--rp-primary); font-weight: 700; box-shadow: 0 1px 4px rgba(15,23,42,.1); }
.dim-tab:disabled { opacity: .38; cursor: not-allowed; }
.dim-tab:focus-visible { outline: 2px solid var(--rp-primary); outline-offset: 1px; }
.dim-note { margin: 6px 2px 0; font-size: 11px; color: #b6c0cf; }
.selection { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin: 12px 0 4px; padding: 8px 10px; border-radius: 9px; background: var(--rp-primary-soft); color: var(--rp-primary); font-size: 12px; }
.selection b { font-weight: 700; }
.selection button { border: 0; background: transparent; color: var(--rp-primary); font-size: 12px; cursor: pointer; white-space: nowrap; }
.selection button:hover { text-decoration: underline; }
.dist-rows { display: grid; gap: 1px; margin-top: 10px; }
.dist-row { display: grid; grid-template-columns: 88px minmax(0, 1fr) 38px 38px; align-items: center; gap: 9px; width: 100%; padding: 6px 4px; border: 0; border-radius: 8px; background: transparent; text-align: left; cursor: pointer; transition: background .15s, opacity .15s; }
.dist-row:hover, .dist-row.active { background: #f8fafc; }
.dist-row.active { box-shadow: inset 2px 0 0 var(--rp-primary); }
.dist-row.dim { opacity: .42; }
.dist-row:focus-visible { outline: 2px solid var(--rp-primary); outline-offset: 1px; }
.dist-label { display: flex; align-items: center; gap: 6px; min-width: 0; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; font-size: 12.5px; color: var(--rp-text-2); }
.dist-label i { width: 8px; height: 8px; border-radius: 3px; flex: none; }
.dist-track { height: 9px; border-radius: 999px; background: #f1f5f9; overflow: hidden; }
.dist-track i { display: block; height: 100%; border-radius: 999px; transition: width .45s ease; }
.dist-row strong { text-align: right; font-size: 12.5px; color: var(--rp-text); font-variant-numeric: tabular-nums; }
.dist-pct { text-align: right; font-size: 11px; color: var(--rp-text-3); font-variant-numeric: tabular-nums; }
.dist-foot { display: flex; align-items: center; justify-content: space-between; gap: 10px; min-height: 26px; margin-top: 8px; }
.more-btn { padding: 3px 0; border: 0; background: transparent; color: var(--rp-primary); font-size: 12px; cursor: pointer; }
.more-btn:hover { text-decoration: underline; }
.summary { margin-left: auto; font-size: 11.5px; color: var(--rp-text-3); }
.chart-empty { margin: 20px 0; text-align: center; color: var(--rp-text-3); font-size: 12.5px; }
@media (max-width: 720px) {
  .dist-row { grid-template-columns: 74px minmax(0, 1fr) 34px 34px; gap: 6px; }
  .dim-tab { min-width: 56px; padding: 0 6px; }
}
</style>
