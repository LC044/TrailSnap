<template>
  <ReportPage>
    <div class="flex flex-col items-center justify-center h-full text-center px-4 py-8">
      <!-- Header -->
      <div class="mb-6">
        <h2 class="text-2xl font-bold text-primary-amber">综合统计</h2>
        <p class="text-xs text-light-text3 dark:text-gray-400 mt-2">年度出行里程与成本</p>
      </div>

      <!-- Key Metrics -->
      <div class="grid grid-cols-2 gap-4 w-full max-w-2xl mx-auto mb-8">
        <div class="bg-white/50 dark:bg-black/20 rounded-xl p-4 backdrop-blur-sm">
          <p class="text-sm text-light-text3 dark:text-gray-400 mb-1">年度总出行里程</p>
          <p class="text-2xl font-bold text-primary-amber">{{ data.totalMileage.toLocaleString() }} km</p>
        </div>
        <div class="bg-white/50 dark:bg-black/20 rounded-xl p-4 backdrop-blur-sm">
          <p class="text-sm text-light-text3 dark:text-gray-400 mb-1">平均出行成本</p>
          <p class="text-2xl font-bold text-primary-amber">¥ {{ data.costPerKm.toFixed(2) }}/km</p>
        </div>
      </div>

      <!-- Chart -->
      <div ref="costChartRef" class="w-full max-w-2xl h-[280px] bg-white/50 dark:bg-black/20 rounded-xl p-2"></div>
    </div>
  </ReportPage>
</template>

<script setup lang="ts">
import ReportPage from './ReportPage.vue';
import type { ComprehensiveMetrics } from '@/types/annualReport';
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue';
import { echarts } from '@/utils/echarts';

const props = defineProps<{
  data: ComprehensiveMetrics;
}>();

const costChartRef = ref<HTMLElement | null>(null);
let costChart: echarts.ECharts | null = null;

const initChart = () => {
  if (!costChartRef.value) return;
  costChart = echarts.init(costChartRef.value);
  // Simple visual comparing total mileage and normalized cost
  costChart.setOption({
    title: { text: '里程与成本概览', left: 'center', textStyle: { fontSize: 14, color: '#888' } },
    tooltip: { trigger: 'axis' },
    grid: { left: '3%', right: '4%', bottom: '10%', containLabel: true },
    xAxis: { type: 'category', data: ['总里程', '单位里程成本'], axisLabel: { color: '#888' }, axisLine: { lineStyle: { color: '#ccc' } } },
    yAxis: { type: 'value', axisLabel: { color: '#888' }, splitLine: { lineStyle: { type: 'dashed', color: '#eee' } } },
    series: [
      {
        type: 'bar',
        data: [props.data.totalMileage, Number((props.data.costPerKm * 100).toFixed(2))],
        itemStyle: {
          color: new (echarts as any).graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#F97316' },
            { offset: 1, color: '#EA580C' }
          ]),
          borderRadius: [4, 4, 0, 0]
        },
        showBackground: true,
        backgroundStyle: { color: 'rgba(180, 180, 180, 0.1)' }
      }
    ]
  });
};

onMounted(() => {
  nextTick(() => initChart());
  window.addEventListener('resize', handleResize);
});

onUnmounted(() => {
  window.removeEventListener('resize', handleResize);
  costChart?.dispose();
});

const handleResize = () => {
  costChart?.resize();
};

watch(() => props.data, () => {
  nextTick(() => {
    costChart?.dispose();
    initChart();
  });
}, { deep: true });
</script>

