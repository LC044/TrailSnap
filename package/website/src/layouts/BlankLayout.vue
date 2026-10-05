<!-- src/layouts/BlankLayout.vue -->
<template>
  <div class="ts-blank-layout ts-page-background h-screen overflow-y-auto font-sans">
    <router-view v-slot="{ Component }">
      <transition name="fade-slide" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>
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
  transition: opacity var(--ts-motion-normal) ease, transform var(--ts-motion-page) var(--ts-ease);
}
.fade-slide-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
</style>
