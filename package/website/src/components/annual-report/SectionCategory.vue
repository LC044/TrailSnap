<template>
  <ReportPage>
    <div class="flex flex-col w-full">
        <!-- Title -->
        <div class="text-center mb-2">
            <h2 class="text-2xl font-bold text-light-text1 dark:text-white">你的年度生活图谱</h2>
            <p class="text-sm text-light-text3 dark:text-gray-400 mt-2">镜头里的世界，藏着你的热爱</p>
        </div>

        <!-- Chart -->
        <div ref="chartRef" class="w-full h-[250px] md:h-[350px]"></div>

        <!-- Top List -->
        <div class="flex flex-col gap-3 mt-0">
            <div
                v-for="(cat, index) in topCategories"
                :key="cat.name"
                class="relative overflow-hidden flex items-center justify-between bg-white/50 dark:bg-white/5 p-3 rounded-xl backdrop-blur-sm"
            >
                <!-- Hand-drawn style progress bar -->
                <div 
                    class="absolute top-0 left-0 h-full transition-all duration-1000 ease-out z-0"
                    :style="{ 
                        width: `calc(${cat.percent}% + 10px)`, 
                        backgroundColor: ['#F97316', '#FBBF24', '#EC4899'][index] || '#ccc',
                        opacity: 0.2,
                        borderRadius: '0 12px 12px 0',
                        transform: 'skewX(-10deg) translateX(-5px)'
                    }"
                ></div>
                
                <!-- Content -->
                <div class="relative z-10 flex items-center gap-2">
                    <div class="w-2 h-2 rounded-full" :style="{ backgroundColor: ['#F97316', '#FBBF24', '#EC4899'][index] || '#ccc' }"></div>
                    <span class="font-medium text-sm text-light-text1 dark:text-gray-200">{{ cat.name }}</span>
                    <span class="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5 ml-1">{{ cat.percent }}%</span>
                </div>
                <div class="relative z-10 flex items-center">
                    <span class="text-primary-amber font-bold text-sm">{{ cat.value }}</span>
                </div>
            </div>
        </div>
    </div>
  </ReportPage>
</template>


<script setup lang="ts">
import ReportPage from './ReportPage.vue';
import type { MemoryMetrics } from '@/types/annualReport';
import { onMounted, ref, computed } from 'vue';
import { echarts } from '@/utils/echarts';

const props = defineProps<{
  data: MemoryMetrics;
}>();

const chartRef = ref<HTMLElement | null>(null);
let chartInstance: echarts.ECharts | null = null;

const initChart = () => {
  if (!chartRef.value) return;
  chartInstance = echarts.init(chartRef.value);
  const isMobile = window.innerWidth < 768;
  const option = {
    series: [
      {
        type: 'pie',
        radius: ['50%', '70%'],
        center: ['50%', '40%'],
        data: props.data.categoryDistribution,
        color: ['#F97316', '#FBBF24', '#EC4899', '#8B5CF6', '#10B981'],
        label: { show: !isMobile },
        emphasis: {
            itemStyle: {
                scale: true,
                scaleSize: 10,
                shadowBlur: 10,
                shadowOffsetX: 0,
                shadowColor: 'rgba(0, 0, 0, 0.5)'
            } 
        }
      }
    ],
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} ({d}%)'
    }
  };
  chartInstance.setOption(option);
};

onMounted(() => {
    // Delay init to ensure transition is done or use IntersectionObserver
    setTimeout(initChart, 500);
    window.addEventListener('resize', () => chartInstance?.resize());
});

// Top 3 Categories
const topCategories = computed(() => {
    const total = props.data.categoryDistribution.reduce((acc, cur) => acc + cur.value, 0);
    return [...props.data.categoryDistribution]
        .sort((a, b) => b.value - a.value)
        .slice(0, 3)
        .map(cat => ({
            ...cat,
            percent: total ? ((cat.value / total) * 100).toFixed(1) : '0'
        }));
});
</script>