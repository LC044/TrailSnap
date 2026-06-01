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
      <!-- 顶部导航 -->
      <NavBar />
      
      <!-- 页面内容 -->
      <main class="flex-1 overflow-y-auto bg-slate-50 dark:bg-gray-900 box-border dark:from-gray-900 dark:to-gray-800 relative pt-[60px] md:pt-0">
        <transition name="fade-slide" mode="out-in">
          <router-view />
        </transition>
      </main>
    </div>

    <!-- 悬浮的 Agent 助手按钮 -->
    <button 
      v-show="!isAgentOpen && $route.name !== 'Login'" 
      @click="isAgentOpen = true"
      class="fixed bottom-6 right-6 sm:bottom-8 sm:right-8 z-50 w-14 h-14 bg-indigo-600 hover:bg-indigo-700 text-white rounded-full shadow-lg shadow-indigo-500/30 flex items-center justify-center transition-transform hover:scale-110 active:scale-95 group"
    >
      <Bot class="w-6 h-6 group-hover:animate-bounce" />
    </button>

    <!-- Agent 聊天弹窗 -->
    <AgentChat v-model="isAgentOpen" />
  </div>
</template>

<script setup lang="ts">
import { ref, provide } from 'vue';
// 导入导航栏、侧边栏
import NavBar from '@/layouts/NavBar.vue';
import Sidebar from '@/layouts/Sidebar.vue';
import AgentChat from '@/views/agent/AgentChat.vue';
import { Bot } from 'lucide-vue-next';
// 导入主题逻辑
import { provideTheme } from '@/composables/useTheme';

const isAgentOpen = ref(false);

// 提供主题状态
const {
  isDarkMode,
  currentTheme,
  themeStyle,
  themeColors,
  setMode,
  setTheme
} = provideTheme();
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