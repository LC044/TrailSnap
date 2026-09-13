<template>
  <section>
    <div class="page-head">
      <div class="page-head-left"><div class="page-head-icon"><el-icon :size="26"><Flag /></el-icon></div><div><h1>版本计划</h1><p class="sub">人工选择进入版本开发候选的需求</p><p class="desc">跟踪每个版本的范围、进度和发布状态。</p></div></div>
      <div class="page-head-actions"><el-button v-if="manager" type="primary" :icon="Plus" @click="$emit('create')">创建版本批次</el-button></div>
    </div>
    <div v-if="!batches.length" class="panel empty"><el-icon><Flag /></el-icon><div>暂无版本批次</div></div>
    <div v-else class="batch-grid">
      <article v-for="batch in batches" :key="batch.id" class="panel batch-card">
        <div class="card-head"><div><h2 class="card-title">{{ batch.name }}</h2><div class="meta"><span>{{ batch.version_name }}</span><span>{{ batchTypeLabel(batch.batch_type) }}</span><span v-if="batch.target_date">目标 {{ batch.target_date }}</span></div></div><span class="tag" :class="`s-${batch.status}`">{{ statusLabel(batch.status) }}</span></div>
        <el-button v-if="manager" class="batch-edit-btn" size="small" text :icon="EditPen" @click="$emit('edit', batch)">编辑</el-button>
        <p class="description">{{ batch.goal }}</p>
        <a v-if="batch.github_milestone_url" class="github-link" :href="batch.github_milestone_url" target="_blank" rel="noopener">GitHub Milestone #{{ batch.github_milestone_number }}</a>
        <ul class="batch-items">
          <li v-for="item in batch.items" :key="item.id">
            <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap"><strong style="font-size:14px">{{ item.requirement_snapshot.title }}</strong><span class="tag no-dot" :class="`d-${item.delivery_status}`">{{ deliveryLabel(item.delivery_status) }}</span></div>
            <div v-if="manager" class="actions" style="margin-top:8px">
              <el-select v-if="!['planning','candidate_selection','published','completed','cancelled'].includes(batch.status)" :model-value="item.delivery_status" size="small" style="width:150px" @change="$emit('update-delivery', batch.id, item.id, String($event))"><el-option v-for="status in deliveryStatuses" :key="status" :label="deliveryLabel(status)" :value="status" /></el-select>
              <el-button v-if="['planning','candidate_selection'].includes(batch.status)" size="small" type="danger" plain @click="$emit('remove', batch.id, item.id)">移出</el-button>
            </div>
          </li>
        </ul>
        <div v-if="manager" class="actions">
          <el-select v-if="['planning','candidate_selection'].includes(batch.status)" v-model="candidateSelection[batch.id]" filterable placeholder="选择候选需求" style="width:240px"><el-option v-for="requirement in candidates" :key="requirement.id" :label="requirement.title" :value="requirement.id" /></el-select>
          <el-button v-if="['planning','candidate_selection'].includes(batch.status)" @click="$emit('add', batch.id)">加入</el-button>
          <el-button v-if="batch.items.length && ['planning','candidate_selection'].includes(batch.status)" type="primary" @click="$emit('lock', batch.id)">锁定范围</el-button>
          <el-dropdown v-if="allowedStatuses(batch.status).length" @command="$emit('update-state', batch.id, String($event))"><el-button>更新状态</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item v-for="status in allowedStatuses(batch.status)" :key="status" :command="status">{{ statusLabel(status) }}</el-dropdown-item></el-dropdown-menu></template></el-dropdown>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { EditPen, Flag, Plus } from '@element-plus/icons-vue'
import type { Batch, Requirement } from '../../api'
import { batchTypeLabel, deliveryLabel, statusLabel } from '../../labels'

defineProps<{ batches: Batch[]; candidates: Requirement[]; manager: boolean; candidateSelection: Record<string, string>; deliveryStatuses: string[]; allowedStatuses: (status: string) => string[] }>()
defineEmits<{
  create: []; edit: [batch: Batch]; add: [batchId: string]; remove: [batchId: string, itemId: string]
  lock: [batchId: string]; 'update-state': [batchId: string, status: string]
  'update-delivery': [batchId: string, itemId: string, status: string]
}>()
</script>
