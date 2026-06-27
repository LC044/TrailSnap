<template>
  <div class="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
    <h2 class="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-4">足迹概览</h2>
    <div v-if="loading" class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <el-skeleton v-for="i in 4" :key="i" animated>
        <template #template>
          <el-skeleton-item variant="h1" style="width: 60%" />
          <el-skeleton-item variant="text" style="width: 80%; margin-top: 8px" />
        </template>
      </el-skeleton>
    </div>
    <div v-else-if="!overview" class="text-gray-400 dark:text-gray-500 text-sm">暂无数据</div>
    <div v-else class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <div class="flex flex-col">
        <span class="text-4xl md:text-5xl font-bold text-primary-600 dark:text-primary-500 leading-tight">
          {{ overview.has_location ? overview.total_distance_km.toLocaleString() : '—' }}
        </span>
        <span class="text-xs text-gray-500 dark:text-gray-400 mt-1">公里 / 含跨城移动</span>
      </div>
      <div class="flex flex-col">
        <span class="text-4xl md:text-5xl font-bold text-primary-600 dark:text-primary-500 leading-tight">
          {{ overview.province_count }}<span class="text-2xl text-gray-400 dark:text-gray-500"> 省</span>
          {{ overview.city_count }}<span class="text-2xl text-gray-400 dark:text-gray-500"> 市</span>
        </span>
        <span class="text-xs text-gray-500 dark:text-gray-400 mt-1">省 + 城市 / 去重后</span>
      </div>
      <div class="flex flex-col">
        <span class="text-4xl md:text-5xl font-bold text-primary-600 dark:text-primary-500 leading-tight">
          {{ overview.travel_days }}
        </span>
        <span class="text-xs text-gray-500 dark:text-gray-400 mt-1">天 / 至少 1 张照片</span>
      </div>
      <div class="flex flex-col">
        <span class="text-4xl md:text-5xl font-bold text-primary-600 dark:text-primary-500 leading-tight">
          {{ overview.has_location ? Math.round(overview.farthest_distance_km).toLocaleString() : '—' }}
        </span>
        <span class="text-xs text-gray-500 dark:text-gray-400 mt-1 truncate" :title="overview.farthest_place ? `最远：${overview.farthest_place}` : '公里 / 最远点距中心'">
          {{ overview.farthest_place ? `公里 / ${overview.farthest_place}` : '公里 / 最远点距中心' }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { OverviewStats } from '@/api/location';

defineProps<{
  overview: OverviewStats | null;
  loading: boolean;
}>();
</script>
