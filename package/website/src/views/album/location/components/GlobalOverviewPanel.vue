<template>
  <div class="overview-cockpit space-y-6 animate-fade-in">
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
        <div class="mb-4 flex items-center justify-between">
          <div>
            <div class="cockpit-kicker">TRAVEL INTELLIGENCE</div>
            <h2 class="text-xl font-bold text-white">足迹概览</h2>
          </div>
          <div class="live-indicator"><span /> 数据已同步</div>
        </div>
        
        <!-- 足迹里程碑 -->
        <div class="exploration-card">
          <div class="progress-orbit" :style="{ '--progress': `${explorationPercentage * 3.6}deg` }">
            <div class="progress-orbit__inner">
              <strong>{{ explorationPercentage }}%</strong>
              <span>已探索</span>
            </div>
          </div>
          <div class="min-w-0 flex-1">
            <div class="text-base font-semibold text-white">探索中国</div>
            <div class="mt-1 text-xs text-[#7891aa]">已点亮 {{ globalStats.province_count }} / 34 个省级行政区</div>
            <div class="progress-track mt-4">
              <div :style="{ width: `${explorationPercentage}%`, backgroundColor: currentTheme.primary }" />
            </div>
          </div>
        </div>

        <div class="mt-3 grid grid-cols-3 gap-2">
          <div class="metric-card">
            <div class="metric-label">点亮省份</div>
            <div class="metric-value">
              {{ globalStats.province_count || 0 }}
            </div>
          </div>
          <div class="metric-card">
            <div class="metric-label">点亮城市</div>
            <div class="metric-value">
              {{ globalStats.city_count || 0 }}
            </div>
          </div>
          <div class="metric-card">
            <div class="metric-label">点亮区县</div>
            <div class="metric-value metric-value--small">{{ globalStats.district_count || 0 }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Top 5 排行榜 -->
    <div>
      <h3 class="section-heading">
        <Trophy class="w-4 h-4 text-yellow-500" /> 热门打卡地
      </h3>
      <div v-if="topRegions.length > 0" class="space-y-3">
        <div v-for="(item, index) in topRegions" :key="item.name" class="ranking-row flex items-center gap-3 cursor-pointer group rounded-xl p-2 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none" role="button" tabindex="0" @click="emit('select-region', item.name, item.count)" @keydown.enter="emit('select-region', item.name, item.count)">
          <div class="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold" 
               :class="index === 0 ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-500' : 
                       index === 1 ? 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400' : 
                       index === 2 ? 'bg-orange-50 text-orange-700 dark:bg-orange-900/30 dark:text-orange-500' : 
                       'bg-gray-50 text-gray-500 dark:bg-gray-800/50 dark:text-gray-500'">
            {{ index + 1 }}
          </div>
          <div class="flex-1">
            <div class="flex justify-between text-sm mb-1">
              <span class="text-[#c8d9e9] group-hover:text-primary-500 transition-colors">{{ item.name }}</span>
              <span class="text-[#7189a0]">{{ item.count }} 张</span>
            </div>
            <div class="h-1 w-full bg-[#152a40] rounded-full overflow-hidden">
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
        <h3 class="section-heading">
          <TrendingUp class="w-4 h-4 text-primary-500" /> 足迹趋势
        </h3>
        <div class="dimension-toggle">
          <button @click="trendDimension = 'year'; renderTrendChart()" :class="{ active: trendDimension === 'year' }" class="focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none">年</button>
          <button @click="trendDimension = 'month'; renderTrendChart()" :class="{ active: trendDimension === 'month' }" class="focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none">月</button>
        </div>
      </div>
      <div class="chart-card">
        <div ref="trendChartContainer" class="h-40 w-full"></div>
      </div>
    </div>

    <!-- 最近去过的地方 -->
    <div class="pt-2">
      <h3 class="section-heading mb-3">
        <MapPin class="w-4 h-4 text-primary-500" /> 最近去过
      </h3>
      <div v-if="recentTrips.length > 0" class="space-y-2">
        <div v-for="(trip, index) in recentTrips" :key="index" class="recent-trip flex items-center justify-between p-3 rounded-xl cursor-pointer focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none" role="button" tabindex="0" @click="emit('click-location', trip.locationName, trip.level)" @keydown.enter="emit('click-location', trip.locationName, trip.level)">
          <div class="flex flex-col">
            <span class="text-sm font-medium text-[#dcecff]">{{ trip.locationName }}</span>
            <span class="text-xs text-[#7189a0] mt-0.5">{{ trip.startDate }}</span>
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
import { computed, ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { echarts } from '@/utils/echarts'
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
const explorationPercentage = computed(() => Math.min(Math.round(((props.globalStats?.province_count || 0) / 34) * 100), 100))

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
      axisLabel: { color: '#7189a0', fontSize: 10 }
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { type: 'dashed', color: 'rgba(113, 137, 160, 0.18)' } },
      axisLabel: { color: '#7189a0', fontSize: 10 }
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
.overview-cockpit { color: #c8d9e9; }
.cockpit-kicker {
  margin-bottom: 3px;
  color: var(--theme-primary);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.16em;
}
.live-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #7189a0;
  font-size: 10px;
}
.live-indicator span {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: var(--theme-primary);
  box-shadow: 0 0 10px rgba(var(--theme-rgb), 0.8);
}
.exploration-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 15px;
  border: 1px solid rgba(var(--theme-rgb), 0.24);
  border-radius: 16px;
  background: linear-gradient(135deg, rgba(var(--theme-rgb), 0.11), rgba(15, 35, 57, 0.52));
  box-shadow: inset 0 1px rgba(255, 255, 255, 0.035);
}
.progress-orbit {
  display: grid;
  width: 78px;
  height: 78px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 999px;
  background: conic-gradient(var(--theme-primary) var(--progress), rgba(var(--theme-rgb), 0.12) 0);
  box-shadow: 0 0 28px rgba(var(--theme-rgb), 0.18);
}
.progress-orbit__inner {
  display: flex;
  width: 64px;
  height: 64px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(var(--theme-rgb), 0.15);
  border-radius: 999px;
  background: #0a192b;
}
.progress-orbit__inner strong { color: #fff; font-size: 20px; line-height: 1; }
.progress-orbit__inner span { margin-top: 4px; color: #7189a0; font-size: 9px; }
.progress-track { height: 4px; overflow: hidden; border-radius: 999px; background: #172c42; }
.progress-track div { height: 100%; border-radius: inherit; box-shadow: 0 0 10px rgba(var(--theme-rgb), 0.6); }
.metric-card {
  min-width: 0;
  padding: 11px;
  border: 1px solid rgba(var(--theme-rgb), 0.16);
  border-radius: 12px;
  background: rgba(15, 35, 57, 0.62);
}
.metric-label { overflow: hidden; color: #7189a0; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.metric-value { margin-top: 4px; color: #f0f8ff; font-size: 22px; font-weight: 700; }
.metric-value--small { font-size: 17px; line-height: 28px; }
.section-heading { display: flex; align-items: center; gap: 6px; color: #a9bed1; font-size: 13px; font-weight: 600; }
.ranking-row { transition: background-color 180ms ease; }
.ranking-row:hover { background: rgba(var(--theme-rgb), 0.07); }
.dimension-toggle { display: flex; padding: 2px; border: 1px solid rgba(var(--theme-rgb), 0.14); border-radius: 8px; background: #0b1a2c; }
.dimension-toggle button { padding: 3px 8px; border-radius: 6px; color: #7189a0; font-size: 10px; }
.dimension-toggle button.active { color: #e8f6ff; background: rgba(var(--theme-rgb), 0.18); }
.chart-card { padding: 8px; border: 1px solid rgba(var(--theme-rgb), 0.15); border-radius: 14px; background: rgba(13, 31, 51, 0.62); }
.recent-trip { border: 1px solid rgba(var(--theme-rgb), 0.13); background: rgba(13, 31, 51, 0.58); transition: border-color 180ms ease, background-color 180ms ease; }
.recent-trip:hover { border-color: rgba(var(--theme-rgb), 0.4); background: rgba(var(--theme-rgb), 0.08); }
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
