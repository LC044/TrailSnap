<template>
  <div class="container mx-auto py-6 px-4">
    <h1 class="text-2xl font-bold mb-6 text-gray-800 dark:text-white">工具箱</h1>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      
      <!-- Low Score Cleanup -->
      <div 
        class="bg-white dark:bg-gray-800 rounded-xl shadow-sm p-6 cursor-pointer hover:shadow-md transition-all border border-gray-100 dark:border-gray-700"
        @click="$router.push('/toolbox/cleanup')"
      >
        <div class="flex items-center gap-4 mb-3">
          <div class="w-12 h-12 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center text-red-500">
            <Trash2 class="w-6 h-6" />
          </div>
          <div>
            <h3 class="font-bold text-lg text-gray-800 dark:text-gray-100">低分清理</h3>
            <p class="text-sm text-gray-500 dark:text-gray-400">清理模糊、低质量照片</p>
          </div>
        </div>
      </div>

      <!-- Similar Photo Cleanup -->
      <div 
        class="bg-white dark:bg-gray-800 rounded-xl shadow-sm p-6 cursor-pointer hover:shadow-md transition-all border border-gray-100 dark:border-gray-700"
        @click="$router.push('/toolbox/similar')"
      >
        <div class="flex items-center gap-4 mb-3">
          <div class="w-12 h-12 rounded-full bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center text-blue-500">
            <Images class="w-6 h-6" />
          </div>
          <div>
            <h3 class="font-bold text-lg text-gray-800 dark:text-gray-100">相似照片清理</h3>
            <p class="text-sm text-gray-500 dark:text-gray-400">聚类相似照片，保留最佳</p>
          </div>
        </div>
      </div>

      <!-- Clean Duplicates -->
      <div 
        class="bg-white dark:bg-gray-800 rounded-xl shadow-sm p-6 cursor-pointer hover:shadow-md transition-all border border-gray-100 dark:border-gray-700"
        @click="$router.push('/toolbox/duplicate')"
      >
        <div class="flex items-center gap-4 mb-3">
          <div class="w-12 h-12 rounded-full bg-orange-100 dark:bg-orange-900/30 flex items-center justify-center text-orange-500">
            <Copy class="w-6 h-6" />
          </div>
          <div>
            <h3 class="font-bold text-lg text-gray-800 dark:text-gray-100">清理重复</h3>
            <p class="text-sm text-gray-500 dark:text-gray-400">清理完全重复的照片</p>
          </div>
        </div>
      </div>

      <!-- Organize Photos -->
      <div 
        class="bg-white dark:bg-gray-800 rounded-xl shadow-sm p-6 cursor-pointer hover:shadow-md transition-all border border-gray-100 dark:border-gray-700"
        @click="$router.push('/toolbox/organize')"
      >
        <div class="flex items-center gap-4 mb-3">
          <div class="w-12 h-12 rounded-full bg-purple-100 dark:bg-purple-900/30 flex items-center justify-center text-purple-500">
            <FolderOpen class="w-6 h-6" />
          </div>
          <div>
            <h3 class="font-bold text-lg text-gray-800 dark:text-gray-100">图片整理</h3>
            <p class="text-sm text-gray-500 dark:text-gray-400">按时间/分类/人物自动归档</p>
          </div>
        </div>
      </div>

      <!-- Batch Rename -->
      <div 
        class="bg-white dark:bg-gray-800 rounded-xl shadow-sm p-6 cursor-pointer hover:shadow-md transition-all border border-gray-100 dark:border-gray-700"
        @click="$router.push('/toolbox/rename')"
      >
        <div class="flex items-center gap-4 mb-3">
          <div class="w-12 h-12 rounded-full bg-teal-100 dark:bg-teal-900/30 flex items-center justify-center text-teal-500">
            <Tag class="w-6 h-6" />
          </div>
          <div>
            <h3 class="font-bold text-lg text-gray-800 dark:text-gray-100">批量重命名</h3>
            <p class="text-sm text-gray-500 dark:text-gray-400">按时间规则统一重命名图片</p>
          </div>
        </div>
      </div>

      <!-- Time From Filename -->
      <div 
        class="bg-white dark:bg-gray-800 rounded-xl shadow-sm p-6 cursor-pointer hover:shadow-md transition-all border border-gray-100 dark:border-gray-700"
        @click="$router.push('/toolbox/time-from-filename')"
      >
        <div class="flex items-center gap-4 mb-3">
          <div class="w-12 h-12 rounded-full bg-indigo-100 dark:bg-indigo-900/30 flex items-center justify-center text-indigo-500">
            <Clock class="w-6 h-6" />
          </div>
          <div>
            <h3 class="font-bold text-lg text-gray-800 dark:text-gray-100">修改图片元数据</h3>
            <p class="text-sm text-gray-500 dark:text-gray-400">根据文件名批量修改照片拍摄时间</p>
          </div>
        </div>
      </div>

    </div>

    <!-- Right side: Activity/Stats placeholder -->
    <div class="mt-12 space-y-6">
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
import { Trash2, Images, Copy, FolderOpen, Tag, Clock } from 'lucide-vue-next'
</script>
