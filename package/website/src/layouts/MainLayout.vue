<!-- src/layouts/MainLayout.vue -->
<template>
  <div
    :class="[isDarkMode ? 'dark' : '']"
    :style="themeStyle"
    class="h-screen w-full flex font-sans transition-colors duration-300 bg-slate-50 dark:bg-slate-900 text-slate-700 dark:text-slate-200 overflow-hidden"
  >
    <!-- 左侧导航栏 -->
    <Sidebar class="hidden md:flex" />

    <!-- 右侧主体内容区 -->
    <div class="flex-1 flex flex-col min-w-0 transition-all duration-300 relative" id="main-content-wrapper">
      <!-- 页面内容（移动端底部留出 Tab 栏 + safe-area 高度） -->
      <main class="flex-1 overflow-y-auto bg-slate-50 dark:bg-slate-900 box-border relative pb-[calc(var(--ts-tabbar-h)_+_env(safe-area-inset-bottom))] md:pb-0">
        <transition name="fade-slide" mode="out-in">
          <router-view />
        </transition>
      </main>
    </div>

    <!-- 移动端底部 Tab 栏（fixed，仅 <768px 显示） -->
    <BottomNav />

    <!-- Agent 聊天弹窗 -->
    <AgentChat v-model="isAgentOpen" />

    <!-- 通知抽屉 + 设置弹窗（全局唯一一份，由 Sidebar 的铃铛 / 移动端 BottomNav 更多 sheet 里的铃铛触发） -->
    <NotificationDrawer />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
// 导入侧边栏（桌面）/ 底部 Tab 栏（移动）
import BottomNav from '@/layouts/BottomNav.vue';
import Sidebar from '@/layouts/Sidebar.vue';
// AgentChat 仍用同步 import：dev 模式下 defineAsyncComponent 会让 vite 在首次打开助手时
// 现编译整条依赖链（PhotoLightbox / markdown-it / dompurify），耗时超过 e2e 的 10s 超时。
// 生产构建时，AgentChat 的重依赖（xgplayer / fabric 等）已被 PhotoLightbox / PhotoEditor
// 内部的动态 import 切到独立 chunk，不会回流到 entry，首屏体积不受影响。
import AgentChat from '@/views/agent/AgentChat.vue';
import NotificationDrawer from '@/components/NotificationDrawer.vue';
// 从根组件注入主题（避免重复 provide 导致主题状态分裂）
import { injectTheme } from '@/composables/useTheme';
import { useUiStore } from '@/stores/uiStore';
import { useOverlayStack } from '@/composables/useOverlayStack';

const uiStore = useUiStore();
const isAgentOpen = computed({
  get: () => uiStore.agentOpen,
  set: value => uiStore.setAgentOpen(value),
});
useOverlayStack(isAgentOpen, () => uiStore.closeAgent());

// 注入由 App.vue 提供的主题状态
const {
  isDarkMode,
  currentTheme,
  themeStyle,
  themeColors,
  setMode,
  setTheme
} = injectTheme();

</script>

<style scoped>

/* 页面过渡动画（原 App.vue 中的样式） */
.fade-slide-enter-active {
  transition: opacity 0.5s ease, transform 0.5s ease;
}
.fade-slide-enter-from {
  opacity: 0;
  transform: translateY(20px);
}
.fade-slide-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-20px);
}
</style>
