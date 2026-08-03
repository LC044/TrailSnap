
<template>
  <ReportPage :class="{ 'animate-in': isActive }" ref="sectionRef">
    <div class="flex flex-col items-center justify-center h-full text-center px-4 py-8 overflow-y-auto">
      
      <!-- Header -->
      <div class="mb-8 shrink-0">
         <h2 class="text-3xl font-bold text-primary-amber mb-2">交通费用年度分析</h2>
         <div class="h-1 w-20 bg-primary-amber/20 rounded-full mx-auto"></div>
      </div>

      <!-- Key Metrics -->
      <div class="grid grid-cols-2 gap-4 w-full max-w-2xl mx-auto mb-8 animate-fade-in-up">
        <div class="bg-white/50 dark:bg-black/20 rounded-xl p-4 backdrop-blur-sm">
           <p class="text-sm text-light-text3 dark:text-gray-400 mb-1">年度总支出</p>
           <p class="text-2xl font-bold text-primary-amber">¥ {{ data.totalAmount.toLocaleString() }}</p>
        </div>
        <div class="bg-white/50 dark:bg-black/20 rounded-xl p-4 backdrop-blur-sm">
           <p class="text-sm text-light-text3 dark:text-gray-400 mb-1">平均票价</p>
           <p class="text-2xl font-bold text-primary-amber">¥ {{ Math.round(data.averagePrice).toLocaleString() }}</p>
        </div>
      </div>

      <!-- Max Expense Info -->
      <div v-if="data.maxExpenseTicket" class="mb-8 animate-fade-in-up" style="animation-delay: 0.2s;">
        <p class="text-sm text-light-text3 dark:text-gray-400">单笔最高消费</p>
        <p class="text-lg text-primary-dark dark:text-gray-200 mt-1">
          <span class="font-bold">{{ data.maxExpenseTicket }}</span>
          <span class="ml-2 text-primary-amber font-bold">¥ {{ data.maxExpenseAmount }}</span>
        </p>
      </div>

      <!-- Charts Container -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6 w-full max-w-4xl mx-auto flex-1 min-h-[300px] animate-fade-in-up" style="animation-delay: 0.4s;">
        <!-- Monthly Trend Chart -->
        <div ref="trendChartRef" class="w-full h-[300px] bg-white/50 dark:bg-black/20 rounded-xl p-2"></div>
        
        <!-- Monthly Proportion Chart -->
        <div ref="pieChartRef" class="w-full h-[300px] bg-white/50 dark:bg-black/20 rounded-xl p-2"></div>
      </div>

      <!-- Details Button -->
      <div class="mt-6 animate-fade-in-up shrink-0" style="animation-delay: 0.5s;">
        <button @click="showDetails = true" class="px-6 py-2 bg-primary-amber/10 text-primary-amber rounded-full hover:bg-primary-amber/20 transition-colors text-sm font-medium">
          查看车票明细数据
        </button>
      </div>

      <!-- Footer Note -->
      <p class="text-xs text-light-text3 dark:text-gray-500 mt-4 animate-fade-in-up shrink-0" style="animation-delay: 0.6s;">
          数据来源：车票收藏夹 | 统计时间：{{ new Date().toLocaleDateString() }}
      </p>
      
      <!-- Details Modal -->
      <Teleport to="body">
        <div v-if="showDetails" class="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" @click.self="showDetails = false">
          <div class="bg-white dark:bg-dark-navy rounded-2xl w-full max-w-4xl max-h-[80vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            <div class="p-4 border-b border-gray-100 dark:border-gray-800 flex justify-between items-center bg-white dark:bg-dark-navy sticky top-0 z-10">
              <h3 class="text-lg font-bold text-gray-900 dark:text-white">车票明细数据</h3>
              <button @click="showDetails = false" class="text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            
            <div class="overflow-auto flex-1 p-4">
              <div v-if="loadingDetails" class="flex justify-center py-10">
                <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-amber"></div>
              </div>
              <div v-else-if="detailError" class="flex flex-col items-center justify-center py-12 text-red-500 gap-4">
                <AlertCircle class="w-10 h-10 opacity-80" />
                <div class="text-center">
                  <p class="font-medium">{{ detailError }}</p>
                  <button 
                    @click="fetchDetails" 
                    class="mt-4 px-4 py-2 bg-red-100 dark:bg-red-900/20 hover:bg-red-200 dark:hover:bg-red-900/40 text-red-600 dark:text-red-400 rounded-full text-sm transition-colors"
                  >
                    重试
                  </button>
                </div>
              </div>
              <table v-else class="w-full text-sm text-left">
                <thead class="text-xs text-gray-500 uppercase bg-gray-50 dark:bg-gray-800/50 dark:text-gray-400 sticky top-0">
                  <tr>
                    <th class="px-4 py-3">日期</th>
                    <th class="px-4 py-3">车次</th>
                    <th class="px-4 py-3">出发地</th>
                    <th class="px-4 py-3">目的地</th>
                    <th class="px-4 py-3">席别</th>
                    <th class="px-4 py-3">乘车人</th>
                    <th class="px-4 py-3 text-right">价格</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="ticket in ticketDetails" :key="ticket.id" class="border-b dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50">
                    <td class="px-4 py-3 font-medium">{{ new Date(ticket.date_time).toLocaleDateString() }} {{ new Date(ticket.date_time).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) }}</td>
                    <td class="px-4 py-3">{{ ticket.train_code }}</td>
                    <td class="px-4 py-3">{{ ticket.departure_station }}</td>
                    <td class="px-4 py-3">{{ ticket.arrival_station }}</td>
                    <td class="px-4 py-3">{{ ticket.seat_type }}</td>
                    <td class="px-4 py-3">{{ ticket.name }}</td>
                    <td class="px-4 py-3 text-right font-bold text-primary-amber">¥{{ ticket.price }}</td>
                  </tr>
                  <tr v-if="ticketDetails.length === 0">
                    <td colspan="7" class="px-4 py-8 text-center text-gray-500">暂无数据</td>
                  </tr>
                </tbody>
              </table>
            </div>
            
            <div class="p-4 border-t border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/30 text-right text-xs text-gray-500">
               共 {{ ticketDetails.length }} 条记录
            </div>
          </div>
        </div>
      </Teleport>

    </div>
  </ReportPage>
