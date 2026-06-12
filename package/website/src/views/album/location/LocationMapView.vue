<template>
  <div class="flex flex-col md:flex-row w-full h-full">
    <!-- 左侧地图区域 -->
    <div class="flex-1 relative overflow-hidden shadow-sm h-[50vh] md:h-full">
       <div ref="mapContainer" class="w-full h-full"></div>
       
       <!-- Map Controls Overlay -->
       <div class="absolute bottom-6 right-6 flex flex-col gap-2">
          <!-- Add any custom map controls here if needed -->
       </div>
    </div>

    <!-- 右侧信息面板 -->
    <div class="w-full md:w-80 lg:w-96 flex flex-col bg-white/80 dark:bg-gray-900/80 backdrop-blur-md border-t md:border-t-0 md:border-l border-gray-200 dark:border-gray-700 h-[50vh] md:h-full z-10 transition-all duration-300">
      <el-scrollbar class="flex-1">
        <div class="p-4 md:p-6 space-y-8">
          
          <!-- 选中区域详情 -->
          <div v-if="selectedRegion" class="space-y-4 animate-fade-in">
            <div class="flex items-center justify-between">
              <h2 class="text-xl font-bold text-gray-800 dark:text-white flex items-center gap-2">
                <MapPin class="w-5 h-5 text-primary-500" />
                {{ selectedRegion }}
              </h2>
              <button @click="clearSelection" class="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors">
                <X class="w-5 h-5" />
              </button>
            </div>
            
            <div class="grid grid-cols-2 gap-3">
              <div class="bg-gray-50 dark:bg-gray-800/50 p-3 rounded-xl border border-gray-100 dark:border-gray-700/50">
                <div class="text-xs text-gray-500 dark:text-gray-400 mb-1">照片数量</div>
                <div class="text-xl font-semibold text-gray-800 dark:text-white">{{ selectedRegionCount }}</div>
              </div>
              <div v-if="regionFirstVisit" class="bg-gray-50 dark:bg-gray-800/50 p-3 rounded-xl border border-gray-100 dark:border-gray-700/50">
                <div class="text-xs text-gray-500 dark:text-gray-400 mb-1">首次点亮</div>
                <div class="text-sm font-semibold text-gray-800 dark:text-white mt-1">{{ regionFirstVisit }}</div>
              </div>
            </div>

            <!-- 时间跨度 & 标签 -->
            <div v-if="regionTimeSpan || regionTags.length > 0" class="flex flex-col gap-2 mt-2">
              <div v-if="regionTimeSpan" class="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1.5">
                <Calendar class="w-3.5 h-3.5" />
                时间跨度: {{ regionTimeSpan }}
              </div>
              <div v-if="regionTags.length > 0" class="flex flex-wrap gap-2">
                <span v-for="tag in regionTags" :key="tag.name" class="px-2.5 py-1 bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400 rounded-lg text-xs font-medium border border-primary-100 dark:border-primary-800/30">
                  #{{ tag.name }}
                </span>
              </div>
            </div>

            <!-- 区域探索进度 -->
            <div v-if="regionSubLevel && regionTotalCount > 0" class="mt-4 bg-gradient-to-r from-primary-50 to-primary-100 dark:from-primary-900/20 dark:to-primary-900/10 p-4 rounded-xl border border-primary-100 dark:border-primary-800/30">
              <div class="flex justify-between items-end mb-2">
                <div>
                  <div class="text-sm font-bold text-gray-800 dark:text-gray-200">{{ selectedRegion }}探索进度</div>
                  <div class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">已点亮 {{ regionExploredCount }} / {{ regionTotalCount }} 个{{ regionSubLevel === 'city' ? '城市' : '区县' }}</div>
                </div>
                <div class="text-lg font-black text-primary-600 dark:text-primary-400">
                  {{ regionTotalCount > 0 ? Math.round((regionExploredCount / regionTotalCount) * 100) : 0 }}%
                </div>
              </div>
              <div class="h-2 w-full bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden shadow-inner">
                <div class="h-full rounded-full transition-all duration-1000" :style="{ width: `${regionTotalCount > 0 ? (regionExploredCount / regionTotalCount) * 100 : 0}%`, backgroundColor: currentTheme.primary }"></div>
              </div>
            </div>

            <!-- 区域热门打卡地 -->
            <div v-if="regionSubLevel && regionTopSubRegions.length > 0" class="mt-4">
              <h3 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-1.5">
                <Trophy class="w-4 h-4 text-yellow-500" /> 热门打卡地
              </h3>
              <div class="space-y-3">
                <div v-for="(item, index) in regionTopSubRegions" :key="item.name" class="flex items-center gap-3 cursor-pointer group" @click="emitClickLocation(item.name, regionSubLevel)">
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
                             width: `${(item.count / regionTopSubRegions[0].count) * 100}%`,
                             backgroundColor: currentTheme.primary
                           }">
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 区域最近去过 -->
            <div v-if="regionSubLevel && regionRecentVisits.length > 0" class="mt-4">
              <h3 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-1.5">
                <MapPin class="w-4 h-4 text-primary-500" /> 最近去过
              </h3>
              <div class="space-y-2">
                <div v-for="(trip, index) in regionRecentVisits" :key="index" class="flex items-center justify-between bg-white dark:bg-gray-800/50 p-3 rounded-xl border border-gray-100 dark:border-gray-700/50 hover:border-primary-200 dark:hover:border-primary-800/50 cursor-pointer transition-colors" @click="emitClickLocation(trip.locationName, regionSubLevel)">
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
            </div>

            <!-- 下钻地图按钮 -->
            <div v-if="level === 'province' || level === 'city'" class="pt-2">
              <button @click="emit('change-level', level === 'province' ? 'city' : 'district', { zoom: 0.9, center: [], parentRegion: selectedRegion })" class="w-full py-2.5 rounded-xl bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-sm font-medium text-gray-700 dark:text-gray-200 transition-colors flex items-center justify-center gap-1.5">
                进入{{ level === 'province' ? '城市' : '区县' }}地图
                <ChevronRight class="w-4 h-4" />
              </button>
            </div>

            <!-- 照片预览墙 -->
            <div v-if="regionPhotos.length > 0" class="space-y-2">
              <div class="flex items-center justify-between">
                <span class="text-sm font-medium text-gray-700 dark:text-gray-300">精彩瞬间</span>
                <button @click="emitClickLocation(selectedRegion)" class="px-3 py-1.5 rounded-lg bg-primary-50 hover:bg-primary-100 dark:bg-primary-900/20 dark:hover:bg-primary-900/40 text-xs text-primary-600 dark:text-primary-400 transition-colors flex items-center gap-1">
                  查看全部 <ChevronRight class="w-3.5 h-3.5" />
                </button>
              </div>
              <div class="grid grid-cols-3 gap-2">
                <div 
                  v-for="(photo, index) in regionPhotos" 
                  :key="photo.id"
                  class="aspect-square rounded-lg overflow-hidden cursor-pointer group relative shadow-sm"
                  @click="emitClickLocation(selectedRegion)"
                >
                  <img :src="photo.thumbnail || photo.url" class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110" loading="lazy" />
                  <div class="absolute inset-0 bg-gradient-to-t from-black/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
                </div>
              </div>
            </div>
            <div v-else class="text-center py-6 text-gray-400 text-sm">
              暂无照片预览
            </div>
          </div>

          <!-- 全局概览 (未选中时显示) -->
          <div v-else class="space-y-8 animate-fade-in">
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
            <div v-if="topRegions.length > 0">
              <h3 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-1.5">
                <Trophy class="w-4 h-4 text-yellow-500" /> 热门打卡地
              </h3>
              <div class="space-y-3">
                <div v-for="(item, index) in topRegions" :key="item.name" class="flex items-center gap-3 cursor-pointer group" @click="selectRegion(item.name, item.count)">
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
            </div>
          </div>

          <!-- 时间轴趋势图 -->
          <div v-if="globalStats && (globalStats.province_count > 0 || globalStats.city_count > 0) && !selectedRegion">
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
          <div v-if="recentTrips.length > 0 && !selectedRegion" class="pt-2">
            <h3 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-1.5">
              <MapPin class="w-4 h-4 text-primary-500" /> 最近去过
            </h3>
            <div class="space-y-2">
              <div v-for="(trip, index) in recentTrips" :key="index" class="flex items-center justify-between bg-white dark:bg-gray-800/50 p-3 rounded-xl border border-gray-100 dark:border-gray-700/50 hover:border-primary-200 dark:hover:border-primary-800/50 cursor-pointer transition-colors" @click="emitClickLocation(trip.locationName)">
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
          </div>

        </div>
      </el-scrollbar>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import { locationService } from '@/api/location'
