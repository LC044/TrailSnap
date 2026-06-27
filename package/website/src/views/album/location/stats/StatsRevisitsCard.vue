<template>
  <div class="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
    <h2 class="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-4">重访清单</h2>
    <div v-if="loading" class="space-y-3">
      <el-skeleton v-for="i in 3" :key="i" animated>
        <template #template><el-skeleton-item variant="text" style="width: 100%" /></template>
      </el-skeleton>
    </div>
    <div v-else-if="error" class="flex flex-col items-center gap-2 py-8 text-gray-400 dark:text-gray-500">
      <span class="text-sm">统计加载失败</span>
      <button @click="$emit('retry')" class="text-sm text-primary-500 hover:text-primary-600 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none rounded">重试</button>
    </div>
    <div v-else-if="!revisits.length" class="py-8 text-center text-gray-400 dark:text-gray-500 text-sm">还没有重游记录，多出去走走吧</div>
    <ul v-else class="space-y-2">
      <li
        v-for="r in revisits" :key="r.name"
        :class="['flex items-center gap-3 rounded-lg px-3 py-2.5 transition-colors', r.visit_count >= 3 ? 'bg-amber-50 dark:bg-amber-900/20 border-l-4 border-amber-400' : 'bg-gray-50 dark:bg-gray-700/30']"
      >
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">{{ r.name }}</span>
            <span :class="['text-xs px-1.5 py-0.5 rounded-full font-medium', r.visit_count >= 3 ? 'bg-amber-200 text-amber-800 dark:bg-amber-400/30 dark:text-amber-200' : 'bg-gray-200 text-gray-600 dark:bg-gray-600 dark:text-gray-200']">
              {{ r.visit_count }} 次
            </span>
          </div>
          <div class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{{ r.first_date || '?' }} ~ {{ r.last_date || '?' }} · 间隔 {{ gapDays(r) }} 天</div>
        </div>
        <div class="flex items-center gap-1.5 flex-shrink-0">
          <div
            v-for="(d, i) in r.visit_dates.slice(0, 5)" :key="i"
            class="w-2 h-2 rounded-full bg-primary-500 cursor-help"
            :title="d"
          ></div>
          <span v-if="r.visit_dates.length > 5" class="text-xs text-gray-400">+{{ r.visit_dates.length - 5 }}</span>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import type { PlaceStats } from '@/api/location';

defineProps<{ revisits: PlaceStats[]; loading: boolean; error: boolean }>();
defineEmits<{ (e: 'retry'): void }>();

function gapDays(r: PlaceStats): number {
  if (!r.first_date || !r.last_date) return 0;
  const a = new Date(r.first_date).getTime();
  const b = new Date(r.last_date).getTime();
  return Math.round(Math.abs(b - a) / 86400000);
}
</script>
