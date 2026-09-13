<template>
  <section>
    <div class="page-head"><div class="page-head-left"><div class="page-head-icon"><el-icon :size="26"><UserFilled /></el-icon></div><div><h1>角色管理</h1><p class="sub">所有者可以任命或移除管理员</p></div></div></div>
    <el-table :data="users" class="panel users-panel">
      <el-table-column prop="username" label="用户名" /><el-table-column prop="email" label="邮箱" />
      <el-table-column prop="role" label="角色"><template #default="scope"><span class="tag no-dot plain">{{ roleLabel(scope.row.role) }}</span></template></el-table-column>
      <el-table-column label="GitHub"><template #default="scope">{{ scope.row.github ? `@${scope.row.github.login}` : '未绑定' }}</template></el-table-column>
      <el-table-column label="操作"><template #default="scope"><el-button v-if="scope.row.role !== 'owner'" size="small" @click="$emit('toggle-role', scope.row)">{{ scope.row.role === 'admin' ? '降为查看者' : '设为管理员' }}</el-button></template></el-table-column>
    </el-table>
  </section>
</template>

<script setup lang="ts">
import { UserFilled } from '@element-plus/icons-vue'
import { roleLabel } from '../../labels'
import type { User } from '../../api'
defineProps<{ users: User[] }>()
defineEmits<{ 'toggle-role': [user: User] }>()
</script>
