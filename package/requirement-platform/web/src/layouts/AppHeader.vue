<template>
  <header class="topbar">
    <div class="topbar-inner">
      <div class="brand"><img :src="logoUrl" alt="行影集" /><span class="brand-copy"><span>行影集</span><small>需求管理平台</small></span></div>
      <nav ref="navElement" class="nav" aria-label="主导航">
        <button v-for="item in items" :key="item.key" :class="{ active: active === item.key }" :title="collapsed ? item.label : undefined" @click="$emit('navigate', item.key)"><el-icon :size="19"><component :is="item.icon" /></el-icon><span class="nav-label">{{ item.label }}</span></button>
      </nav>
      <div class="topbar-side">
        <button class="icon-btn" type="button" aria-label="通知" @click="$emit('notification')"><el-icon :size="18"><Bell /></el-icon></button>
        <el-dropdown v-if="user" trigger="click" @command="$emit('user-command', $event)">
          <button class="user-chip" type="button"><span class="avatar" :style="{ width: '30px', height: '30px', fontSize: '13px', ...avatarColor(user.username) }">{{ user.username.slice(0, 1) }}</span><span class="nav-label" style="font-size:14px">{{ user.username }}</span><el-icon :size="12"><ArrowDown /></el-icon></button>
          <template #dropdown><el-dropdown-menu><el-dropdown-item command="mine">我的需求</el-dropdown-item><el-dropdown-item command="logout" divided>退出登录</el-dropdown-item></el-dropdown-menu></template>
        </el-dropdown>
        <el-button v-else type="primary" @click="$emit('login')"><span class="nav-label">登录 / 注册</span><el-icon class="collapsed-login"><User /></el-icon></el-button>
        <button class="collapse-btn" type="button" :aria-label="collapsed ? '展开导航' : '折叠导航'" @click="$emit('toggle')"><el-icon><Expand v-if="collapsed" /><Fold v-else /></el-icon><span class="nav-label">折叠导航</span></button>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { ref, type Component } from 'vue'
import { ArrowDown, Bell, Expand, Fold, User } from '@element-plus/icons-vue'
import logoUrl from '../assets/logo.svg'
import { avatarColor } from '../labels'
import type { User as ApiUser } from '../api'
import type { AppTab } from '../router'

defineProps<{ items: Array<{ key: AppTab; label: string; icon: Component }>; active: AppTab; collapsed: boolean; user: ApiUser | null }>()
defineEmits<{ navigate: [tab: AppTab]; notification: []; login: []; toggle: []; 'user-command': [command: string | number | object] }>()
const navElement = ref<HTMLElement | null>(null)
defineExpose({ element: navElement })
</script>