</template>

<script setup lang="ts">
import ReportPage from './ReportPage.vue';
import type { ExpenseMetrics, TicketDetail } from '@/types/annualReport';
import { getReportExpenseDetails } from '@/api/annualReport';
import { ref, onMounted, watch, nextTick, onUnmounted } from 'vue';
import { useIntersectionObserver } from '@vueuse/core';
import { echarts } from '@/utils/echarts';

const props = defineProps<{
  data: ExpenseMetrics;
  startTime: string;
  endTime: string;
}>();

const isActive = ref(false);
const showDetails = ref(false);
const ticketDetails = ref<TicketDetail[]>([]);
const loadingDetails = ref(false);
const detailError = ref<string | null>(null);
const detailsLoaded = ref(false);

const sectionRef = ref<HTMLElement | null>(null);

import { AlertCircle } from 'lucide-vue-next';

const fetchDetails = async () => {
  loadingDetails.value = true;
  detailError.value = null; // Clear previous error
  try {
    ticketDetails.value = await getReportExpenseDetails(props.startTime, props.endTime);
    detailsLoaded.value = true;
  } catch (e: any) {
    const errorCode = e?.response?.status || e?.code || 'UNKNOWN';
    detailError.value = `加载明细失败，请稍后重试（错误代码： ${errorCode} ）`;
    console.error(e);
  } finally {
    loadingDetails.value = false;
  }
};

watch(showDetails, async (val) => {
  if (val && !detailsLoaded.value) {
    fetchDetails();
  }
});

useIntersectionObserver(
  sectionRef,
  ([{ isIntersecting }]) => {
    if (isIntersecting && !isActive.value) {
      isActive.value = true;
      nextTick(() => {
        trendChart?.resize();
        pieChart?.resize();
      });
    }
  },
  { threshold: 0.3 }
);

const trendChartRef = ref<HTMLElement | null>(null);
const pieChartRef = ref<HTMLElement | null>(null);
let trendChart: echarts.ECharts | null = null;
let pieChart: echarts.ECharts | null = null;

