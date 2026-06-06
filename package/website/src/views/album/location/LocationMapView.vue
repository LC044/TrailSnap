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
            </div>

            <!-- 照片预览墙 -->
            <div v-if="regionPhotos.length > 0" class="space-y-2">
              <div class="flex items-center justify-between">
                <span class="text-sm font-medium text-gray-700 dark:text-gray-300">精彩瞬间</span>
                <button @click="emitClickLocation(selectedRegion)" class="px-2 py-1 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 text-xs text-primary-500 hover:text-primary-600 transition-colors flex items-center gap-0.5">
                  查看全部 <ChevronRight class="w-3 h-3" />
                </button>
              </div>
              <div class="grid grid-cols-3 gap-2">
                <div 
                  v-for="(photo, index) in regionPhotos" 
                  :key="photo.id"
                  class="aspect-square rounded-lg overflow-hidden cursor-pointer group relative"
                  @click="emitClickLocation(selectedRegion)"
                >
                  <img :src="photo.thumbnail || photo.url" class="w-full h-full object-cover transition-transform duration-300 group-hover:scale-110" loading="lazy" />
                  <div class="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors"></div>
                </div>
              </div>
            </div>
            <div v-else class="text-center py-6 text-gray-400 text-sm">
              暂无照片预览
            </div>
          </div>

          <!-- 全局概览 (未选中时显示) -->
          <div v-else class="space-y-8 animate-fade-in">
            <div>
              <h2 class="text-xl font-bold text-gray-800 dark:text-white mb-4">足迹概览</h2>
              <div class="grid grid-cols-2 gap-3">
                <div class="bg-primary-50 dark:bg-primary-900/20 p-3 rounded-xl border border-primary-100 dark:border-primary-800/30">
                  <div class="text-xs text-primary-600 dark:text-primary-400 mb-1">点亮省份</div>
                  <div class="text-2xl font-bold text-primary-700 dark:text-primary-300">
                    {{ globalStats?.province_count || 0 }}
                  </div>
                </div>
                <div class="bg-blue-50 dark:bg-blue-900/20 p-3 rounded-xl border border-blue-100 dark:border-blue-800/30">
                  <div class="text-xs text-blue-600 dark:text-blue-400 mb-1">点亮城市</div>
                  <div class="text-2xl font-bold text-blue-700 dark:text-blue-300">
                    {{ globalStats?.city_count || 0 }}
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
                      <div class="h-full bg-primary-500/80 rounded-full transition-all duration-1000" :style="{ width: `${(item.count / topRegions[0].count) * 100}%` }"></div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 时间轴趋势图 -->
          <div>
            <h3 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-1.5">
              <TrendingUp class="w-4 h-4 text-green-500" /> 足迹趋势
            </h3>
            <div ref="trendChartContainer" class="h-40 w-full bg-gray-50 dark:bg-gray-800/30 rounded-xl border border-gray-100 dark:border-gray-700/50"></div>
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
import { MapPin, X, ChevronRight, Trophy, TrendingUp } from 'lucide-vue-next'
import type { LocationStatistics } from '@/types/location'
import type { Photo, AlbumImage } from '@/types/album'
import { mapPhotoToImage } from '@/stores/photoStore'

const props = defineProps<{
  level: string
  viewMode: string
  startDate?: string
  endDate?: string
}>()

const emit = defineEmits<{
  (e: 'click-location', name: string): void
  (e: 'change-level', level: string, viewState: { zoom: number, center: number[] }): void
}>()

const mapContainer = ref<HTMLElement | null>(null)
let myMap: echarts.ECharts | null = null

// 新增右侧面板状态
const selectedRegion = ref<string | null>(null)
const selectedRegionCount = ref(0)
const regionPhotos = ref<AlbumImage[]>([])
const globalStats = ref<LocationStatistics | null>(null)
const topRegions = ref<{name: string, count: number}[]>([])
const trendChartContainer = ref<HTMLElement | null>(null)
let trendChart: echarts.ECharts | null = null

let zoomTimer: any = null
const { isDarkMode, currentTheme } = useTheme()
const isDark = isDarkMode

// 获取全局统计数据
const fetchGlobalData = async () => {
  try {
    globalStats.value = await locationService.getStatistics()
    
    // 获取时间轴数据以渲染趋势图
    const timelineData = await albumService.getTimelineStats()
    if (timelineData && timelineData.timeline) {
      renderTrendChart(timelineData.timeline)
    }
  } catch (e) {
    console.error('Failed to fetch global stats', e)
  }
}