import { albumService } from '@/api/album'
import { useTheme } from '@/composables/useTheme'
import { MapPin, X, ChevronRight, Trophy, TrendingUp, Images, Calendar } from 'lucide-vue-next'
import type { LocationStatistics, TimelineNode } from '@/types/location'
import type { Photo, AlbumImage } from '@/types/album'
import { mapPhotoToImage } from '@/stores/photoStore'
import request from '@/utils/request'

const ADMIN_SUFFIX_REGEX = /(省|市|自治区|特别行政区|回族自治区|壮族自治区|维吾尔自治区|县|区)$/

const buildNameMap = (geoJson: any): Record<string, string> => {
  const nameMap: Record<string, string> = {}
  if (geoJson?.features) {
    geoJson.features.forEach((f: any) => {
      const fullName = f.properties.name
      if (fullName) {
        nameMap[fullName] = fullName
        const shortName = fullName.replace(ADMIN_SUFFIX_REGEX, '')
        if (shortName && shortName !== fullName) {
          nameMap[shortName] = fullName
        }
      }
    })
  }
  return nameMap
}

const props = defineProps<{
  level: string
  viewMode: string
  startDate?: string
  endDate?: string
  parentRegion?: string
}>()

const emit = defineEmits<{
  (e: 'click-location', name: string, level?: string): void
  (e: 'change-level', level: string, viewState: { zoom: number, center: number[], parentRegion?: string }): void
}>()

