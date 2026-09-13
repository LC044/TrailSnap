<template>
  <section>
    <div class="page-head">
      <div class="page-head-left"><div class="page-head-icon"><el-icon :size="26"><Collection /></el-icon></div><div><h1>我的需求</h1><p class="sub">查看自己提交的需求和处理进度</p><p class="desc">跟踪每一条需求从提交到上线的全过程。</p></div></div>
    </div>
    <div v-if="!user" class="panel empty"><el-icon><User /></el-icon><div>登录后查看自己的需求</div><div class="actions" style="justify-content:center"><el-button type="primary" @click="$emit('login')">登录 / 注册</el-button></div></div>
    <RequirementTable v-else :items="items" :manager="manager" :user="user" @open="$emit('open', $event)" @action="$emit('action', $event)" />
  </section>
</template>

<script setup lang="ts">
import { Collection, User } from '@element-plus/icons-vue'
import RequirementTable from '../../RequirementTable.vue'
import type { Requirement, User as ApiUser } from '../../api'
defineProps<{ items: Requirement[]; manager: boolean; user: ApiUser | null }>()
defineEmits<{ login: []; open: [item: Requirement]; action: [payload: { item: Requirement; command: string }] }>()
</script>
