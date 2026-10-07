<template>
  <section class="ts-surface p-5 sm:p-6" aria-labelledby="home-footprint-title">
    <div class="mb-5 flex items-center justify-between gap-3">
      <div class="flex min-w-0 items-center gap-3">
        <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-50 text-primary-500 dark:bg-primary-900/30"><MapPin class="h-5 w-5" aria-hidden="true" /></span>
        <div class="min-w-0">
          <h2 id="home-footprint-title" class="ts-section-title text-base font-bold text-gray-900 dark:text-gray-100">我的足迹</h2>
          <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">照片记录下的地点与时光</p>
        </div>
      </div>
      <button type="button" class="ts-button ts-button-ghost shrink-0 gap-1 px-2 text-xs text-primary-600 dark:text-primary-400" @click="openStatistics">查看足迹<ChevronRight class="h-3.5 w-3.5" aria-hidden="true" /></button>
    </div>
    <div v-if="loading && !data" class="grid grid-cols-3 gap-3 animate-pulse" aria-label="正在加载足迹统计">
      <div v-for="item in 3" :key="item" class="h-16 rounded-xl bg-gray-100 dark:bg-gray-800" />
    </div>
    <div v-else-if="data" class="grid grid-cols-3 divide-x divide-gray-100 dark:divide-gray-800">
      <button v-for="metric in metrics" :key="metric.label" type="button" class="flex min-w-0 flex-col items-center gap-2 rounded-xl px-1 py-2 transition-colors hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:hover:bg-gray-800/70" :aria-label="`${metric.label} ${metric.value} ${metric.unit}，查看足迹统计`" @click="openStatistics">
        <span class="text-2xl font-bold tracking-tight text-gray-900 dark:text-white sm:text-3xl">{{ metric.value.toLocaleString('zh-CN') }}<span class="ml-1 text-xs font-normal text-gray-400 dark:text-gray-500">{{ metric.unit }}</span></span>
        <span class="text-xs text-gray-500 dark:text-gray-400">{{ metric.label }}</span>
      </button>
    </div>
    <div v-else class="flex items-center justify-between gap-3 py-3">
      <p class="text-sm text-gray-500 dark:text-gray-400">足迹统计暂时无法加载</p>
      <button type="button" class="ts-button ts-button-ghost text-primary-600 dark:text-primary-400" @click="emit('retry')">重试</button>
    </div>
    <p v-if="data" class="mt-4 border-t border-gray-100 pt-3 text-xs leading-relaxed text-gray-400 dark:border-gray-800 dark:text-gray-500">{{ data.city_count || data.province_count ? '地点来自照片位置信息，记录天数按拍摄日期去重' : '照片还没有城市信息，可在地图中补充位置；记录天数按拍摄日期去重' }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import { ChevronRight, MapPin } from 'lucide-vue-next';
import type { OverviewStats } from '@/api/location';
import { useLocationStore } from '@/stores/locationStore';

const props = defineProps<{ data: OverviewStats | null; loading: boolean }>();
const emit = defineEmits<{ retry: [] }>();
const router = useRouter();
const locationStore = useLocationStore();
const metrics = computed(() => [
  { label: '记录城市', value: props.data?.city_count ?? 0, unit: '座' },
  { label: '记录省份', value: props.data?.province_count ?? 0, unit: '个' },
  { label: '记录天数', value: props.data?.travel_days ?? 0, unit: '天' },
]);
const openStatistics = () => {
  locationStore.viewMode = 'statistics';
  router.push('/album/location');
};
</script>