const initCharts = () => {
  if (trendChartRef.value && props.data.monthlyTrend) {
    trendChart = echarts.init(trendChartRef.value);
    
    const monthLabels = props.data.monthlyTrend.map(m => parseInt(m.month.split('-')[1]) + '月');
    const amounts = props.data.monthlyTrend.map(m => m.amount);

    const series: any[] = [
        {
          name: '本年度',
          data: amounts,
          type: 'bar',
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: '#F97316' }, // primary-amber
              { offset: 1, color: '#EA580C' }
            ]),
            borderRadius: [4, 4, 0, 0]
          },
          showBackground: true,
          backgroundStyle: {
            color: 'rgba(180, 180, 180, 0.1)'
          }
        }
    ];

    if (props.data.monthlyTrendLastYear && props.data.monthlyTrendLastYear.length > 0) {
        const lastYearMap = new Map(props.data.monthlyTrendLastYear.map(m => [parseInt(m.month.split('-')[1]), m.amount]));
        const lastYearAmounts = props.data.monthlyTrend.map(m => {
            const monthInt = parseInt(m.month.split('-')[1]);
            return lastYearMap.get(monthInt) || 0;
        });

        series.push({
            name: '去年同期',
            data: lastYearAmounts,
            type: 'line',
            smooth: true,
            symbol: 'circle',
            symbolSize: 6,
            itemStyle: { color: '#9CA3AF' },
            lineStyle: { width: 2, type: 'dashed' }
        });
    }

    trendChart.setOption({
      title: {
        text: '月度支出趋势 (同比)',
        left: 'center',
        textStyle: { fontSize: 14, color: '#888' }
      },
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) => {
            let res = `${params[0].name}<br/>`;
            params.forEach((param: any) => {
                res += `${param.marker}${param.seriesName}: ¥${param.value}<br/>`;
            });
            return res;
        }
      },
      legend: {
          bottom: 0,
          data: ['本年度', '去年同期'],
          textStyle: { color: '#888' }
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '10%',
        containLabel: true
      },
      xAxis: {
        type: 'category',
        data: monthLabels,
        axisLine: { lineStyle: { color: '#ccc' } },
        axisLabel: { color: '#888', interval: 0 }
      },
      yAxis: {
        type: 'value',
        axisLine: { show: false },
        axisLabel: { color: '#888' },
        splitLine: { lineStyle: { type: 'dashed', color: '#eee' } }
      },
      series: series
    });
  }

  if (pieChartRef.value && props.data.monthlyTrend) {
    pieChart = echarts.init(pieChartRef.value);
    
    const pieData = props.data.monthlyTrend.map(m => ({
      name: m.month,
      value: m.amount
    }));

    pieChart.setOption({
      title: {
        text: '各月支出占比',
        left: 'center',
        textStyle: { fontSize: 14, color: '#888' }
      },
      tooltip: {
        trigger: 'item',
        formatter: '{b}: ¥{c} ({d}%)'
      },
      series: [
        {
          name: '支出占比',
          type: 'pie',
          radius: ['40%', '70%'],
          avoidLabelOverlap: false,
          itemStyle: {
            borderRadius: 10,
            borderColor: '#fff',
            borderWidth: 2
          },
          label: {
            show: false,
            position: 'center'
          },
          emphasis: {
            label: {
              show: true,
              fontSize: 16,
              fontWeight: 'bold',
              formatter: '{b}\n{d}%'
            }
          },
          labelLine: {
            show: false
          },
          data: pieData
        }
      ]
    });
  }
};

onMounted(() => {
  nextTick(() => {
    initCharts();
  });
  
  window.addEventListener('resize', handleResize);
});

onUnmounted(() => {
  window.removeEventListener('resize', handleResize);
  trendChart?.dispose();
  pieChart?.dispose();
});

const handleResize = () => {
  trendChart?.resize();
  pieChart?.resize();
};

watch(() => props.data, () => {
  nextTick(() => {
    trendChart?.dispose();
    pieChart?.dispose();
    initCharts();
  });
}, { deep: true });

</script>

<style scoped>
.animate-fade-in-up {
  opacity: 0;
  animation: fadeInUp 1s ease-out forwards;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
