<template>
  <div class="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-semibold text-gray-800 dark:text-gray-100">最常去的 {{ places.length }} 个地方</h2>
      <div v-if="places.length" class="flex bg-gray-100 dark:bg-gray-700 rounded-lg p-0.5">
        <button
          v-for="opt in viewOpts" :key="opt.value"
          @click="mode = opt.value"
          :class="['px-3 py-1 rounded-md text-xs font-medium transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none', mode === opt.value ? 'bg-white dark:bg-gray-800 text-primary-500 shadow-sm' : 'text-gray-500 dark:text-gray-400']"
        >{{ opt.label }}</button>
      </div>
    </div>
    <div v-if="loading" class="h-64 flex items-center justify-center">
      <el-skeleton-item variant="rect" style="width: 100%; height: 100%" animated />
    </div>
    <div v-else-if="error" class="h-64 flex flex-col items-center justify-center gap-2 text-gray-400 dark:text-gray-500">
      <span class="text-sm">统计加载失败</span>
      <button @click="$emit('retry')" class="text-sm text-primary-500 hover:text-primary-600 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none rounded">重试</button>
    </div>
    <div v-else-if="!places.length" class="h-64 flex items-center justify-center text-gray-400 dark:text-gray-500 text-sm">暂无数据</div>
    <div v-else-if="mode === 'chart'" ref="chartEl" class="h-64 w-full"></div>
    <ul v-else class="divide-y divide-gray-100 dark:divide-gray-700">
      <li
        v-for="(p, i) in places" :key="p.name"
        @click="$emit('go-location', p.name)"
        class="flex items-center gap-3 py-2.5 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/50 rounded-lg px-2 -mx-2 transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
        tabindex="0"
        @keydown.enter="$emit('go-location', p.name)"
      >
        <span class="w-6 text-center text-sm font-semibold" :class="i < 3 ? 'text-primary-500' : 'text-gray-400 dark:text-gray-500'">{{ i + 1 }}</span>
        <div class="flex-1 min-w-0">
          <div class="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">{{ p.name }}</div>
          <div class="text-xs text-gray-400 dark:text-gray-500">{{ p.first_date || '?' }} ~ {{ p.last_date || '?' }}</div>
        </div>
        <div class="flex items-center gap-2 flex-shrink-0">
          <div class="hidden sm:block w-20 h-1.5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
            <div class="h-full bg-primary-500 rounded-full" :style="{ width: `${(p.photo_count / maxCount) * 100}%` }"></div>
          </div>
          <span class="text-sm font-semibold text-gray-600 dark:text-gray-300">{{ p.photo_count }}</span>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount, nextTick } from 'vue';
import { echarts } from '@/utils/echarts';
import { useIntersectionObserver } from '@vueuse/core';
import { injectTheme } from '@/composables/useTheme';
import type { PlaceStats } from '@/api/location';

const props = defineProps<{ places: PlaceStats[]; loading: boolean; error: boolean }>();
defineEmits<{ (e: 'go-location', name: string): void; (e: 'retry'): void }>();

const { isDarkMode, currentTheme } = injectTheme();
const mode = ref<'list' | 'chart'>('list');
const viewOpts = [{ label: '列表', value: 'list' as const }, { label: '图表', value: 'chart' as const }];
const chartEl = ref<HTMLElement | null>(null);
let chart: echarts.ECharts | null = null;

const maxCount = computed(() => Math.max(...props.places.map(p => p.photo_count), 1));

function buildOption() {
  const primary = currentTheme.value.primary;
  const isDark = isDarkMode.value;
  const textColor = isDark ? '#cbd5e1' : '#475569';
  const splitColor = isDark ? '#334155' : '#e2e8f0';
  const sorted = [...props.places].reverse();
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 8, right: 48, top: 8, bottom: 8, containLabel: true },
    xAxis: { type: 'value', axisLabel: { color: textColor }, splitLine: { lineStyle: { color: splitColor } } },
    yAxis: { type: 'category', data: sorted.map(p => p.name), axisLine: { lineStyle: { color: splitColor } }, axisLabel: { color: textColor } },
    series: [{ type: 'bar', data: sorted.map(p => p.photo_count), itemStyle: { color: primary, borderRadius: [0, 4, 4, 0] }, barMaxWidth: 18 }],
  };
}

function render() {
  if (!chartEl.value || !props.places.length) return;
  if (!chart) chart = echarts.init(chartEl.value);
  chart.setOption(buildOption(), true);
}
function onResize() { chart?.resize(); }
const { stop } = useIntersectionObserver(chartEl, ([entry]) => {
  if (entry.isIntersecting && mode.value === 'chart' && !chart) nextTick(render);
});
watch(() => [mode.value, props.places, isDarkMode.value, currentTheme.value], () => {
  if (mode.value === 'chart' && props.places.length) nextTick(render);
  else if (mode.value !== 'chart' && chart) { chart.dispose(); chart = null; }
}, { deep: true });
window.addEventListener('resize', onResize);

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize);
  stop();
  chart?.dispose();
  chart = null;
});
</script>
