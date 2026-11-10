<template>
  <article class="panel status-card">
    <div class="card-head">
      <div class="card-title"><h2>状态分布</h2><p>点击圆环或图例查看细分状态</p></div>
      <el-button v-if="selected" size="small" text @click="selected = null">重置</el-button>
    </div>

    <div class="donut-block">
      <div class="donut-wrap">
        <svg viewBox="0 0 200 200" class="donut-svg" role="img" :aria-label="`需求状态分布，共 ${total} 条`">
          <circle cx="100" cy="100" r="72" fill="none" stroke="#f1f5f9" stroke-width="24" />
          <circle v-for="segment in segments" :key="segment.key" cx="100" cy="100" r="72" fill="none"
            :stroke="segment.color" :stroke-width="active === segment.key ? 29 : 24"
            :stroke-dasharray="`${segment.dash} ${circumference - segment.dash}`" :stroke-dashoffset="-segment.offset"
            transform="rotate(-90 100 100)" class="donut-seg" :class="{ dim: active !== null && active !== segment.key }"
            tabindex="0" role="button" :aria-label="`${segment.label} ${segment.count} 条，占 ${segment.pct.toFixed(1)}%`"
            @pointerenter="hoverKey = segment.key" @pointerleave="hoverKey = null"
            @click="toggle(segment.key)" @keydown.enter.prevent="toggle(segment.key)" @keydown.space.prevent="toggle(segment.key)" />
        </svg>
        <div class="donut-center">
          <strong>{{ centerCount }}</strong>
          <span>{{ centerLabel }}</span>
          <small v-if="activeGroup">{{ activeGroup.pct.toFixed(1) }}% 占比</small>
        </div>
      </div>

      <div class="status-legend">
        <button v-for="group in groups" :key="group.key" type="button" class="legend-row"
          :class="{ dim: active !== null && active !== group.key, active: selected === group.key }"
          :aria-pressed="selected === group.key" @pointerenter="hoverKey = group.key" @pointerleave="hoverKey = null" @click="toggle(group.key)">
          <span class="legend-dot" :style="{ background: group.color }"></span>
          <span class="legend-label">{{ group.label }}</span>
          <strong>{{ group.count }}</strong>
          <span class="legend-pct">{{ group.pct.toFixed(0) }}%</span>
        </button>
      </div>
    </div>

    <div class="status-detail">
      <div class="detail-head">
        <span>{{ activeGroup ? `${activeGroup.label} · 细分状态` : '全部状态明细' }}</span>
        <small>共 {{ detailTotal }} 条</small>
      </div>
      <div v-if="detailRows.length" class="detail-rows">
        <div v-for="row in visibleDetailRows" :key="row.key" class="detail-row" :title="`${row.label}：${row.count} 条`">
          <span class="detail-label">{{ row.label }}</span>
          <span class="detail-track"><i :style="{ width: `${row.pct}%`, background: row.color }"></i></span>
          <strong>{{ row.count }}</strong>
        </div>
      </div>
      <p v-else class="chart-empty">暂无状态数据</p>
      <button v-if="detailRows.length > 6 && !selected" type="button" class="more-btn" @click="expanded = !expanded">
        {{ expanded ? '收起' : `展开全部 ${detailRows.length} 项` }}
      </button>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElButton } from 'element-plus'
import type { Dashboard } from '../../api'
import { formatNumber, groupRows, statusGroups, statusMeta, type BreakdownRow } from './dashboardData'

const props = defineProps<{ data: Dashboard }>()
const selected = ref<string | null>(null)
const hoverKey = ref<string | null>(null)
const expanded = ref(false)

const groups = computed(() => groupRows(props.data))
const total = computed(() => groups.value.reduce((sum, group) => sum + group.count, 0))
const radius = 72
const circumference = 2 * Math.PI * radius
const segments = computed(() => {
  let offset = 0
  return groups.value.filter(group => group.count > 0 && total.value > 0).map(group => {
    const length = (group.count / total.value) * circumference
    const segment = { ...group, dash: Math.max(.5, length - 3), offset }
    offset += length
    return segment
  })
})
const active = computed(() => hoverKey.value ?? selected.value)
const activeGroup = computed(() => groups.value.find(group => group.key === active.value) ?? null)
const centerCount = computed(() => activeGroup.value ? formatNumber(activeGroup.value.count) : formatNumber(total.value))
const centerLabel = computed(() => activeGroup.value?.label ?? '全部需求')

