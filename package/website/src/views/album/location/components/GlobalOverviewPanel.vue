<template>
  <div class="space-y-8 animate-fade-in">
    <!-- 骨架屏加载状态 -->
    <div v-if="!globalStats" class="space-y-8">
      <div>
        <div class="h-6 w-24 bg-gray-200 dark:bg-gray-700 rounded animate-pulse mb-4"></div>
        <div class="grid grid-cols-2 gap-3">
          <div class="h-20 bg-gray-200 dark:bg-gray-700 rounded-xl animate-pulse"></div>
          <div class="h-20 bg-gray-200 dark:bg-gray-700 rounded-xl animate-pulse"></div>
        </div>
      </div>
    </div>

    <div v-else class="space-y-6">
      <div>
        <h2 class="text-xl font-bold text-gray-800 dark:text-white mb-4">足迹概览</h2>
        
        <!-- 足迹里程碑 -->
        <div class="mb-4 bg-gradient-to-r from-primary-50 to-primary-100 dark:from-primary-900/20 dark:to-primary-900/10 p-4 rounded-xl border border-primary-100 dark:border-primary-800/30">
          <div class="flex justify-between items-end mb-2">
            <div>
              <div class="text-sm font-bold text-gray-800 dark:text-gray-200">全国探索进度</div>
              <div class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">已点亮 {{ globalStats.province_count }} / 34 个省级行政区</div>
            </div>
            <div class="text-lg font-black text-primary-600 dark:text-primary-400">
              {{ Math.round((globalStats.province_count / 34) * 100) }}%
            </div>
          </div>
          <div class="h-2 w-full bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden shadow-inner">
            <div class="h-full rounded-full transition-all duration-1000" :style="{ width: `${(globalStats.province_count / 34) * 100}%`, backgroundColor: currentTheme.primary }"></div>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div class="bg-primary-50 dark:bg-primary-900/20 p-3 rounded-xl border border-primary-100 dark:border-primary-800/30">
            <div class="text-xs text-primary-600 dark:text-primary-400 mb-1">点亮省份</div>
            <div class="text-2xl font-bold text-primary-700 dark:text-primary-300">
              {{ globalStats.province_count || 0 }}
            </div>
          </div>
          <div class="bg-primary-50 dark:bg-primary-900/20 p-3 rounded-xl border border-primary-100 dark:border-primary-800/30">
            <div class="text-xs text-primary-600 dark:text-primary-400 mb-1">点亮城市</div>
            <div class="text-2xl font-bold text-primary-700 dark:text-primary-300">
              {{ globalStats.city_count || 0 }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Top 5 排行榜 -->
    <div>
      <h3 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-1.5">
        <Trophy class="w-4 h-4 text-yellow-500" /> 热门打卡地
      </h3>
      <div v-if="topRegions.length > 0" class="space-y-3">
        <div v-for="(item, index) in topRegions" :key="item.name" class="flex items-center gap-3 cursor-pointer group" @click="emit('select-region', item.name, item.count)">
          <div class="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold" 
               :class="index === 0 ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-500' : 
                       index === 1 ? 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400' : 
                       index === 2 ? 'bg-orange-50 text-orange-700 dark:bg-orange-900/30 dark:text-orange-500' : 
                       'bg-gray-50 text-gray-500 dark:bg-gray-800/50 dark:text-gray-500'">
            {{ index + 1 }}
          </div>
          <div class="flex-1">
            <div class="flex justify-between text-sm mb-1">
              <span class="text-gray-700 dark:text-gray-200 group-hover:text-primary-500 transition-colors">{{ item.name }}</span>
              <span class="text-gray-500 dark:text-gray-400">{{ item.count }} 张</span>
            </div>
            <div class="h-1.5 w-full bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
              <div class="h-full rounded-full transition-all duration-1000" 
                   :style="{ 
                     width: `${(item.count / topRegions[0].count) * 100}%`,
                     backgroundColor: currentTheme.primary
                   }">
              </div>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="py-2">
        <el-empty description="这里还是一片未知领域，快去探索吧！" :image-size="60" />
      </div>
    </div>

    <!-- 时间轴趋势图 -->
    <div v-if="globalStats && (globalStats.province_count > 0 || globalStats.city_count > 0)">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-sm font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-1.5">
          <TrendingUp class="w-4 h-4 text-green-500" /> 足迹趋势
        </h3>
        <div class="flex bg-gray-100 dark:bg-gray-800 p-0.5 rounded-lg">
          <button @click="trendDimension = 'year'; renderTrendChart()" :class="trendDimension === 'year' ? 'bg-white dark:bg-gray-700 shadow-sm text-gray-800 dark:text-white' : 'text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'" class="px-2 py-1 text-xs rounded-md transition-all font-medium">年</button>
          <button @click="trendDimension = 'month'; renderTrendChart()" :class="trendDimension === 'month' ? 'bg-white dark:bg-gray-700 shadow-sm text-gray-800 dark:text-white' : 'text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'" class="px-2 py-1 text-xs rounded-md transition-all font-medium">月</button>
        </div>
      </div>
      <div class="bg-white dark:bg-gray-800/50 rounded-xl p-2 border border-gray-100 dark:border-gray-700/50 shadow-sm hover:shadow-md transition-shadow">
        <div ref="trendChartContainer" class="h-40 w-full"></div>
      </div>
    </div>

    <!-- 最近去过的地方 -->
    <div class="pt-2">
      <h3 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-1.5">
        <MapPin class="w-4 h-4 text-primary-500" /> 最近去过
      </h3>
      <div v-if="recentTrips.length > 0" class="space-y-2">
        <div v-for="(trip, index) in recentTrips" :key="index" class="flex items-center justify-between bg-white dark:bg-gray-800/50 p-3 rounded-xl border border-gray-100 dark:border-gray-700/50 hover:border-primary-200 dark:hover:border-primary-800/50 cursor-pointer transition-colors" @click="emit('click-location', trip.locationName, 'city')">
          <div class="flex flex-col">
            <span class="text-sm font-medium text-gray-800 dark:text-white">{{ trip.locationName }}</span>
            <span class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{{ trip.startDate }}</span>
          </div>
          <div class="flex items-center gap-1.5 text-xs text-primary-600 dark:text-primary-400 bg-primary-50 dark:bg-primary-900/20 px-2 py-1 rounded-md">
            <Images class="w-3 h-3" />
            {{ trip.photoCount }}
          </div>
        </div>
      </div>
      <div v-else class="py-2">
        <el-empty description="暂无最近访问记录" :image-size="60" />
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import { useTheme } from '@/composables/useTheme'
import { MapPin, Trophy, TrendingUp, Images } from 'lucide-vue-next'
import type { LocationStatistics, TimelineNode } from '@/types/location'

