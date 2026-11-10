<template>
  <div class="kpi-grid">
    <button v-for="card in cards" :key="card.key" type="button" class="kpi-card" :class="`tone-${card.tone}`"
      :aria-label="`${card.label} ${formatNumber(card.value)}，${card.hint}`" @click="go(card)">
      <div class="kpi-top">
        <span class="kpi-icon"><el-icon :size="17"><component :is="card.icon" /></el-icon></span>
        <span class="kpi-label">{{ card.label }}</span>
        <el-icon class="kpi-arrow" :size="14"><ArrowRight /></el-icon>
      </div>
      <div class="kpi-main">
        <strong class="kpi-value">{{ formatNumber(card.value) }}</strong>
        <span v-if="card.badge" class="kpi-badge" :class="card.badgeTone">{{ card.badge }}</span>
      </div>
      <p class="kpi-hint">{{ card.hint }}</p>
      <svg v-if="card.spark.length > 1" class="kpi-spark" viewBox="0 0 100 32" preserveAspectRatio="none" aria-hidden="true">
        <defs>
          <linearGradient :id="`spark-${card.key}`" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" :stop-color="card.color" stop-opacity=".28" />
            <stop offset="100%" :stop-color="card.color" stop-opacity="0" />
          </linearGradient>
        </defs>
        <path :d="sparkArea(card.spark)" :fill="`url(#spark-${card.key})`" />
        <path :d="sparkLine(card.spark)" fill="none" :stroke="card.color" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke" />
      </svg>
      <div v-if="card.bar !== undefined" class="kpi-bar"><span :style="{ width: `${Math.min(100, card.bar)}%`, background: card.color }" /></div>
    </button>
  </div>

  <div class="kpi-strip">
    <div v-for="item in strip" :key="item.label" class="kpi-mini">
      <el-icon :size="15"><component :is="item.icon" /></el-icon>
      <span class="mini-label">{{ item.label }}</span>
      <strong>{{ item.value }}</strong>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, type Component } from 'vue'
import { ArrowRight, CircleCheck, Clock, Connection, DataAnalysis, Files, Hide, Star, Timer, TrendCharts, User } from '@element-plus/icons-vue'
import type { Dashboard } from '../../api'
import { formatNumber, palette, type TrendPoint } from './dashboardData'

type NavTab = 'public' | 'admin' | 'versions'
type KpiCard = {
  key: string; label: string; value: number; hint: string; icon: Component; tone: string; color: string
  spark: number[]; bar?: number; tab?: NavTab; badge?: string; badgeTone?: 'up' | 'down'
}

const props = defineProps<{ data: Dashboard; points: TrendPoint[] }>()
const emit = defineEmits<{ navigate: [tab: NavTab] }>()

const sum = (values: number[]) => values.reduce((total, value) => total + value, 0)
const pct = (value: number) => props.data.total ? (value / props.data.total) * 100 : 0
const last7 = computed(() => sum(props.points.slice(-7).map(point => point.count)))
const prev7 = computed(() => sum(props.points.slice(-14, -7).map(point => point.count)))
const changePct = computed(() => prev7.value ? Math.round(((last7.value - prev7.value) / prev7.value) * 100) : null)

const cards = computed<KpiCard[]>(() => [
  {
    key: 'total', label: '全部需求', value: props.data.total, tab: 'public',
    hint: `近 ${props.points.length || 30} 天新增 ${formatNumber(sum(props.points.map(point => point.count)))} 条`,
    icon: DataAnalysis, tone: 'blue', color: palette.blue,
    spark: props.points.map(point => point.count),
  },
  {
    key: 'new', label: '近 7 天新增', value: props.data.new_last_7_days, tab: 'public',
    hint: changePct.value === null ? '等待更多历史数据' : `较前 7 天${changePct.value >= 0 ? '增长' : '下降'} ${Math.abs(changePct.value)}%`,
    icon: TrendCharts, tone: 'violet', color: palette.violet,
    spark: props.points.slice(-14).map(point => point.count),
    badge: changePct.value === null ? undefined : `${changePct.value >= 0 ? '+' : ''}${changePct.value}%`,
    badgeTone: (changePct.value ?? 0) >= 0 ? 'up' : 'down',
  },
  {
    key: 'pending', label: '待处理', value: props.data.pending_review, tab: 'admin',
    hint: `占全部需求 ${pct(props.data.pending_review).toFixed(1)}% · 建议优先审核`,
    icon: Timer, tone: 'amber', color: palette.amber, spark: [], bar: pct(props.data.pending_review),
  },
  {
    key: 'progress', label: '开发发布中', value: props.data.in_progress, tab: 'versions',
    hint: `占全部需求 ${pct(props.data.in_progress).toFixed(1)}% · 版本推进中`,
    icon: CircleCheck, tone: 'teal', color: palette.teal, spark: [], bar: pct(props.data.in_progress),
  },
])