const groupKeyOf = (status: string) => statusGroups.find(group => group.statuses.includes(status))?.key ?? 'closed'
const detailRows = computed<BreakdownRow[]>(() => {
  const entries = Object.entries(props.data.by_status ?? {}).filter(([, count]) => count > 0)
  const filtered = selected.value ? entries.filter(([status]) => groupKeyOf(status) === selected.value) : entries
  const base = total.value || 1
  return filtered.map(([key, count]) => ({ key, count, ...statusMeta(key), pct: (count / base) * 100 }))
    .sort((a, b) => b.count - a.count)
})
const detailTotal = computed(() => detailRows.value.reduce((sum, row) => sum + row.count, 0))
const visibleDetailRows = computed(() => expanded.value || selected.value ? detailRows.value : detailRows.value.slice(0, 6))

function toggle(key: string) {
  selected.value = selected.value === key ? null : key
  expanded.value = false
  hoverKey.value = null
}
</script>

<style scoped>
.status-card { margin-bottom: 0; min-width: 0; }
.card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.card-title h2 { margin: 0; font-size: 17px; }
.card-title p { margin: 4px 0 0; font-size: 12px; color: var(--rp-text-3); }
.donut-block { display: flex; align-items: center; gap: 14px; margin: 12px 0 6px; }
.donut-wrap { position: relative; width: 168px; height: 168px; flex: none; }
.donut-svg { width: 100%; height: 100%; display: block; }
.donut-seg { cursor: pointer; transition: stroke-width .18s ease, opacity .18s ease; }
.donut-seg.dim { opacity: .32; }
.donut-seg:focus-visible { outline: none; filter: drop-shadow(0 0 4px rgba(37,99,235,.7)); }
.donut-center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; pointer-events: none; gap: 1px; }
.donut-center strong { font-size: 27px; line-height: 1.1; font-weight: 800; letter-spacing: -.5px; color: var(--rp-text); font-variant-numeric: tabular-nums; }
.donut-center span { font-size: 12px; color: var(--rp-text-3); }
.donut-center small { margin-top: 3px; font-size: 10.5px; color: var(--rp-primary); font-weight: 600; }
.status-legend { display: grid; gap: 2px; flex: 1; min-width: 0; }
.legend-row { display: flex; align-items: center; gap: 7px; width: 100%; padding: 5px 7px; border: 0; border-radius: 8px; background: transparent; text-align: left; cursor: pointer; transition: background .15s, opacity .15s; }
.legend-row:hover, .legend-row.active { background: var(--rp-primary-soft); }
.legend-row.dim { opacity: .42; }
.legend-row:focus-visible { outline: 2px solid var(--rp-primary); outline-offset: 1px; }
.legend-dot { width: 9px; height: 9px; border-radius: 3px; flex: none; }
.legend-label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12.5px; color: var(--rp-text-2); }
.legend-row strong { font-size: 13px; color: var(--rp-text); font-variant-numeric: tabular-nums; }
.legend-pct { width: 34px; text-align: right; font-size: 11px; color: var(--rp-text-3); font-variant-numeric: tabular-nums; }
.status-detail { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--rp-border); }
.detail-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; font-size: 12.5px; font-weight: 600; color: var(--rp-text-2); }
.detail-head small { font-size: 11px; font-weight: 400; color: var(--rp-text-3); }
.detail-rows { display: grid; gap: 2px; }
.detail-row { display: grid; grid-template-columns: 76px minmax(0, 1fr) 32px; align-items: center; gap: 8px; width: 100%; padding: 4px 2px; border: 0; border-radius: 6px; background: transparent; text-align: left; cursor: default; }
.detail-row:hover { background: #f8fafc; }
.detail-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; color: var(--rp-text-2); }
.detail-track { height: 7px; border-radius: 999px; background: #f1f5f9; overflow: hidden; }
.detail-track i { display: block; height: 100%; border-radius: 999px; transition: width .45s ease; }
.detail-row strong { text-align: right; font-size: 12px; color: var(--rp-text); font-variant-numeric: tabular-nums; }
.more-btn { margin-top: 8px; padding: 3px 0; border: 0; background: transparent; color: var(--rp-primary); font-size: 12px; cursor: pointer; }
.more-btn:hover { text-decoration: underline; }
.chart-empty { margin: 14px 0; text-align: center; color: var(--rp-text-3); font-size: 12.5px; }
@media (max-width: 420px) {
  .donut-block { gap: 6px; }
  .donut-wrap { width: 132px; height: 132px; }
  .donut-center strong { font-size: 22px; }
  .legend-row { padding: 4px 5px; }
}
</style>
