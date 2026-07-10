<template>
  <div class="container mx-auto py-4 md:py-6 px-4">
    <h1 class="text-xl md:text-2xl font-bold mb-4 md:mb-6 text-gray-800 dark:text-white">工具箱</h1>

    <!-- Mobile: compact grouped list (one card, row dividers, chevrons).
         Desktop: card grid. -->
    <div class="bg-white dark:bg-gray-800 md:bg-transparent md:dark:bg-transparent
                rounded-xl md:rounded-none overflow-hidden md:overflow-visible
                border border-gray-100 dark:border-gray-700 md:border-0
                md:grid md:grid-cols-2 lg:grid-cols-3 md:gap-6">
      <div
        v-for="tool in tools"
        :key="tool.path"
        @click="$router.push(tool.path)"
        class="flex items-center gap-3 md:gap-4 px-4 py-3 md:p-6 cursor-pointer transition-colors
               border-b border-gray-100 dark:border-gray-700 last:border-b-0
               md:border md:rounded-xl md:shadow-sm md:hover:shadow-md md:transition-all
               md:border-gray-100 md:dark:border-gray-700
               hover:bg-gray-50 dark:hover:bg-gray-700/50
               md:hover:bg-transparent md:dark:hover:bg-transparent
               active:bg-gray-100 dark:active:bg-gray-700 md:active:bg-transparent"
      >
        <div class="w-9 h-9 md:w-12 md:h-12 rounded-lg md:rounded-full flex items-center justify-center flex-shrink-0 bg-primary-50 dark:bg-primary-900/20 text-primary-500">
          <component :is="tool.icon" class="w-5 h-5 md:w-6 md:h-6" />
        </div>
        <div class="flex-1 min-w-0">
          <h3 class="font-medium md:font-bold text-sm md:text-lg text-gray-800 dark:text-gray-100">{{ tool.title }}</h3>
          <p class="text-xs md:text-sm text-gray-500 dark:text-gray-400 truncate md:truncate-none">{{ tool.desc }}</p>
        </div>
        <ChevronRight class="w-4 h-4 text-gray-300 dark:text-gray-600 md:hidden flex-shrink-0" />
      </div>
    </div>

    <!-- Recent activity: desktop only — an empty placeholder is just noise on a phone. -->
    <div class="mt-12 space-y-6 hidden md:block">
      <h2 class="text-lg font-bold text-gray-800 dark:text-white flex items-center gap-2">
        <Clock class="w-5 h-5 text-primary-500" />
        最近活动
      </h2>
      <div class="flex items-center justify-center h-48 bg-gray-50 dark:bg-gray-900/50 rounded-lg border border-gray-200 dark:border-gray-700 text-gray-400">
        暂无最近活动
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Trash2, Images, Copy, FolderOpen, Tag, Clock, ChevronRight } from 'lucide-vue-next'

const tools = [
  { path: '/toolbox/cleanup', title: '低分清理', desc: '清理模糊、低质量照片', icon: Trash2 },
  { path: '/toolbox/similar', title: '相似照片清理', desc: '聚类相似照片，保留最佳', icon: Images },
  { path: '/toolbox/duplicate', title: '清理重复', desc: '清理完全重复的照片', icon: Copy },
  { path: '/toolbox/organize', title: '图片整理', desc: '按时间/分类/人物自动归档', icon: FolderOpen },
  { path: '/toolbox/rename', title: '批量重命名', desc: '按时间规则统一重命名图片', icon: Tag },
  { path: '/toolbox/time-from-filename', title: '修改图片元数据', desc: '根据文件名批量修改照片拍摄时间', icon: Clock },
]
</script>
