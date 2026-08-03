<template>
  <div class="w-full h-full flex flex-col justify-between">
    <!-- Header -->
    <div class="flex justify-between items-center mb-4">
      <h3 class="text-base font-bold text-gray-800 dark:text-gray-100">拍摄时光</h3>
      <span class="text-xs text-gray-500">{{ latestYear }}年占{{ latestYearData?.percentage }}%</span>
    </div>

    <div class="flex items-center flex-1">
      <!-- Chart -->
      <div ref="chartRef" class="w-[100px] h-[100px]"></div>
      
      <!-- Legend -->
      <div class="ml-4 flex flex-col justify-center space-y-2">
        <div 
          v-for="item in data.chart_data.slice(0, 3)" 
          :key="item.year"
          class="flex items-center space-x-2 text-xs text-gray-600 dark:text-gray-300 cursor-pointer"
          @click="$router.push(`/photos?year=${item.year}`)"
        >
          <span class="w-2 h-2 rounded-full" :style="{ backgroundColor: item.color }"></span>
          <span>{{ item.year }}</span>
          <span class="text-gray-400">{{ item.percentage }}%</span>
        </div>
      </div>
    </div>

    <!-- Monthly Peak Alert -->
    <div 
      class="mt-4 bg-[#E8F4F8] dark:bg-blue-900/20 rounded-md p-2 text-xs text-gray-800 dark:text-gray-200 cursor-pointer"
      @click="$router.push('/photos')" 
    >
      {{ data.monthly_peak }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, PropType, nextTick, computed } from 'vue';
import { echarts } from '@/utils/echarts';
import { DashboardTime } from '@/api/dashboard';

const props = defineProps({
  data: {
    type: Object as PropType<DashboardTime>,
    required: true
  }
});

const chartRef = ref<HTMLElement | null>(null);
let chartInstance: echarts.ECharts | null = null;
const latestYear = computed(() => props.data.chart_data?.[0]?.year || 0);
const latestYearData = computed(() => props.data.chart_data.find(item => item.year === latestYear.value));

const initChart = () => {
  if (!chartRef.value) return;
  
  chartInstance = echarts.init(chartRef.value);
  const option = {
    series: [
      {
        type: 'pie',
        radius: ['60%', '90%'],
        avoidLabelOverlap: false,
        label: { show: false },
        labelLine: { show: false },
        data: props.data.chart_data.map(item => ({
          value: item.count,
          name: item.year.toString(),
          itemStyle: { color: item.color }
        }))
      }
    ]
  };
  chartInstance.setOption(option);
  
  // Handle click
  chartInstance.on('click', (params) => {
    // console.log(params.name); 
    // Navigation logic could go here
  });
};

onMounted(() => {
    nextTick(() => {
        initChart();
    });
});

watch(() => props.data, () => {
  if (chartInstance) {
    chartInstance.setOption({
      series: [{
        data: props.data.chart_data.map(item => ({
          value: item.count,
          name: item.year.toString(),
          itemStyle: { color: item.color }
        }))
      }]
    });
  } else {
      initChart();
  }
}, { deep: true });

// Resize handling could be added
</script>