const strip = computed(() => [
  { label: '已关联 GitHub', value: formatNumber(props.data.github_linked), icon: Connection },
  { label: '匿名提交', value: formatNumber(props.data.anonymous), icon: Hide },
  { label: '参与人数', value: formatNumber(props.data.contributor_count), icon: Files },
  { label: '近 30 天活跃', value: props.data.active_contributors_30d === undefined ? '—' : formatNumber(props.data.active_contributors_30d), icon: User },
  { label: '关注总数', value: formatNumber(props.data.follower_count), icon: Star },
  { label: '近 30 天完成', value: props.data.released_last_30d === undefined ? '—' : formatNumber(props.data.released_last_30d), icon: CircleCheck },
  { label: '平均处理时长', value: props.data.avg_resolution_days == null ? '—' : `${props.data.avg_resolution_days} 天`, icon: Clock },
])

function go(card: KpiCard) {
  if (card.tab) emit('navigate', card.tab)
}

function sparkCoords(values: number[]) {
  const max = Math.max(1, ...values)
  return values.map((value, index) => ({
    x: values.length > 1 ? (index / (values.length - 1)) * 100 : 0,
    y: 30 - (value / max) * 25,
  }))
}
const sparkLine = (values: number[]) => sparkCoords(values)
  .map((point, index) => `${index ? 'L' : 'M'}${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ')
const sparkArea = (values: number[]) => {
  if (values.length < 2) return ''
  return `${sparkLine(values)} L100,32 L0,32 Z`
}
</script>

<style scoped>
.kpi-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.kpi-card {
  --kpi-color: var(--rp-primary); --kpi-soft: var(--rp-primary-soft);
  position: relative; display: block; min-width: 0; min-height: 148px; padding: 16px 16px 14px;
  overflow: hidden; text-align: left; cursor: pointer;
  border: 1px solid var(--rp-border); border-radius: 16px; background: #fff; box-shadow: var(--rp-shadow);
  transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
}
.kpi-card:hover { transform: translateY(-2px); box-shadow: 0 10px 28px -14px rgba(37,99,235,.45); border-color: #cbdcff; }
.kpi-card:focus-visible { outline: 2px solid var(--rp-primary); outline-offset: 2px; }
.kpi-card.tone-violet { --kpi-color: #8b5cf6; --kpi-soft: #f4f0ff; }
.kpi-card.tone-amber { --kpi-color: #f59e0b; --kpi-soft: #fff7e8; }
.kpi-card.tone-teal { --kpi-color: #0f9f95; --kpi-soft: #e9fbfa; }
.kpi-top { display: flex; align-items: center; gap: 8px; }
.kpi-icon { display: inline-flex; align-items: center; justify-content: center; width: 30px; height: 30px; flex: none; border-radius: 9px; background: var(--kpi-soft); color: var(--kpi-color); }
.kpi-label { font-size: 13px; color: var(--rp-text-2); font-weight: 600; white-space: nowrap; }
.kpi-arrow { margin-left: auto; color: #cbd5e1; opacity: 0; transform: translateX(-4px); transition: opacity .18s, transform .18s; }
.kpi-card:hover .kpi-arrow { opacity: 1; transform: translateX(0); }
.kpi-main { display: flex; align-items: baseline; gap: 8px; margin-top: 12px; }
.kpi-value { font-size: 30px; line-height: 1.1; font-weight: 800; letter-spacing: -.5px; color: var(--rp-text); font-variant-numeric: tabular-nums; }
.kpi-badge { padding: 2px 7px; border-radius: 999px; font-size: 11.5px; font-weight: 700; font-variant-numeric: tabular-nums; }
.kpi-badge.up { background: #eaf8f1; color: #16a36a; }
.kpi-badge.down { background: #fef2f2; color: #dc2626; }
.kpi-hint { position: relative; z-index: 1; margin: 7px 0 0; font-size: 12px; line-height: 1.5; color: var(--rp-text-3); }
.kpi-spark { position: absolute; right: 0; bottom: 0; width: 58%; height: 54px; opacity: .9; pointer-events: none; }
.kpi-bar { position: relative; margin-top: 12px; height: 6px; border-radius: 999px; background: #f1f5f9; overflow: hidden; }
.kpi-bar span { display: block; height: 100%; border-radius: 999px; transition: width .5s ease; }

.kpi-strip { display: grid; grid-template-columns: repeat(auto-fit, minmax(126px, 1fr)); gap: 8px; margin: 12px 0 18px; }
.kpi-mini { display: flex; align-items: center; gap: 6px; min-width: 0; padding: 10px 10px; border: 1px solid var(--rp-border); border-radius: 12px; background: rgba(255,255,255,.8); }
.kpi-mini .el-icon { flex: none; color: var(--rp-primary); }
.kpi-mini .mini-label { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11.5px; color: var(--rp-text-3); }
.kpi-mini strong { margin-left: auto; flex: none; font-size: 13px; font-weight: 700; color: var(--rp-text); font-variant-numeric: tabular-nums; }

@media (max-width: 980px) {
  .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 720px) {
  .kpi-grid { gap: 10px; }
  .kpi-card { min-height: 134px; padding: 13px 12px; }
  .kpi-value { font-size: 25px; }
  .kpi-label { font-size: 12px; }
  .kpi-hint { font-size: 11px; }
  .kpi-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; }
  .kpi-mini { padding: 8px; }
}
@media (max-width: 420px) {
  .kpi-grid { grid-template-columns: minmax(0, 1fr); }
  .kpi-card { min-height: 0; }
  .kpi-mini .mini-label { font-size: 11px; }
}
</style>
