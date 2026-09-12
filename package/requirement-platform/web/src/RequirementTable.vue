<template>
  <div class="panel" :class="{ 'table-panel': true }">
    <table v-if="items.length" class="req-table">
      <thead>
        <tr>
          <th style="width: 46%">需求标题</th>
          <th style="width: 10%">类型</th>
          <th style="width: 11%">状态</th>
          <th style="width: 9%">优先级</th>
          <th style="width: 12%">提交人</th>
          <th style="width: 9%">更新时间</th>
          <th class="cell-more" style="width: 3%"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in pagedItems" :key="item.id">
          <td>
            <div class="cell-title">
              <span class="type-badge" :class="item.type">
                <el-icon :size="18"><component :is="typeIcon(item.type)" /></el-icon>
              </span>
              <div style="min-width: 0">
                <p class="req-title req-title-link" @click="emit('open', item)"><span class="req-number">REQ-{{ item.public_number }}</span> {{ item.title }}</p>
                <p class="req-desc">{{ item.description }}</p>
              </div>
            </div>
          </td>
          <td class="cell-type"><span class="tag no-dot" :class="`t-${item.type}`">{{ typeLabel(item.type) }}</span></td>
          <td class="cell-status"><span class="tag" :class="`s-${item.status}`">{{ statusLabel(item.status) }}</span></td>
          <td class="cell-priority"><span class="tag no-dot" :class="`p-${item.priority}`">{{ priorityLabel(item.priority) }}</span></td>
          <td class="cell-user">
            <span class="avatar" :style="{ width: '28px', height: '28px', fontSize: '13px', ...avatarColor(creatorName(item)) }">
              {{ creatorName(item).slice(0, 1) }}
            </span>
            {{ creatorName(item) }}
          </td>
          <td class="cell-date">{{ formatDate(item.updated_at) }}</td>
          <td class="cell-more">
            <el-dropdown trigger="click" @command="command => emit('action', { item, command })">
              <el-button text circle :icon="MoreFilled" :aria-label="`更多操作：${item.title}`" />
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="follow">关注（{{ item.follower_count || 0 }}）</el-dropdown-item>
                  <el-dropdown-item v-if="canWithdraw(item)" command="withdraw">撤回</el-dropdown-item>
                  <el-dropdown-item v-if="manager" command="review">审核</el-dropdown-item>
                  <el-dropdown-item v-if="manager" command="edit">编辑需求</el-dropdown-item>
                  <el-dropdown-item v-if="manager" command="status">修改状态</el-dropdown-item>
                  <el-dropdown-item v-if="manager && !item.github_issue_number" command="github-create">新建 GitHub Issue</el-dropdown-item>
                  <el-dropdown-item v-if="manager && !item.github_issue_number" command="github-link">关联已有 GitHub Issue</el-dropdown-item>
                  <el-dropdown-item v-if="manager && item.github_issue_number && item.github_state !== 'closed'" command="github-close">关闭 GitHub Issue 与需求</el-dropdown-item>
                  <el-dropdown-item v-if="manager && item.github_issue_number" command="github-unlink">取消 Issue 关联</el-dropdown-item>
                  <el-dropdown-item v-if="manager && item.status !== 'closed'" command="close">关闭需求</el-dropdown-item>
                  <el-dropdown-item v-if="manager" divided command="delete">删除需求</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-else class="empty">
      <el-icon><Tickets /></el-icon>
      <div>暂无需求</div>
    </div>

    <div v-if="items.length > pageSize" class="table-foot">
      <span class="total">共 {{ items.length }} 条需求</span>
      <el-pagination
        layout="prev, pager, next"
        :total="items.length"
        :page-size="pageSize"
        :current-page="page"
        @current-change="page = $event"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElButton, ElDropdown, ElDropdownItem, ElDropdownMenu, ElIcon, ElPagination } from 'element-plus'
import { Monitor, MagicStick, Lightning, MoreFilled, Tickets } from '@element-plus/icons-vue'
import type { Requirement } from './api'
import { avatarColor, formatDate, priorityLabel, statusLabel, typeLabel } from './labels'

const props = defineProps<{ items: Requirement[]; manager?: boolean; user?: { id: string } | null }>()
const emit = defineEmits<{ open: [item: Requirement]; action: [payload: { item: Requirement; command: string }] }>()

const pageSize = 8
const page = ref(1)
watch(() => props.items, () => { page.value = 1 })
const pagedItems = computed(() => props.items.slice((page.value - 1) * pageSize, page.value * pageSize))

const typeIcons: Record<string, typeof Monitor> = { feature: Monitor, improvement: MagicStick, bug: Lightning }
const typeIcon = (type: string) => typeIcons[type] || Tickets

const creatorName = (item: Requirement) => item.created_by_name || '用户'
const canWithdraw = (item: Requirement) =>
  !!props.user && item.created_by === props.user.id && !['scheduled', 'developing', 'testing', 'release_ready', 'released'].includes(item.status)
</script>

<style scoped>
.t-feature { background: #eff6ff; color: #2563eb; }
.t-improvement { background: #f5f3ff; color: #7c3aed; }
.t-bug { background: #fff7ed; color: #ea580c; }
.req-number { color: var(--rp-primary); font-size: 12px; font-weight: 700; white-space: nowrap; }
</style>