const mapContainer = ref<HTMLElement | null>(null)
let myMap: echarts.ECharts | null = null

// 新增右侧面板状态
const selectedRegion = ref<string | null>(null)
const selectedRegionCount = ref(0)
const regionPhotos = ref<AlbumImage[]>([])
const regionTimeSpan = ref<string>('')
const regionFirstVisit = ref<string>('')
const regionTags = ref<{name: string, count: number}[]>([])
const globalStats = ref<LocationStatistics | null>(null)
const topRegions = ref<{name: string, count: number}[]>([])
const recentTrips = ref<TimelineNode[]>([])
const trendChartContainer = ref<HTMLElement | null>(null)
let trendChart: echarts.ECharts | null = null
const trendDimension = ref<'year' | 'month'>('year')
const rawTimelineData = ref<any[]>([])

let cachedMapData: { data: any[], max: number, geoJson: any, mapName: string, viewState?: { zoom: number, center: number[] } } | null = null
const regionPhotoCache = new Map<string, { photos: AlbumImage[], count: number, timeSpan: string, firstVisit: string, tags: { name: string, count: number }[] }>()
const regionSubDataCache = new Map<string, { subLevel: string, exploredCount: number, totalCount: number, topSubRegions: { name: string, count: number }[], recentVisits: TimelineNode[] }>()
let resizeTimer: ReturnType<typeof setTimeout> | null = null

const regionSubLevel = ref<string>('')
const regionExploredCount = ref(0)
const regionTotalCount = ref(0)
const regionTopSubRegions = ref<{ name: string, count: number }[]>([])
const regionRecentVisits = ref<TimelineNode[]>([])
const { isDarkMode, currentTheme } = useTheme()
const isDark = isDarkMode

// 获取全局统计数据
const fetchGlobalData = async () => {
  try {
    globalStats.value = await locationService.getStatistics()
    
    // 获取最近足迹
    const trips = await locationService.getTimelineNodes(0, 3)
    if (trips && trips.nodes) {
      recentTrips.value = trips.nodes
    }

    // 获取时间轴数据以渲染趋势图
    const timelineData = await albumService.getTimelineStats()
    if (timelineData && timelineData.timeline) {
      rawTimelineData.value = timelineData.timeline
      renderTrendChart()
    }
  } catch (e) {
    console.error('Failed to fetch global stats', e)
  }
}

