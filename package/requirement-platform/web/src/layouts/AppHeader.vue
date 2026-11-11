<template>
  <header class="topbar">
    <!-- 桌面：左侧纵向导航栏 -->
    <div class="topbar-inner desktop-nav">
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

    <!-- 移动端：顶部横向导航栏 -->
    <div class="mobile-nav">
      <div class="mobile-bar">
        <button class="mobile-brand" type="button" aria-label="返回公开需求" @click="go(items[0]?.key ?? 'public')">
          <img :src="logoUrl" alt="" />
          <span class="mobile-brand-copy"><strong>行影集</strong><small>需求管理平台</small></span>
        </button>
        <div class="mobile-actions">
          <button class="icon-btn" type="button" aria-label="通知" @click="$emit('notification')"><el-icon :size="18"><Bell /></el-icon></button>
          <el-dropdown v-if="user" trigger="click" @command="$emit('user-command', $event)">
            <button class="mobile-user" type="button" :aria-label="`账号：${user.username}`"><span class="avatar" :style="{ width: '30px', height: '30px', fontSize: '13px', ...avatarColor(user.username) }">{{ user.username.slice(0, 1) }}</span></button>
            <template #dropdown><el-dropdown-menu><el-dropdown-item command="mine">我的需求</el-dropdown-item><el-dropdown-item command="logout" divided>退出登录</el-dropdown-item></el-dropdown-menu></template>
          </el-dropdown>
          <el-button v-else size="small" type="primary" @click="$emit('login')">登录</el-button>
          <button class="icon-btn menu-toggle" type="button" :aria-label="menuOpen ? '关闭全部页面菜单' : '打开全部页面菜单'" :aria-expanded="menuOpen" aria-controls="rp-mobile-menu" @click="menuOpen = !menuOpen">
            <el-icon :size="20"><Close v-if="menuOpen" /><Menu v-else /></el-icon>
          </button>
        </div>
      </div>

      <nav ref="mobileNavElement" class="mobile-tabs" aria-label="主导航">
        <button v-for="item in items" :key="item.key" type="button" :class="{ active: active === item.key }" :aria-current="active === item.key ? 'page' : undefined" @click="go(item.key)">
          <el-icon :size="15"><component :is="item.icon" /></el-icon><span>{{ shortLabel(item.label) }}</span>
        </button>
      </nav>

      <div v-if="menuOpen" id="rp-mobile-menu" class="mobile-menu">
        <div class="mobile-menu-head"><span>全部页面</span><small>{{ items.length }} 个入口</small></div>
        <div class="mobile-menu-grid">
          <button v-for="item in items" :key="item.key" type="button" :class="{ active: active === item.key }" @click="go(item.key)">
            <span class="mobile-menu-icon"><el-icon :size="18"><component :is="item.icon" /></el-icon></span>
            <span class="mobile-menu-label">{{ item.label }}</span>
          </button>
        </div>
      </div>
      <div v-if="menuOpen" class="mobile-menu-mask" @click="menuOpen = false"></div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch, type Component } from 'vue'
import { ArrowDown, Bell, Close, Expand, Fold, Menu, User } from '@element-plus/icons-vue'
import logoUrl from '../assets/logo.svg'
import { avatarColor } from '../labels'
import type { User as ApiUser } from '../api'
import type { AppTab } from '../router'

const props = defineProps<{ items: Array<{ key: AppTab; label: string; icon: Component }>; active: AppTab; collapsed: boolean; user: ApiUser | null }>()
const emit = defineEmits<{ navigate: [tab: AppTab]; notification: []; login: []; toggle: []; 'user-command': [command: string | number | object] }>()
const navElement = ref<HTMLElement | null>(null)
const mobileNavElement = ref<HTMLElement | null>(null)
const menuOpen = ref(false)

const shortLabels: Record<string, string> = {
  '公开需求': '公开', '提交需求': '提交', '我的需求与本机记录': '我的', '本机提交记录': '本机记录',
  '版本计划': '版本', 'Token 用量': '用量', '总览看板': '总览', '需求审核': '审核',
  'AI 设置': 'AI 设置', '集成设置': '集成', '角色管理': '角色',
}
const shortLabel = (label: string) => shortLabels[label] ?? label
function go(key: AppTab) {
  menuOpen.value = false
  emit('navigate', key)
}
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') menuOpen.value = false
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
watch(() => props.active, () => { menuOpen.value = false })

function scrollActiveIntoView() {
  for (const node of [navElement.value, mobileNavElement.value]) {
    node?.querySelector<HTMLElement>('button.active')?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' })
  }
}
const exposedElement = computed(() => navElement.value)
defineExpose({ element: exposedElement, scrollActiveIntoView })
</script>