const props = defineProps<{
  globalStats: LocationStatistics | null
  topRegions: {name: string, count: number}[]
  recentTrips: TimelineNode[]
  rawTimelineData: any[]
}>()

const emit = defineEmits<{
  (e: 'select-region', name: string, count: number): void
  (e: 'click-location', name: string, level?: string): void
}>()

const { isDarkMode, currentTheme } = useTheme()
const isDark = isDarkMode

const trendChartContainer = ref<HTMLElement | null>(null)
let trendChart: echarts.ECharts | null = null
const trendDimension = ref<'year' | 'month'>('year')
let resizeTimer: ReturnType<typeof setTimeout> | null = null

const renderTrendChart = () => {
  if (!trendChartContainer.value || props.rawTimelineData.length === 0) return
  if (trendChart) trendChart.dispose()
  
  trendChart = echarts.init(trendChartContainer.value)
  
  const dataMap: Record<string, number> = {}
  props.rawTimelineData.forEach(item => {
    const key = trendDimension.value === 'year' 
      ? `${item.year}` 
      : `${item.year}-${String(item.month).padStart(2, '0')}`
    dataMap[key] = (dataMap[key] || 0) + item.count
  })
  
  let keys = Object.keys(dataMap).sort()
  if (trendDimension.value === 'month' && keys.length > 12) {
    keys = keys.slice(-12)
  }
  
  const counts = keys.map(k => dataMap[k])

  const option = {
    tooltip: { trigger: 'axis' },
    grid: { left: 10, right: 10, top: 10, bottom: 20, containLabel: true },
    xAxis: {
      type: 'category',
      data: keys,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: isDark.value ? '#94a3b8' : '#64748b', fontSize: 10 }
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { type: 'dashed', color: isDark.value ? '#334155' : '#e2e8f0' } },
      axisLabel: { color: isDark.value ? '#94a3b8' : '#64748b', fontSize: 10 }
    },
    series: [{
      name: '照片数量',
      data: counts,
      type: 'line',
      smooth: true,
      symbol: 'circle',
      symbolSize: 6,
      itemStyle: { color: currentTheme.value.primary },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: `rgba(${currentTheme.value.rgb}, 0.3)` },
          { offset: 1, color: `rgba(${currentTheme.value.rgb}, 0.0)` }
        ])
      }
    }]
  }
  
  trendChart.setOption(option)
}

watch(() => props.rawTimelineData, () => {
  nextTick(() => {
    renderTrendChart()
  })
}, { deep: true })

watch([isDark, currentTheme], () => {
  renderTrendChart()
}, { deep: true })

const handleResize = () => {
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = setTimeout(() => {
    trendChart?.resize()
  }, 200)
}

onMounted(() => {
  window.addEventListener('resize', handleResize)
  if (props.rawTimelineData.length > 0) {
    nextTick(() => {
      renderTrendChart()
    })
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (resizeTimer) clearTimeout(resizeTimer)
  trendChart?.dispose()
})
</script>

<style scoped>
.animate-fade-in {
  animation: fadeIn 0.3s ease-in-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(5px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
