<template>
  <section>
    <div class="page-head">
      <div class="page-head-left"><div class="page-head-icon"><el-icon :size="26"><Checked /></el-icon></div><div><h1>需求审核</h1><p class="sub">AI 提供建议，最终结论由所有者或管理员确认</p><p class="desc">处理待审核需求，维护候选池质量。</p></div></div>
      <div class="page-head-actions">
        <el-select :model-value="status" clearable placeholder="全部状态" style="width:150px" @update:model-value="$emit('update:status', String($event || ''))" @change="$emit('reload')"><el-option v-for="item in statuses" :key="item" :label="statusLabel(item)" :value="item" /></el-select>
        <el-button :icon="Refresh" @click="$emit('reload')">刷新</el-button><el-button type="primary" :loading="syncing" @click="$emit('sync')">从 GitHub 同步</el-button>
      </div>
    </div>
    <RequirementTable :items="items" manager :user="user" @open="$emit('open', $event)" @action="$emit('action', $event)" />
  </section>
</template>

<script setup lang="ts">
import { Checked, Refresh } from '@element-plus/icons-vue'
import RequirementTable from '../../RequirementTable.vue'
import { statusLabel } from '../../labels'
import type { Requirement, User } from '../../api'
defineProps<{ items: Requirement[]; user: User | null; status: string; statuses: string[]; syncing: boolean }>()
defineEmits<{ reload: []; sync: []; open: [item: Requirement]; action: [payload: { item: Requirement; command: string }]; 'update:status': [value: string] }>()
</script>
