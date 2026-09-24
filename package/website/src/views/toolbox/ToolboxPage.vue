<template>
  <AppPage size="wide" bottom-safe class="py-5 md:py-8">
    <header class="relative overflow-hidden rounded-2xl border border-gray-200/80 bg-white px-5 py-5 shadow-sm dark:border-gray-800 dark:bg-gray-800 md:px-7 md:py-7">
      <div class="pointer-events-none absolute -right-16 -top-20 h-48 w-48 rounded-full bg-primary-500/10 blur-3xl" aria-hidden="true" />
      <div class="relative flex items-start justify-between gap-4">
        <div class="min-w-0">
          <div class="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-400 md:h-12 md:w-12">
            <Wrench class="h-5 w-5 md:h-6 md:w-6" />
          </div>
          <h1 class="text-2xl font-bold tracking-tight text-gray-950 dark:text-white md:text-3xl">工具箱</h1>
          <p class="mt-1.5 max-w-xl text-sm leading-6 text-gray-500 dark:text-gray-400 md:text-base">批量整理、清理与修复你的照片库</p>
        </div>
        <span class="shrink-0 rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-500 dark:border-gray-700 dark:bg-gray-900/60 dark:text-gray-400">6 项工具</span>
      </div>
    </header>

    <section class="mt-7 md:mt-9" aria-labelledby="cleanup-heading">
      <div class="mb-3 flex items-end justify-between gap-4 md:mb-4">
        <div>
          <p class="mb-1 text-xs font-semibold tracking-wider text-primary-600 dark:text-primary-400">释放存储空间</p>
          <h2 id="cleanup-heading" class="text-lg font-bold text-gray-950 dark:text-white md:text-xl">空间清理</h2>
        </div>
        <p class="hidden text-sm text-gray-500 dark:text-gray-400 sm:block">找出不需要的照片，再由你确认删除</p>
      </div>

      <div class="grid grid-cols-2 gap-3 md:grid-cols-3 md:gap-5">
        <RouterLink
          v-for="(tool, index) in cleanupTools"
          :key="tool.path"
          :to="tool.path"
          class="group relative flex min-h-40 flex-col overflow-hidden rounded-2xl border border-gray-200/80 bg-white p-4 shadow-sm transition duration-200 hover:-translate-y-0.5 hover:border-primary-500/40 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:border-gray-800 dark:bg-gray-800 dark:hover:border-primary-500/40 dark:focus-visible:ring-offset-gray-900 md:min-h-48 md:p-5"
          :class="index === 2 ? 'col-span-2 md:col-span-1' : ''"
        >
          <div class="flex items-start justify-between gap-3">
            <span class="flex h-11 w-11 items-center justify-center rounded-xl bg-primary-50 text-primary-600 transition-colors group-hover:bg-primary-100 dark:bg-primary-900/30 dark:text-primary-400 dark:group-hover:bg-primary-900/50">
              <component :is="tool.icon" class="h-5 w-5" />
            </span>
            <ArrowUpRight class="h-4 w-4 text-gray-300 transition group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-primary-500 dark:text-gray-600" />
          </div>
          <div class="mt-auto pt-5">
            <h3 class="text-base font-semibold text-gray-900 dark:text-gray-100 md:text-lg">{{ tool.title }}</h3>
            <p class="mt-1 text-xs leading-5 text-gray-500 dark:text-gray-400 md:text-sm">{{ tool.desc }}</p>
          </div>
        </RouterLink>
      </div>
    </section>

    <section class="mt-8 md:mt-10" aria-labelledby="manage-heading">
      <div class="mb-3 md:mb-4">
        <p class="mb-1 text-xs font-semibold tracking-wider text-primary-600 dark:text-primary-400">批量处理照片</p>
        <h2 id="manage-heading" class="text-lg font-bold text-gray-950 dark:text-white md:text-xl">照片管理</h2>
      </div>

      <div class="overflow-hidden rounded-2xl border border-gray-200/80 bg-white shadow-sm dark:border-gray-800 dark:bg-gray-800 md:grid md:grid-cols-3 md:gap-5 md:overflow-visible md:border-0 md:bg-transparent md:shadow-none md:dark:bg-transparent">
        <RouterLink
          v-for="tool in managementTools"
          :key="tool.path"
          :to="tool.path"
          class="group flex min-h-[76px] items-center gap-3.5 border-b border-gray-200/80 px-4 py-3.5 transition-colors last:border-b-0 hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500 dark:border-gray-700 dark:hover:bg-gray-700/50 md:min-h-28 md:rounded-2xl md:border md:border-gray-200/80 md:bg-white md:p-5 md:shadow-sm md:transition md:duration-200 md:hover:-translate-y-0.5 md:hover:border-primary-500/40 md:hover:bg-white md:hover:shadow-md md:focus-visible:ring-inset-0 md:focus-visible:ring-offset-2 md:dark:border-gray-800 md:dark:bg-gray-800 md:dark:hover:border-primary-500/40 md:dark:hover:bg-gray-800 md:dark:focus-visible:ring-offset-gray-900"
        >
          <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-400 md:h-11 md:w-11">
            <component :is="tool.icon" class="h-5 w-5" />
          </span>
          <span class="min-w-0 flex-1">
            <span class="block text-sm font-semibold text-gray-900 dark:text-gray-100 md:text-base">{{ tool.title }}</span>
            <span class="mt-0.5 block text-xs leading-5 text-gray-500 dark:text-gray-400 md:text-sm">{{ tool.desc }}</span>
          </span>
          <ChevronRight class="h-4 w-4 shrink-0 text-gray-300 transition-transform group-hover:translate-x-0.5 group-hover:text-primary-500 dark:text-gray-600" />
        </RouterLink>
      </div>
    </section>

    <div class="mt-6 flex items-start gap-2.5 rounded-xl bg-gray-100/80 px-3.5 py-3 text-xs leading-5 text-gray-500 dark:bg-gray-800/60 dark:text-gray-400 md:mt-8 md:max-w-xl md:text-sm">
      <ShieldCheck class="mt-0.5 h-4 w-4 shrink-0 text-primary-500" />
      <p>清理工具会先展示待处理照片，确认后才会执行操作。</p>
    </div>

    <section class="mt-10 hidden md:block" aria-labelledby="activity-heading">
      <div class="mb-4 flex items-center gap-2">
        <Clock3 class="h-5 w-5 text-primary-500" />
        <h2 id="activity-heading" class="text-lg font-bold text-gray-950 dark:text-white">最近活动</h2>
      </div>
      <div class="flex min-h-32 items-center justify-center rounded-2xl border border-dashed border-gray-300 bg-gray-50/70 text-sm text-gray-400 dark:border-gray-700 dark:bg-gray-800/40 dark:text-gray-500">
        暂无最近活动
      </div>
    </section>
  </AppPage>
</template>

<script setup lang="ts">
import {
  ArrowUpRight,
  ChevronRight,
  Clock3,
  Copy,
  FolderOpen,
  Images,
  ShieldCheck,
  Tag,
  Trash2,
  Wrench,
} from 'lucide-vue-next'
import AppPage from '@/components/ui/AppPage.vue'

const cleanupTools = [
  { path: '/toolbox/cleanup', title: '低分清理', desc: '清理模糊、低质量照片', icon: Trash2 },
  { path: '/toolbox/similar', title: '相似照片清理', desc: '聚类相似照片，保留最佳', icon: Images },
  { path: '/toolbox/duplicate', title: '清理重复', desc: '查找完全重复的照片', icon: Copy },
]

const managementTools = [
  { path: '/toolbox/organize', title: '图片整理', desc: '按时间、分类与人物自动归档', icon: FolderOpen },
  { path: '/toolbox/rename', title: '批量重命名', desc: '按时间规则统一重命名图片', icon: Tag },
  { path: '/toolbox/time-from-filename', title: '修改图片元数据', desc: '根据文件名修正照片拍摄时间', icon: Clock3 },
]
</script>