// 渲染趋势图
const renderTrendChart = (timeline: any[]) => {
  if (!trendChartContainer.value) return
  if (trendChart) trendChart.dispose()
  
  trendChart = echarts.init(trendChartContainer.value)
  
  // 按年份聚合
  const yearMap: Record<number, number> = {}
  timeline.forEach(item => {
    yearMap[item.year] = (yearMap[item.year] || 0) + item.count
  })
  
  const years = Object.keys(yearMap).sort()
  const counts = years.map(y => yearMap[parseInt(y)])

  const option = {
    tooltip: { trigger: 'axis' },
    grid: { left: 10, right: 10, top: 10, bottom: 20, containLabel: true },
    xAxis: {
      type: 'category',
      data: years,
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
      itemStyle: { color: '#10b981' },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(16, 185, 129, 0.3)' },
          { offset: 1, color: 'rgba(16, 185, 129, 0.0)' }
        ])
      }
    }]
  }
  
  trendChart.setOption(option)
}

const selectRegion = async (name: string, count: number) => {
  selectedRegion.value = name
  selectedRegionCount.value = count
  try {
    const photosResponse = await locationService.getLocationPhotos(
      name, 
      props.level as 'city' | 'province' | 'district' | 'scene', 
      0, 6, 
      props.startDate, 
      props.endDate
    )
    // 根据返回的数据结构（数组或带有 items 的对象）提取图片列表
    const rawPhotos = Array.isArray(photosResponse) ? photosResponse : (photosResponse as any).items || []
    
    // 转换为前端显示的 AlbumImage 对象
    regionPhotos.value = rawPhotos.map(mapPhotoToImage)
  } catch (e) {
    console.error('Failed to fetch region photos', e)
  }
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
}

const emitClickLocation = (name: string | null) => {
  if (name) {
    emit('click-location', name)
  }
}

const initMap = async (viewState?: { zoom: number, center: number[] }) => {
  if (!mapContainer.value) return

  // Dispose existing instance if any
  if (myMap) {
    myMap.dispose()
  }

  myMap = echarts.init(mapContainer.value)
  myMap.showLoading()

  try {
    if (props.level === 'photo-map') return
    // 1. Fetch GeoJSON
    const geoResponse = await fetch(`/api/medias/geojson?level=${props.level}`)
    if (!geoResponse.ok) throw new Error('Failed to load GeoJSON')
    const geoJson = await geoResponse.json()
    echarts.registerMap('china', geoJson)

    // 2. Fetch Distribution Data
    const distribution = await locationService.getDistribution(props.level as 'city' | 'province' | 'district' | 'scene' | undefined, props.startDate, props.endDate)
    
    // 3. Prepare Data
    const nameMap: Record<string, string> = {}
    if (geoJson && geoJson.features) {
      geoJson.features.forEach((f: any) => {
        const fullName = f.properties.name
        if (fullName) {
          nameMap[fullName] = fullName
          // Add short names (e.g. "广东" for "广东省")
          const shortName = fullName.replace(/(省|市|自治区|特别行政区|回族自治区|壮族自治区|维吾尔自治区|县|区)$/, '')
          if (shortName && shortName !== fullName) {
            nameMap[shortName] = fullName
          }
        }
      })
    }

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
    // Use p90 as visual max, but allow real max to be shown
    const visualMax = maxVal > p90 * 2 ? p90 * 1.5 : maxVal

    renderMap(data, visualMax, geoJson, viewState)
    myMap.hideLoading()

    // 4. Bind Events
    myMap.on('click', (params: any) => {
      if (params.name) {
        // 如果点击的是已经选中的区域，则取消选中
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

const renderMap = (data: any[], max: number, geoJson: any, viewState?: { zoom: number, center: number[] }) => {
  if (!myMap) return

  const isDarkMode = isDark.value
  const isMobile = window.innerWidth < 768

  // Build nameMap for ECharts to match GeoJSON names with data names
  const nameMap: Record<string, string> = {}
  if (geoJson && geoJson.features) {
    geoJson.features.forEach((f: any) => {
      const fullName = f.properties.name
      if (fullName) {
        // Find if we have data for this (short name or full name)
        const shortName = fullName.replace(/(省|市|自治区|特别行政区|回族自治区|壮族自治区|维吾尔自治区|县|区)$/, '')
        const hasData = data.find(d => d.name === fullName || d.name === shortName)
        if (hasData) {
          nameMap[fullName] = hasData.name
        }
      }
    })
  }

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
        return `
          <div class="font-bold">${params.name}</div>
          <div class="text-sm">照片数量: ${params.value}</div>
        `
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
        map: 'china',
        roam: true,
        selectedMode: 'single', // 开启单选模式
        zoom: viewState?.zoom || 1.2,
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
            areaColor: '#eab308', // 选中时变成黄色 (Yellow 500)
            borderColor: '#fef08a',
            borderWidth: 1
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
watch(() => props.level, (newLevel) => {
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
    initMap()
  }
}, { deep: true })

// Resize handler
const handleResize = () => {
  myMap?.resize()
  trendChart?.resize()
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
  myMap?.dispose()
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
