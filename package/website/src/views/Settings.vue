<template>
  <!-- 禁用滚动条 -->
  <div class="flex flex-col md:flex-row bg-gray-50 dark:bg-gray-900 scrollbar-hide h-full">
    <!-- Sidebar -->
    <div class="w-full md:w-64 bg-white dark:bg-gray-800 border-b md:border-b-0 md:border-r border-gray-200 dark:border-gray-700 flex-shrink-0">
      <div class="hidden md:block md:p-6">
        <h1 class="text-xl font-bold text-gray-800 dark:text-white">设置中心</h1>
      </div>
      <nav class="flex md:block overflow-x-auto md:overflow-visible pb-2 md:pb-0 mt-0 md:mt-2 px-4 md:px-0 scrollbar-hide">
        <a 
          v-for="item in menuItems" 
          :key="item.key"
          @click="activeTab = item.key"
          class="flex items-center px-4 md:px-6 py-2 md:py-3 text-sm md:text-base text-gray-600 dark:text-white hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer transition-colors whitespace-nowrap md:whitespace-normal mr-2 md:mr-0 rounded-full md:rounded-none"
          :class="{ 'bg-blue-50 text-primary-500 md:border-r-2 border-primary-500 dark:bg-gray-700 dark:text-primary-400': activeTab === item.key }"
        >
          <component :is="item.icon" class="w-5 h-5 mr-2 md:mr-3" />
          {{ item.label }}
        </a>
      </nav>
    </div>

    <!-- Content Area -->
    <div class="flex-1 overflow-auto p-4 md:p-8 max-w-5xl md:mx-auto">
      <UserManagement v-if="activeTab === 'user'" />
      <TaskManagement v-if="activeTab === 'tasks'" />
      <BasicSettings v-if="activeTab === 'basic'" />
      <ExternalGallery v-if="activeTab === 'external'" />
      <Tokens v-if="activeTab === 'tokens'" />
      <AboutPage v-if="activeTab === 'about'" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { User, List, Settings, FolderOpen, Info, Key } from 'lucide-vue-next'
import UserManagement from './settings/UserManagement.vue'
import TaskManagement from './settings/TaskManagement.vue'
import BasicSettings from './settings/BasicSettings.vue'
import ExternalGallery from './settings/ExternalGallery.vue'
import Tokens from './settings/Tokens.vue'
import AboutPage from './settings/AboutPage.vue'

const router = useRouter()
const route = useRoute()

const activeTab = ref('user')
const menuItems = [
  { key: 'user', label: '用户管理', icon: User },
  { key: 'tasks', label: '任务管理', icon: List },
  { key: 'basic', label: '基础设置', icon: Settings },
  { key: 'external', label: '外部图库', icon: FolderOpen },
  { key: 'tokens', label: '令牌管理', icon: Key },
  { key: 'about', label: '关于行影集', icon: Info },
]

// Handle URL hash navigation
watch(() => route.hash, (newHash) => {
  if (newHash) {
    const key = newHash.replace('#', '')
    if (menuItems.some(item => item.key === key)) {
      activeTab.value = key
    }
  }
}, { immediate: true })

watch(activeTab, (newTab) => {
  router.replace({ hash: `#${newTab}` })
})
</script>
