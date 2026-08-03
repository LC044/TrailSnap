<template>
  <ReportPage>
    <div class="flex flex-col items-center justify-center h-full text-center px-4 py-8 overflow-y-auto">
      <!-- Header -->
      <div class="mb-6">
        <h2 class="text-2xl font-bold text-primary-amber">出行行为分析</h2>
        <p class="text-xs text-light-text3 dark:text-gray-400 mt-2">来自你的车票记录</p>
      </div>

      <!-- Charts -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6 w-full max-w-4xl mx-auto">
        <!-- Monthly Frequency -->
        <div ref="freqChartRef" class="w-full h-[280px] bg-white/50 dark:bg-black/20 rounded-xl p-2"></div>
        <!-- Trip Type Distribution -->
        <div ref="typeChartRef" class="w-full h-[280px] bg-white/50 dark:bg-black/20 rounded-xl p-2"></div>
      </div>

      <!-- Lists -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6 w-full max-w-4xl mx-auto mt-6">
        <div class="bg-white/50 dark:bg-black/20 rounded-xl p-4 text-left">
          <h3 class="text-sm font-bold text-light-text2 dark:text-gray-200 mb-3">常用路线 TOP5</h3>
          <div class="flex flex-col gap-2">
            <div v-for="(r, idx) in data.topRoutes" :key="idx" class="flex items-center justify-between">
              <span class="text-sm text-light-text1 dark:text-gray-200">{{ r.route }}</span>
              <span class="text-xs text-primary-amber font-bold">{{ r.count }} 次</span>
            </div>
            <div v-if="!data.topRoutes || data.topRoutes.length === 0" class="text-xs text-gray-500">暂无数据</div>
          </div>
        </div>
        <div class="bg-white/50 dark:bg-black/20 rounded-xl p-4 text-left">
          <h3 class="text-sm font-bold text-light-text2 dark:text-gray-200 mb-3">热门目的地 TOP5</h3>
          <div class="flex flex-col gap-2">
            <div v-for="(d, idx) in data.topDestinations" :key="idx" class="flex items-center justify-between">
              <span class="text-sm text-light-text1 dark:text-gray-200">{{ d.city }}</span>
              <span class="text-xs text-primary-amber font-bold">{{ d.count }} 次</span>
            </div>
            <div v-if="!data.topDestinations || data.topDestinations.length === 0" class="text-xs text-gray-500">暂无数据</div>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <p class="text-xs text-light-text3 dark:text-gray-500 mt-4">统计口径：自然年</p>
    </div>
  </ReportPage>
</template>

<script setup lang="ts">
import ReportPage from './ReportPage.vue';
import type { TravelBehaviorMetrics } from '@/types/annualReport';
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue';
import { echarts } from '@/utils/echarts';

const props = defineProps<{
  data: TravelBehaviorMetrics;
}>();

const freqChartRef = ref<HTMLElement | null>(null);
const typeChartRef = ref<HTMLElement | null>(null);
let freqChart: echarts.ECharts | null = null;
let typeChart: echarts.ECharts | null = null;

const initCharts = () => {
  if (freqChartRef.value && props.data.monthlyFrequency) {
    freqChart = echarts.init(freqChartRef.value);
    const months = props.data.monthlyFrequency.map(m => `${parseInt(m.month.split('-')[1])}月`);
    const counts = props.data.monthlyFrequency.map(m => m.count);
    freqChart.setOption({
      title: { text: '月度出行频次', left: 'center', textStyle: { fontSize: 14, color: '#888' } },
      tooltip: { trigger: 'axis' },
      grid: { left: '3%', right: '4%', bottom: '10%', containLabel: true },
      xAxis: { type: 'category', data: months, axisLabel: { color: '#888' }, axisLine: { lineStyle: { color: '#ccc' } } },
      yAxis: { type: 'value', axisLabel: { color: '#888' }, splitLine: { lineStyle: { type: 'dashed', color: '#eee' } } },
      series: [
        {
          name: '次数',
          type: 'line',
          smooth: true,
          symbol: 'circle',
          symbolSize: 6,
          itemStyle: { color: '#F97316' },
          lineStyle: { width: 3 },
          areaStyle: {
            color: new (echarts as any).graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: '#F97316' },
              { offset: 1, color: 'rgba(249, 115, 22, 0.1)' }
            ])
          },
          data: counts
        }
      ]
    });
  }

  if (typeChartRef.value && props.data.tripTypeDistribution) {
    typeChart = echarts.init(typeChartRef.value);
    const dist = props.data.tripTypeDistribution;
    const pieData = [
      { name: '工作日', value: dist.workday },
      { name: '周末', value: dist.weekend },
      { name: '节假日', value: dist.holiday }
    ];
    typeChart.setOption({
      title: { text: '出行时间分布', left: 'center', textStyle: { fontSize: 14, color: '#888' } },
      tooltip: { trigger: 'item', formatter: '{b}: {c} 次 ({d}%)' },
      series: [
        {
          type: 'pie',
          radius: ['40%', '70%'],
          itemStyle: { borderRadius: 10, borderColor: '#fff', borderWidth: 2 },
          label: { show: false },
          emphasis: { label: { show: true, fontSize: 16, fontWeight: 'bold', formatter: '{b}\n{d}%' } },
          labelLine: { show: false },
          data: pieData
        }
      ]
    });
  }
};

onMounted(() => {
  nextTick(() => initCharts());
  window.addEventListener('resize', handleResize);
});

onUnmounted(() => {
  window.removeEventListener('resize', handleResize);
  freqChart?.dispose();
  typeChart?.dispose();
});

const handleResize = () => {
  freqChart?.resize();
  typeChart?.resize();
};

watch(() => props.data, () => {
  nextTick(() => {
    freqChart?.dispose();
    typeChart?.dispose();
    initCharts();
  });
}, { deep: true });
</script>

