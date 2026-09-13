<template>
  <section>
    <div class="page-head"><div class="page-head-left"><div class="page-head-icon"><el-icon :size="26"><DataAnalysis /></el-icon></div><div><h1>需求总览</h1><p class="desc">掌握需求规模、审核积压和版本推进情况。</p></div></div></div>
    <div class="dashboard-cards">
      <article v-for="item in cards" :key="item.label" class="panel dashboard-card"><strong>{{ item.value }}</strong><span>{{ item.label }}</span></article>
    </div>
    <div class="metric-cards">
      <article class="panel dashboard-card"><strong>{{ data.contributor_count }}</strong><span>参与人数</span></article>
      <article class="panel dashboard-card"><strong>{{ data.follower_count }}</strong><span>关注总数</span></article>
    </div>
    <DashboardCharts :data="data" />
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { DataAnalysis } from '@element-plus/icons-vue'
import DashboardCharts from '../../DashboardCharts.vue'
import type { Dashboard } from '../../api'

const props = defineProps<{ data: Dashboard }>()
const cards = computed(() => [
  { label: '全部需求', value: props.data.total },
  { label: '近 7 天新增', value: props.data.new_last_7_days },
  { label: '待处理', value: props.data.pending_review },
  { label: '开发发布中', value: props.data.in_progress },
  { label: '已关联 GitHub', value: props.data.github_linked },
  { label: '匿名提交', value: props.data.anonymous },
])
</script>
