<template>
  <aside
    :class="[
      'flex flex-col transition-all duration-300 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 shrink-0 z-40',
      isCollapsed ? 'w-16' : 'w-64'
    ]"
  >
    <!-- 顶部 Logo 区域 (可折叠) -->
    <div class="h-14 flex items-center justify-between px-4 border-b border-slate-200 dark:border-slate-800 shrink-0">
      <div class="flex items-center overflow-hidden whitespace-nowrap">
        <img src="@/assets/logo.svg" alt="Logo" class="w-8 h-8 shrink-0" />
        <transition name="fade">
          <h1 v-if="!isCollapsed" class="ml-3 font-bold text-lg text-slate-800 dark:text-slate-100">
            行影集
          </h1>
        </transition>
      </div>
      <!-- 折叠按钮 (仅在非手机端显示？也可以手机端隐藏侧边栏) -->
      <button
        @click="toggleCollapse"
        :title="isCollapsed ? '展开侧边栏' : '折叠侧边栏'"
        class="bg-transparent p-1 rounded-md text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors hidden md:block"
      >
        <Menu v-if="isCollapsed" class="w-5 h-5" />
        <ChevronLeft v-else class="w-5 h-5" />
      </button>
    </div>

    <!-- 主要导航菜单 -->
    <nav class="flex-1 overflow-y-auto py-4 px-2 space-y-1 custom-scrollbar">
      <RouterLink
        v-for="item in navLinks"
        :key="item.href"
        :to="item.href"
        :title="isCollapsed ? item.label : undefined"
        class="flex items-center px-3 py-2.5 rounded-lg text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-primary-600 dark:hover:text-primary-400 transition-colors group relative"
        :class="{ 'bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400 font-medium': isActiveRoute(item.href) }"
      >
        <component :is="item.icon" class="w-5 h-5 shrink-0" />
        <transition name="fade">
          <span v-if="!isCollapsed" class="ml-3 truncate">{{ item.label }}</span>
        </transition>
      </RouterLink>

      <div class="my-4 border-t border-slate-200 dark:border-slate-800"></div>

      <!-- 更多工具 -->
      <RouterLink
        v-for="item in moreLinks"
        :key="item.href"
        :to="item.href"
        :title="isCollapsed ? item.label : undefined"
        class="flex items-center px-3 py-2.5 rounded-lg text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-primary-600 dark:hover:text-primary-400 transition-colors group"
        :class="{ 'bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400 font-medium': isActiveRoute(item.href) }"
      >
        <component :is="item.icon" class="w-5 h-5 shrink-0" />
        <transition name="fade">
          <span v-if="!isCollapsed" class="ml-3 truncate">{{ item.label }}</span>
        </transition>
      </RouterLink>

      <!-- 预留的自定义选项区块占位 -->
      <div v-if="!isCollapsed" class="mt-8 px-3">
        <div class="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-2">
          自定义
        </div>
        <div class="p-3 border border-dashed border-slate-300 dark:border-slate-700 rounded-lg text-center text-sm text-slate-500">
          自定义选项区(占位)
        </div>
      </div>
    </nav>

    <!-- 底部设置与回收站入口 -->
    <div class="p-2 border-t border-slate-200 dark:border-slate-800 shrink-0 space-y-1">
      <RouterLink
        to="/recycle-bin"
        :title="isCollapsed ? '回收站' : undefined"
        class="flex items-center px-3 py-2.5 rounded-lg text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-primary-600 dark:hover:text-primary-400 transition-colors group"
        :class="{ 'bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400 font-medium': isActiveRoute('/recycle-bin') }"
      >
        <Trash2 class="w-5 h-5 shrink-0" />
        <transition name="fade">
          <span v-if="!isCollapsed" class="ml-3 truncate">回收站</span>
        </transition>
      </RouterLink>
      
      <RouterLink
        to="/settings"
        :title="isCollapsed ? '设置' : undefined"
        class="flex items-center px-3 py-2.5 rounded-lg text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-primary-600 dark:hover:text-primary-400 transition-colors group"
        :class="{ 'bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400 font-medium': isActiveRoute('/settings') }"
      >
        <Settings class="w-5 h-5 shrink-0" />
        <transition name="fade">
          <span v-if="!isCollapsed" class="ml-3 truncate">设置</span>
        </transition>
      </RouterLink>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Home,
  Image as ImageIcon,
  Images,
  Ticket,
  Wrench,
  Settings,
  ChevronLeft,
  Menu,
  Trash2
} from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()

// 路由激活状态判断：完全匹配，避免首页（/）一直处于激活状态
const isActiveRoute = (path: string) => {
  if (path === '/') {
    return route.path === '/'
  }
  return route.path.startsWith(path)
}

const isCollapsed = ref(false)

const toggleCollapse = () => {
  isCollapsed.value = !isCollapsed.value
}

const navLinks = [
  { label: '首页', href: '/', icon: Home },
  { label: '照片', href: '/photos', icon: ImageIcon },
  { label: '相册', href: '/album', icon: Images },
]

const moreLinks = [
  { label: '车票', href: '/ticket', icon: Ticket },
  { label: '工具箱', href: '/toolbox', icon: Wrench },
]
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease, width 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  width: 0;
}

.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: #cbd5e1;
  border-radius: 4px;
}
.dark .custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: #475569;
}
</style>
