<template>
  <section>
    <div class="page-head public-page-head">
      <div class="page-head-left">
        <div class="page-head-icon"><el-icon :size="26"><Document /></el-icon></div>
        <div><h1>公开需求</h1><p class="sub">一起把行影集变得更好</p><p class="desc">浏览和参与社区提出的需求，共同推动产品进步。</p></div>
      </div>
      <div class="stat-cards" aria-label="需求统计">
        <div class="stat-card tone-blue"><span class="stat-icon"><el-icon><Document /></el-icon></span><div><div class="num">{{ stats.total }}</div><div class="label">全部需求</div></div></div>
        <div class="stat-card tone-violet"><span class="stat-icon"><el-icon><Flag /></el-icon></span><div><div class="num">{{ stats.planned }}</div><div class="label">已规划</div></div></div>
        <div class="stat-card tone-cyan"><span class="stat-icon"><el-icon><Promotion /></el-icon></span><div><div class="num">{{ stats.developing }}</div><div class="label">开发中</div></div></div>
        <div class="stat-card tone-green"><span class="stat-icon"><el-icon><CircleCheckFilled /></el-icon></span><div><div class="num">{{ stats.done }}</div><div class="label">已完成</div></div></div>
      </div>
    </div>
    <div class="filters">
      <el-input v-model="filters.q" clearable placeholder="搜索 REQ 编号、标题、关键词或描述..." :prefix-icon="Search" class="search" @keyup.enter="$emit('reload')" @clear="$emit('reload')" />
      <el-select v-model="filters.type" clearable placeholder="全部类型" class="select" @change="$emit('reload')">
        <el-option label="新功能" value="feature" /><el-option label="体验优化" value="improvement" /><el-option label="问题修复" value="bug" />
      </el-select>
      <el-select v-model="filters.status" clearable placeholder="全部状态" class="select" @change="$emit('reload')">
        <el-option v-for="status in statusOptions" :key="status" :label="statusLabel(status)" :value="status" /><el-option label="已关闭" value="closed" />
      </el-select>
      <el-select :model-value="sortBy" placeholder="最新更新" class="sort" @update:model-value="$emit('update:sortBy', String($event))">
        <el-option label="最新更新" value="updated" /><el-option label="最早提交" value="oldest" /><el-option label="关注最多" value="followers" />
      </el-select>
      <el-button class="submit-requirement-btn" type="primary" :icon="Plus" @click="$emit('submit')">提交需求</el-button>
    </div>
    <RequirementTable :items="items" :manager="manager" :user="user" @open="$emit('open', $event)" @action="$emit('action', $event)" />
  </section>
</template>

<script setup lang="ts">
import { CircleCheckFilled, Document, Flag, Plus, Promotion, Search } from '@element-plus/icons-vue'
import RequirementTable from '../../RequirementTable.vue'
import { statusLabel } from '../../labels'
import type { Requirement, User } from '../../api'

defineProps<{
  stats: { total: number; planned: number; developing: number; done: number }
  filters: { q: string; type: string; status: string }
  statusOptions: string[]
  sortBy: string
  items: Requirement[]
  manager: boolean
  user: User | null
}>()

defineEmits<{
  reload: []
  submit: []
  open: [item: Requirement]
  action: [payload: { item: Requirement; command: string }]
  'update:sortBy': [value: string]
}>()
</script>
