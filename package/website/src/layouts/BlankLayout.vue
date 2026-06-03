<!-- src/layouts/BlankLayout.vue -->
<template>
  <div class="min-h-screen font-sans bg-slate-50 dark:bg-slate-900 text-slate-700 dark:text-slate-200">
    <transition name="fade-slide" mode="out-in">
      <router-view />
    </transition>
  </div>
</template>

<script setup lang="ts">
// 空白布局无需导航/页脚，仅提供基础容器
// 主题由 App.vue 统一 provide，此处直接 inject，保证主布局与空白布局共享同一份主题状态
import { injectTheme } from '@/composables/useTheme';
injectTheme();
</script>

<style scoped>
/* 复用过渡动画 */
.fade-slide-enter-active {
  transition: opacity 0.5s ease, transform 0.5s ease;
}
.fade-slide-enter-from {
  opacity: 0;
  transform: translateY(20px);
}
</style>