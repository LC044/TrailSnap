<template>
  <section class="dashboard-page">
    <div class="page-head dashboard-head">
      <div class="page-head-left">
        <div class="page-head-icon"><el-icon :size="26"><DataAnalysis /></el-icon></div>
        <div><h1>需求总览</h1><p class="desc">掌握需求规模、审核积压和版本推进情况。</p></div>
      </div>
      <div class="dashboard-controls">
        <div class="range-switch" role="group" aria-label="统计时间范围">
          <button v-for="option in ranges" :key="option" type="button" :class="{ active: range === option }"
            :disabled="option > points.length" :aria-pressed="range === option" @click="range = option">近 {{ option }} 天</button>
        </div>
        <span class="updated" :title="data.generated_at || ''">更新于 {{ formatUpdatedAt(data.generated_at) }}</span>
        <el-button class="refresh-btn" size="small" circle :loading="loading" aria-label="刷新看板数据" @click="emit('reload')">
          <el-icon v-if="!loading" :size="15"><Refresh /></el-icon>
        </el-button>
      </div>
    </div>

    <DashboardKpi :data="data" :points="slicedPoints" @navigate="emit('navigate', $event)" />

    <div v-if="insight" class="insight-bar">
      <el-icon :size="16"><InfoFilled /></el-icon>
      <span>{{ insight }}</span>
      <button v-if="data.pending_review" type="button" @click="emit('navigate', 'admin')">前往审核 <el-icon :size="12"><ArrowRight /></el-icon></button>
    </div>

    <div class="dashboard-main-grid">
      <DashboardTrend :points="points" :range="range" />
      <DashboardStatus :data="data" />
    </div>

    <div class="dashboard-secondary-grid">
      <DashboardBreakdown :data="data" />
      <DashboardRanking :data="data" @open-detail="emit('open-detail', $event)" />
    </div>

    <p class="dashboard-footnote">口径说明：统计范围为未删除的全部需求；新增趋势按创建时间统计，完成、关闭与平均处理时长按最近更新时间估算。时间范围仅影响趋势图与顶部指标卡。</p>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowRight, DataAnalysis, InfoFilled, Refresh } from '@element-plus/icons-vue'
import type { Dashboard } from '../../api'
import DashboardKpi from './DashboardKpi.vue'
import DashboardTrend from './DashboardTrend.vue'
import DashboardStatus from './DashboardStatus.vue'
import DashboardBreakdown from './DashboardBreakdown.vue'
import DashboardRanking from './DashboardRanking.vue'
import { formatUpdatedAt, trendPoints } from './dashboardData'

const props = defineProps<{ data: Dashboard; loading?: boolean }>()
const emit = defineEmits<{
  reload: []
  navigate: [tab: 'public' | 'admin' | 'versions']
  'open-detail': [number: number]
}>()

const ranges = [7, 30, 90]
const range = ref(30)
const points = computed(() => trendPoints(props.data))
const slicedPoints = computed(() => points.value.slice(-range.value))
const insight = computed(() => {
  const pending = props.data.pending_review
  const recent = props.data.new_last_7_days
  const share = props.data.total ? ((pending / props.data.total) * 100).toFixed(1) : '0.0'
  if (pending > 0) return `当前有 ${pending} 条需求待审核，占全部需求 ${share}%；近 7 天新增 ${recent} 条。`
  return `近 7 天新增 ${recent} 条需求，目前没有待审核积压。`
})
</script>

<style scoped>
.dashboard-page { min-width: 0; }
.dashboard-head { align-items: center; }
.dashboard-controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.range-switch { display: inline-flex; padding: 3px; border-radius: 10px; background: #eaf0f8; }
.range-switch button { min-height: 28px; padding: 0 11px; border: 0; border-radius: 8px; background: transparent; color: var(--rp-text-2); font-size: 12.5px; cursor: pointer; transition: background .15s, color .15s, box-shadow .15s; }
.range-switch button.active { background: #fff; color: var(--rp-primary); font-weight: 700; box-shadow: 0 1px 5px rgba(15,23,42,.12); }
.range-switch button:disabled { opacity: .4; cursor: not-allowed; }
.range-switch button:focus-visible { outline: 2px solid var(--rp-primary); outline-offset: 1px; }
.updated { font-size: 11.5px; color: var(--rp-text-3); white-space: nowrap; }
.refresh-btn { margin-left: 0; }
.insight-bar { display: flex; align-items: center; gap: 9px; margin: 0 0 16px; padding: 11px 14px; border: 1px solid #dbeafe; border-radius: 12px; background: linear-gradient(90deg, #f2f7ff, #fbfdff); color: var(--rp-text-2); font-size: 12.5px; }
.insight-bar > .el-icon { color: var(--rp-primary); flex: none; }
.insight-bar span { flex: 1; min-width: 0; line-height: 1.5; }
.insight-bar button { display: inline-flex; align-items: center; gap: 3px; flex: none; padding: 4px 8px; border: 0; border-radius: 7px; background: #fff; color: var(--rp-primary); font-size: 12px; font-weight: 600; cursor: pointer; box-shadow: 0 1px 3px rgba(15,23,42,.08); }
.insight-bar button:hover { background: var(--rp-primary-soft); }
.dashboard-main-grid { display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(310px, 1fr); gap: 16px; align-items: stretch; margin-bottom: 16px; }
.dashboard-secondary-grid { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(310px, 1fr); gap: 16px; align-items: stretch; }
.dashboard-footnote { margin: 16px 2px 0; font-size: 11.5px; line-height: 1.6; color: var(--rp-text-3); }
@media (max-width: 1180px) {
  .dashboard-main-grid, .dashboard-secondary-grid { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 720px) {
  .dashboard-head { align-items: flex-start; }
  .dashboard-controls { width: 100%; }
  .range-switch { margin-right: auto; }
  .insight-bar { flex-wrap: wrap; }
  .insight-bar button { margin-left: auto; }
}
@media (max-width: 420px) {
  .updated { display: none; }
}
</style>