// 渲染趋势图
const renderTrendChart = () => {
  if (!trendChartContainer.value || rawTimelineData.value.length === 0) return
  if (trendChart) trendChart.dispose()
  
  trendChart = echarts.init(trendChartContainer.value)
  
  const dataMap: Record<string, number> = {}
  rawTimelineData.value.forEach(item => {
    const key = trendDimension.value === 'year' 
      ? `${item.year}` 
      : `${item.year}-${String(item.month).padStart(2, '0')}`
    dataMap[key] = (dataMap[key] || 0) + item.count
  })
  
  let keys = Object.keys(dataMap).sort()
  // 如果是按月显示且数据过多，只显示最近的 12 个月
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

const fetchRegionSubData = async (name: string) => {
  if (props.level !== 'province' && props.level !== 'city') {
    regionSubLevel.value = ''
    return
  }

  const subLevel = props.level === 'province' ? 'city' : 'district'
  regionSubLevel.value = subLevel

  const cacheKey = `sub_${name}_${subLevel}_${props.startDate || ''}_${props.endDate || ''}`
  const cached = regionSubDataCache.get(cacheKey)
  if (cached) {
    regionExploredCount.value = cached.exploredCount
    regionTotalCount.value = cached.totalCount
    regionTopSubRegions.value = cached.topSubRegions
    regionRecentVisits.value = cached.recentVisits
    return
  }

  regionExploredCount.value = 0
  regionTotalCount.value = 0
  regionTopSubRegions.value = []
  regionRecentVisits.value = []

  try {
    const geoParams: Record<string, string> = { level: subLevel, v: '2' }
    geoParams.parent = name
    const geoRes = await request.get('/api/medias/geojson', { params: geoParams })
    const subGeoJson = geoRes.data ?? geoRes

    let subDistribution = await locationService.getDistribution(subLevel as 'city' | 'province' | 'district' | 'scene', props.startDate, props.endDate)

    const nameMap = buildNameMap(subGeoJson)
    const validNames = new Set(Object.keys(nameMap))
    subDistribution = subDistribution.filter(item =>
      validNames.has(item.name) || [...validNames].some(v => v.includes(item.name))
    )

    const totalCount = subGeoJson.features?.length || 0
    const exploredCount = subDistribution.filter(d => d.count > 0).length

    regionTotalCount.value = totalCount
    regionExploredCount.value = exploredCount

    const topSubRegions = [...subDistribution]
      .sort((a, b) => b.count - a.count)
      .slice(0, 5)
    regionTopSubRegions.value = topSubRegions

    let recentVisits: TimelineNode[] = []
    try {
      const trips = await locationService.getTimelineNodes(0, 30, props.startDate, props.endDate, subLevel)
      if (trips?.nodes) {
        recentVisits = trips.nodes.filter((node: TimelineNode) =>
          validNames.has(node.locationName) || [...validNames].some(v => v.includes(node.locationName))
        ).slice(0, 3)
      }
    } catch { /* non-critical */ }
    regionRecentVisits.value = recentVisits

    regionSubDataCache.set(cacheKey, { subLevel, exploredCount, totalCount, topSubRegions, recentVisits })
  } catch (e) {
    console.error('Failed to fetch sub-region data', e)
    regionSubLevel.value = ''
  }
}

const selectRegion = async (name: string, count: number) => {
  selectedRegion.value = name
  selectedRegionCount.value = count

  const cacheKey = `${name}_${props.level}_${props.startDate || ''}_${props.endDate || ''}`
  const cached = regionPhotoCache.get(cacheKey)
  if (cached) {
    regionPhotos.value = cached.photos
    regionTimeSpan.value = cached.timeSpan
    regionFirstVisit.value = cached.firstVisit
    regionTags.value = cached.tags
    fetchRegionSubData(name)
    return
  }

  regionTimeSpan.value = ''
  regionTags.value = []
  try {
    const photosResponse = await locationService.getLocationPhotos(
      name,
      props.level as 'city' | 'province' | 'district' | 'scene',
      0, 20,
      props.startDate,
      props.endDate
    )
    const rawPhotos = Array.isArray(photosResponse) ? photosResponse : (photosResponse as any).items || []

    if (rawPhotos.length > 0) {
      const times = rawPhotos.map((p: any) => new Date(p.photo_time).getTime()).filter((t: number) => !isNaN(t))
      if (times.length > 0) {
        const minDate = new Date(Math.min(...times))
        const maxDate = new Date(Math.max(...times))
        regionFirstVisit.value = `${minDate.getFullYear()}年${minDate.getMonth() + 1}月${minDate.getDate()}日`
        if (minDate.getFullYear() === maxDate.getFullYear() && minDate.getMonth() === maxDate.getMonth()) {
          regionTimeSpan.value = `${minDate.getFullYear()}年${minDate.getMonth() + 1}月`
        } else {
          regionTimeSpan.value = `${minDate.getFullYear()}.${minDate.getMonth() + 1} - ${maxDate.getFullYear()}.${maxDate.getMonth() + 1}`
        }
      }
    }

    const tagCount: Record<string, number> = {}
    rawPhotos.forEach((p: any) => {
      if (p.metadata_info?.tags) {
        p.metadata_info.tags.forEach((t: any) => {
          tagCount[t.tag_name] = (tagCount[t.tag_name] || 0) + 1
        })
      }
    })
    regionTags.value = Object.entries(tagCount)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(t => ({ name: t[0], count: t[1] }))

    const photos = rawPhotos.slice(0, 6).map(mapPhotoToImage)
    regionPhotos.value = photos

    regionPhotoCache.set(cacheKey, {
      photos,
      count,
      timeSpan: regionTimeSpan.value,
      firstVisit: regionFirstVisit.value,
      tags: regionTags.value
    })
  } catch (e) {
    console.error('Failed to fetch region photos', e)
  }

  fetchRegionSubData(name)
}

const clearSelection = () => {
  if (myMap && selectedRegion.value) {
    // 必须传入 name 来取消特定区域的选中，否则可能不生效
    myMap.dispatchAction({
      type: 'downplay',
      seriesIndex: 0,
      name: selectedRegion.value
    })
    myMap.dispatchAction({
      type: 'unselect',
      seriesIndex: 0,
      name: selectedRegion.value
    })
  }
  selectedRegion.value = null
  regionPhotos.value = []
  regionSubLevel.value = ''
  regionExploredCount.value = 0
  regionTotalCount.value = 0
  regionTopSubRegions.value = []
  regionRecentVisits.value = []
}

const emitClickLocation = (name: string | null, overrideLevel?: string) => {
  if (name) {
    emit('click-location', name, overrideLevel)
  }
}

const initMap = async (viewState?: { zoom: number, center: number[] }) => {
  if (!mapContainer.value) return

  if (myMap) {
    myMap.dispose()
  }

  myMap = echarts.init(mapContainer.value)
  myMap.showLoading({
    text: '',
    color: currentTheme.value.primary,
    maskColor: isDark.value ? 'rgba(30, 41, 59, 0.8)' : 'rgba(255, 255, 255, 0.8)',
    spinnerRadius: 14,
    lineWidth: 3
  })

  try {
    if (props.level === 'photo-map') {
      myMap.hideLoading()
      return
    }

    // 1. Fetch GeoJSON via axios
    const mapName = props.parentRegion ? `map_${props.parentRegion}` : 'china'
    const geoParams: Record<string, string> = { level: props.level, v: '2' }
    if (props.parentRegion) geoParams.parent = props.parentRegion
    const geoRes = await request.get('/api/medias/geojson', { params: geoParams })
    const geoJson = geoRes.data ?? geoRes
    echarts.registerMap(mapName, geoJson)

    // 2. Fetch Distribution Data
    let distribution = await locationService.getDistribution(props.level as 'city' | 'province' | 'district' | 'scene' | undefined, props.startDate, props.endDate)

    // Filter by parentRegion using shared nameMap
    if (props.parentRegion && geoJson.features) {
      const nameMap = buildNameMap(geoJson)
      const validNames = new Set(Object.keys(nameMap))
      distribution = distribution.filter(item => validNames.has(item.name) || [...validNames].some(v => v.includes(item.name)))
    }

    // 3. Prepare Data using shared nameMap
    const nameMap = buildNameMap(geoJson)
    const data = distribution.map(item => ({
      name: nameMap[item.name] || item.name,
      value: item.count,
    }))

    // Update Top Regions
    topRegions.value = [...data]
      .sort((a, b) => b.value - a.value)
      .slice(0, 5)
      .map(item => ({
        name: item.name,
        count: item.value
      }))

    // Calculate 90th percentile to handle outliers for better color distribution
    const values = data.map(d => d.value).sort((a, b) => a - b)
    const p90 = values[Math.floor(values.length * 0.9)] || 10
    const maxVal = Math.max(...values, 10)
    const visualMax = maxVal > p90 * 2 ? p90 * 1.5 : maxVal

    cachedMapData = { data, max: visualMax, geoJson, mapName, viewState }
    renderMap(data, visualMax, geoJson, mapName, viewState)
    myMap.hideLoading()

    // 4. Bind Events
    myMap.on('click', (params: any) => {
      if (params.name) {
        if (selectedRegion.value === params.name) {
          clearSelection()
        } else {
          selectRegion(params.name, params.value || 0)
        }
      }
    })

  } catch (e) {
    console.error('Map init failed', e)
    myMap?.hideLoading()
  }
}

const renderMap = (data: any[], max: number, geoJson: any, mapName: string, viewState?: { zoom: number, center: number[] }) => {
  if (!myMap) return

  const isDarkMode = isDark.value
  const isMobile = window.innerWidth < 768

  // Use shared nameMap builder
  const nameMap = buildNameMap(geoJson)

  // 动态主题色渐变：根据当前主题的 RGB 和背景色进行混合，生成纯色（非透明）渐变
  const rgbStr = currentTheme.value.rgb
  const bgRgb = isDarkMode ? [30, 41, 59] : [244, 244, 245] // #1e293b 或 #f4f4f5
  
  const mixColor = (ratio: number) => {
    const [r1, g1, b1] = rgbStr.split(',').map(Number)
    const [r2, g2, b2] = bgRgb
    const r = Math.round(r1 * ratio + r2 * (1 - ratio))
    const g = Math.round(g1 * ratio + g2 * (1 - ratio))
    const b = Math.round(b1 * ratio + b2 * (1 - ratio))
    return `rgb(${r}, ${g}, ${b})`
  }

  const inRangeColors = isDarkMode
    ? [mixColor(0.3), mixColor(0.6), mixColor(1)]
    : [mixColor(0.2), mixColor(0.6), mixColor(1)]

  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        if (!params.value) return params.name
        return `<div style="font-weight:bold">${params.name}</div><div style="font-size:12px">照片数量: ${params.value}</div>`
      },
      backgroundColor: isDarkMode ? 'rgba(30, 41, 59, 0.9)' : 'rgba(255, 255, 255, 0.9)',
      borderColor: isDarkMode ? '#475569' : '#e2e8f0',
      textStyle: {
        color: isDarkMode ? '#f1f5f9' : '#1e293b'
      }
    },
    visualMap: {
      show: false,
      min: 1, // Start from 1 so 0 is not colored (treated as empty)
      max: max,
      left: isMobile ? 'center' : 'left',
      bottom: isMobile ? 20 : 30,
      orient: isMobile ? 'horizontal' : 'vertical',
      text: ['高', '低'],
      calculable: true, // Show handles
      inRange: {
        color: inRangeColors,
        // 去掉透明度渐变，使用纯色渐变显得更干净高级
        opacity: 1 
      },
      textStyle: {
        color: isDarkMode ? '#cbd5e1' : '#475569'
      },
      // Ensure the legend is large enough
      itemWidth: isMobile ? 15 : 20,
      itemHeight: isMobile ? 100 : 140
    },
    series: [
      {
        name: '照片数量',
        type: 'map',
        map: mapName,
        roam: true,
        selectedMode: 'single', // 开启单选模式
        // 如果是子区域地图，默认缩小一点比例以留出边距，否则使用传入的 zoom 或 1.2
        zoom: viewState?.zoom || (props.parentRegion ? 0.9 : 1.2),
        center: viewState?.center || undefined,
        nameMap: nameMap,
        data: data,
        label: {
          show: true,
          formatter: (params: any) => {
            // Only show name for regions with data (lit up)
            return params.value > 0 ? params.name : ''
          },
          color: isDarkMode ? '#e2e8f0' : currentTheme.value.primary, // 浅色模式下文字使用动态主色
          fontSize: props.level === 'province' ? (isMobile ? 10 : 12) : (isMobile ? 9 : 11),
          textBorderColor: isDarkMode ? 'rgba(0,0,0,0.8)' : 'rgba(255,255,255,0.9)',
          textBorderWidth: 2,
        },
        labelLayout: {
          hideOverlap: true
        },
        itemStyle: {
          // 优化未点亮区域的底色和边框，增加浅色模式下的对比度
          areaColor: isDarkMode ? '#1e293b' : '#e2e8f0', // 浅色模式加深底色，使用更明显的灰色
          borderColor: isDarkMode ? '#334155' : '#ffffff', // 浅色模式保持白边，由于底色加深，白边会更清晰
          borderWidth: isDarkMode ? 0.5 : 1
        },
        emphasis: {
          itemStyle: {
            areaColor: currentTheme.value.primary,
            borderColor: isDarkMode ? mixColor(0.8) : '#ffffff',
            borderWidth: 1
          },
          label: {
            show: true,
            color: '#ffffff',
            textBorderColor: isDarkMode ? 'rgba(0,0,0,0.8)' : 'rgba(0,0,0,0.3)',
            textBorderWidth: 2
          }
        },
        select: {
          itemStyle: {
            areaColor: mixColor(0.85),
            borderColor: currentTheme.value.primary,
            borderWidth: 2
          },
          label: {
            show: true,
            color: '#ffffff',
            textBorderColor: 'rgba(0,0,0,0.5)',
            textBorderWidth: 2
          }
        }
      }
    ],
    // 工具栏：保存为图片
    toolbox: {
      show: true,
      right: isMobile ? 10 : 20,
      top: 20,
      feature: {
        saveAsImage: {
          title: '保存为图片',
          name: '位置分布图',
          backgroundColor: isDarkMode ? '#0f172a' : '#ffffff',
          excludeComponents: ['toolbox'],
          pixelRatio: isMobile ? 5 : 3,
        }
      },
      iconStyle: {
        borderColor: isDarkMode ? '#cbd5e1' : '#475569'
      },
      emphasis: {
        iconStyle: {
          borderColor: isDarkMode ? '#fff' : '#0f172a'
        }
      }
    }
  }

  myMap.setOption(option)
}

