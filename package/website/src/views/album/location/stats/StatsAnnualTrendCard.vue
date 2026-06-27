<template>
  <div class="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-semibold text-gray-800 dark:text-gray-100">年度旅行趋势</h2>
      <button
        v-if="data.length"
        @click="downloadPng"
        class="p-1.5 rounded-md text-gray-400 dark:text-gray-400 hover:text-primary-500 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
        title="下载为图片"
      >
        <Download class="w-4 h-4" />
      </button>
    </div>
    <div v-if="loading" class="h-72 flex items-center justify-center">
      <el-skeleton-item variant="rect" style="width: 100%; height: 100%" animated />
    </div>
    <div v-else-if="error" class="h-72 flex flex-col items-center justify-center gap-2 text-gray-400 dark:text-gray-500">
      <span class="text-sm">统计加载失败</span>
      <button @click="$emit('retry')" class="text-sm text-primary-500 hover:text-primary-600 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none rounded">重试</button>
    </div>
    <div v-else-if="!data.length" class="h-72 flex items-center justify-center text-gray-400 dark:text-gray-500 text-sm">暂无数据</div>
    <div v-else ref="chartEl" class="h-72 w-full"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onBeforeUnmount, nextTick } from 'vue';
import * as echarts from 'echarts';
import { Download } from 'lucide-vue-next';
import { useIntersectionObserver } from '@vueuse/core';
import { injectTheme } from '@/composables/useTheme';
import type { AnnualTrendItem } from '@/api/location';

const props = defineProps<{ data: AnnualTrendItem[]; loading: boolean; error: boolean }>();
const emit = defineEmits<{ (e: 'narrow-range', start: string, end: string, year: number): void; (e: 'retry'): void }>();

const { isDarkMode, currentTheme } = injectTheme();
const chartEl = ref<HTMLElement | null>(null);
let chart: echarts.ECharts | null = null;

function buildOption() {
  const primary = currentTheme.value.primary;
  const secondary = currentTheme.value.secondary;
  const isDark = isDarkMode.value;
  const textColor = isDark ? '#cbd5e1' : '#475569';
  const splitColor = isDark ? '#334155' : '#e2e8f0';
  const years = props.data.map(d => String(d.year));
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['照片数', '距离(km)'], textStyle: { color: textColor } },
    grid: { left: 48, right: 56, top: 40, bottom: 32 },
    xAxis: { type: 'category', data: years, axisLine: { lineStyle: { color: splitColor } }, axisLabel: { color: textColor } },
    yAxis: [
      { type: 'value', name: '照片数', nameTextStyle: { color: textColor }, axisLabel: { color: textColor }, splitLine: { lineStyle: { type: 'dashed', color: splitColor } } },
      { type: 'value', name: '距离(km)', nameTextStyle: { color: textColor }, axisLabel: { color: textColor }, splitLine: { show: false } },
    ],
    series: [
      { name: '照片数', type: 'bar', data: props.data.map(d => d.photo_count), itemStyle: { color: primary, borderRadius: [4, 4, 0, 0] }, emphasis: { itemStyle: { color: secondary } } },
      { name: '距离(km)', type: 'line', yAxisIndex: 1, data: props.data.map(d => d.distance_km), smooth: true, symbol: 'circle', symbolSize: 8, lineStyle: { color: secondary, width: 2 }, itemStyle: { color: secondary } },
    ],
  };
}

function render() {
  if (!chartEl.value || !props.data.length) return;
  if (!chart) {
    chart = echarts.init(chartEl.value);
    chart.on('click', handleClick);
  }
  chart.setOption(buildOption(), true);
}

function onResize() { chart?.resize(); }

const { stop } = useIntersectionObserver(chartEl, ([entry]) => {
  if (entry.isIntersecting && props.data.length && !chart) {
    nextTick(render);
  }
});

watch(() => [props.data, isDarkMode.value, currentTheme.value], () => {
  if (props.data.length) nextTick(render);
}, { deep: true });

window.addEventListener('resize', onResize);

function handleClick(params: any) {
  if (params.componentType === 'series' && params.seriesType === 'bar') {
    const year = props.data[params.dataIndex]?.year;
    if (year) emit('narrow-range', `${year}-01-01`, `${year}-12-31`, year);
  }
}

function downloadPng() {
  if (!chart) return;
  const url = chart.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: isDarkMode.value ? '#1f2937' : '#fff' });
  const a = document.createElement('a');
  a.href = url; a.download = '年度旅行趋势.png'; a.click();
}

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize);
  stop();
  chart?.off('click', handleClick);
  chart?.dispose();
  chart = null;
});
</script>
