<template>
  <div class="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
    <h2 class="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-4">月度出行雷达</h2>
    <div v-if="loading" class="h-64 md:h-72 flex items-center justify-center">
      <el-skeleton-item variant="rect" style="width: 100%; height: 100%" animated />
    </div>
    <div v-else-if="error" class="h-64 md:h-72 flex flex-col items-center justify-center gap-2 text-gray-400 dark:text-gray-500">
      <span class="text-sm">统计加载失败</span>
      <button @click="$emit('retry')" class="text-sm text-primary-500 hover:text-primary-600 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none rounded">重试</button>
    </div>
    <div v-else-if="!data.length || maxScore === 0" class="h-64 md:h-72 flex items-center justify-center text-gray-400 dark:text-gray-500 text-sm">暂无数据</div>
    <template v-else>
      <div ref="chartEl" class="h-64 md:h-72 w-full"></div>
      <div class="mt-3 grid grid-cols-6 md:grid-cols-12 gap-1.5">
        <button
          v-for="m in data"
          :key="m.month"
          @click="clickMonth(m.month)"
          class="px-1 py-1 rounded text-xs text-gray-600 dark:text-gray-300 hover:bg-primary-50 dark:hover:bg-primary-500/10 hover:text-primary-600 dark:hover:text-primary-400 transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          :title="`查看 ${m.month} 月照片`"
        >
          {{ m.month }}月
        </button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount, nextTick } from 'vue';
import * as echarts from 'echarts';
import { useIntersectionObserver } from '@vueuse/core';
import { injectTheme } from '@/composables/useTheme';
import type { MonthlyRadarItem } from '@/api/location';

const props = defineProps<{ data: MonthlyRadarItem[]; mostRecentYear: number | null; loading: boolean; error: boolean }>();
const emit = defineEmits<{ (e: 'narrow-range', start: string, end: string): void; (e: 'retry'): void }>();

const { isDarkMode, currentTheme } = injectTheme();
const chartEl = ref<HTMLElement | null>(null);
let chart: echarts.ECharts | null = null;

const maxScore = computed(() => Math.max(...props.data.map(d => d.activity_score), 0));

function buildOption() {
  const primary = currentTheme.value.primary;
  const isDark = isDarkMode.value;
  const textColor = isDark ? '#cbd5e1' : '#475569';
  const splitColor = isDark ? '#334155' : '#e2e8f0';
  const avg = Math.round(props.data.reduce((s, d) => s + d.activity_score, 0) / 12);
  return {
    tooltip: { trigger: 'item' },
    legend: { data: ['我的活跃度', '全年平均'], bottom: 0, textStyle: { color: textColor } },
    radar: {
      indicator: props.data.map(d => ({ name: `${d.month}月`, max: 100 })),
      axisName: { color: textColor, fontSize: 11 },
      splitLine: { lineStyle: { color: splitColor } },
      splitArea: { areaStyle: { color: isDark ? ['rgba(255,255,255,0.02)', 'rgba(255,255,255,0.04)'] : ['rgba(0,0,0,0.02)', 'rgba(0,0,0,0.04)'] } },
      axisLine: { lineStyle: { color: splitColor } },
    },
    series: [{
      type: 'radar',
      data: [
        { value: props.data.map(d => d.activity_score), name: '我的活跃度', areaStyle: { color: primary, opacity: 0.3 }, lineStyle: { color: primary, width: 2 }, itemStyle: { color: primary } },
        { value: props.data.map(() => avg), name: '全年平均', areaStyle: { opacity: 0 }, lineStyle: { color: '#94a3b8', type: 'dashed', width: 1.5 }, itemStyle: { color: '#94a3b8' } },
      ],
    }],
  };
}

function render() {
  if (!chartEl.value || !props.data.length || maxScore.value === 0) return;
  if (!chart) chart = echarts.init(chartEl.value);
  chart.setOption(buildOption(), true);
}

function onResize() { chart?.resize(); }
const { stop } = useIntersectionObserver(chartEl, ([entry]) => {
  if (entry.isIntersecting && props.data.length && !chart) nextTick(render);
});
watch(() => [props.data, isDarkMode.value, currentTheme.value], () => { if (props.data.length) nextTick(render); }, { deep: true });
window.addEventListener('resize', onResize);

function clickMonth(month: number) {
  const year = props.mostRecentYear || new Date().getFullYear();
  const start = `${year}-${String(month).padStart(2, '0')}-01`;
  const end = `${year}-${String(month).padStart(2, '0')}-28`;
  emit('narrow-range', start, end);
}

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize);
  stop();
  chart?.dispose();
  chart = null;
});
</script>