// Watchers
watch(() => props.viewMode, (newMode) => {
  if (newMode === 'map') {
    nextTick(() => {
      initMap()
      trendChart?.resize()
    })
  }
})

// When level changes, we might need to re-init if we are in map view
watch([() => props.level, () => props.parentRegion], ([newLevel, newParentRegion]) => {
  if (props.viewMode === 'map' && newLevel !== 'photo-map' && newLevel !== 'scene') {
    nextTick(() => {
      initMap()
    })
  }
})

watch([() => props.startDate, () => props.endDate], () => {
  if (props.viewMode === 'map' && props.level !== 'photo-map' && props.level !== 'scene') {
    nextTick(() => {
      initMap()
    })
  }
})

watch([isDark, currentTheme], () => {
  if (props.viewMode === 'map' && myMap) {
    if (cachedMapData) {
      renderMap(cachedMapData.data, cachedMapData.max, cachedMapData.geoJson, cachedMapData.mapName, cachedMapData.viewState)
    } else {
      initMap()
    }
    renderTrendChart()
  }
}, { deep: true })

watch(selectedRegion, (val, oldVal) => {
  if (oldVal && !val) {
    nextTick(() => renderTrendChart())
  }
})

const handleResize = () => {
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = setTimeout(() => {
    myMap?.resize()
    trendChart?.resize()
  }, 200)
}

onMounted(() => {
  fetchGlobalData()
  if (props.viewMode === 'map' && props.level !== 'photo-map') {
    nextTick(() => {
      initMap()
    })
  }
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (resizeTimer) clearTimeout(resizeTimer)
  myMap?.dispose()
  trendChart?.dispose()
  regionPhotoCache.clear()
  regionSubDataCache.clear()
  cachedMapData = null
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
