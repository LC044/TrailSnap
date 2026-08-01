<template>
  <div class="w-full h-full relative">
    <div ref="mapContainer" class="w-full h-full"></div>
    
    <!-- 面包屑导航 -->
    <div v-if="parentRegion" class="absolute top-6 left-6 z-10 flex items-center gap-2 bg-white/90 dark:bg-gray-800/90 backdrop-blur-md px-3 py-2 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 animate-fade-in">
      <button @click="emit('change-level', level === 'city' ? 'province' : 'city', { zoom: 1.2, center: [] })" class="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 hover:text-primary-500 dark:text-gray-400 transition-colors" title="返回上一级">
        <ArrowLeft class="w-4 h-4" />
      </button>
      <div class="w-px h-4 bg-gray-300 dark:bg-gray-600"></div>
      <button @click="emit('change-level', level === 'city' ? 'province' : 'city', { zoom: 1.2, center: [] })" class="text-sm font-medium text-gray-500 hover:text-primary-500 dark:text-gray-400 dark:hover:text-primary-400 transition-colors flex items-center gap-1">
        <MapPin class="w-4 h-4" />
        全国
      </button>
      <ChevronRight class="w-4 h-4 text-gray-400" />
      <span class="text-sm font-bold text-gray-800 dark:text-white pr-2">{{ parentRegion }}</span>
    </div>
    
    <!-- Map Controls Overlay -->
    <div class="absolute bottom-6 right-6 flex flex-col gap-2 z-10">
       <button @click="handleZoom('in')" class="p-2 bg-white/90 dark:bg-gray-800/90 backdrop-blur border border-gray-200 dark:border-gray-700 rounded-lg shadow-sm hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300 transition-colors" title="放大">
         <ZoomIn class="w-5 h-5" />
       </button>
       <button @click="handleZoom('out')" class="p-2 bg-white/90 dark:bg-gray-800/90 backdrop-blur border border-gray-200 dark:border-gray-700 rounded-lg shadow-sm hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300 transition-colors" title="缩小">
         <ZoomOut class="w-5 h-5" />
       </button>
       <button @click="resetMap" class="p-2 bg-white/90 dark:bg-gray-800/90 backdrop-blur border border-gray-200 dark:border-gray-700 rounded-lg shadow-sm hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300 transition-colors" title="重置视角">
         <RotateCcw class="w-5 h-5" />
       </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import { locationService } from '@/api/location'
import { useTheme } from '@/composables/useTheme'
import { MapPin, ChevronRight, ZoomIn, ZoomOut, RotateCcw, ArrowLeft } from 'lucide-vue-next'
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
  selectedRegion: string | null
}>()

const emit = defineEmits<{
  (e: 'change-level', level: string, viewState: { zoom: number, center: number[], parentRegion?: string }): void
  (e: 'select-region', name: string, count: number): void
  (e: 'update-top-regions', regions: { name: string, count: number }[]): void
}>()

const mapContainer = ref<HTMLElement | null>(null)
let myMap: echarts.ECharts | null = null

const { isDarkMode, currentTheme } = useTheme()
const isDark = isDarkMode

let cachedMapData: { data: any[], max: number, geoJson: any, mapName: string, viewState?: { zoom: number, center: number[] } } | null = null
let resizeTimer: ReturnType<typeof setTimeout> | null = null

// 双击下钻检测：记录上一次单击的区块名与时间，用于区分「单击选中」与「双击进入下一级」
let lastClickName = ''
let lastClickTime = 0
const DBL_CLICK_THRESHOLD = 350

const handleZoom = (type: 'in' | 'out') => {
  if (!myMap) return
  const currentOption = myMap.getOption()
  const series = currentOption ? (currentOption as any).series[0] : null
  if (!series) return
  const currentZoom = series.zoom || 1
  const newZoom = type === 'in' ? currentZoom * 1.2 : currentZoom / 1.2
  myMap.setOption({
    series: [{ zoom: newZoom }]
  })
}

const resetMap = () => {
  if (!myMap) return
  myMap.dispatchAction({ type: 'restore' })
}

const clearSelection = () => {
  if (myMap && props.selectedRegion) {
    myMap.dispatchAction({
      type: 'downplay',
      seriesIndex: 0,
      name: props.selectedRegion
    })
    myMap.dispatchAction({
      type: 'unselect',
      seriesIndex: 0,
      name: props.selectedRegion
    })
  }
}

defineExpose({ clearSelection })

const initMap = async (viewState?: { zoom: number, center: number[] }) => {
  if (!mapContainer.value) return

  if (myMap) {
    myMap.dispose()
  }

  // 地图重建后，上一次的点击记录失效，避免跨级别误判为双击
  lastClickName = ''
  lastClickTime = 0

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

    const mapName = props.parentRegion ? `map_${props.parentRegion}` : 'china'
    const geoParams: Record<string, string> = { level: props.level, v: '2' }
    if (props.parentRegion) geoParams.parent = props.parentRegion
    const geoRes = await request.get('/api/medias/geojson', { params: geoParams })
    const geoJson = geoRes.data ?? geoRes
    echarts.registerMap(mapName, geoJson)

    let distribution = await locationService.getDistribution(props.level as 'city' | 'province' | 'district' | 'scene' | undefined, props.startDate, props.endDate)

    if (props.parentRegion && geoJson.features) {
      const nameMap = buildNameMap(geoJson)
      const validNames = new Set(Object.keys(nameMap))
      distribution = distribution.filter(item => validNames.has(item.name) || [...validNames].some(v => v.includes(item.name)))
    }

    const nameMap = buildNameMap(geoJson)
    const data = distribution.map(item => ({
      name: nameMap[item.name] || item.name,
      value: item.count,
    }))

    const topRegions = [...data]
      .sort((a, b) => b.value - a.value)
      .slice(0, 5)
      .map(item => ({
        name: item.name,
        count: item.value
      }))
    emit('update-top-regions', topRegions)

    const values = data.map(d => d.value).sort((a, b) => a - b)
    const p90 = values[Math.floor(values.length * 0.9)] || 10
    const maxVal = Math.max(...values, 10)
    const visualMax = maxVal > p90 * 2 ? p90 * 1.5 : maxVal

    cachedMapData = { data, max: visualMax, geoJson, mapName, viewState }
    renderMap(data, visualMax, geoJson, mapName, viewState)
    myMap.hideLoading()

    myMap.on('click', (params: any) => {
      if (!params.name) return
      const name = params.name
      const value = params.value || 0
      const now = Date.now()

      // 双击同一区块 → 下钻到下一级（等价于右侧「进入城市/区县地图」按钮）
      const nextLevel = props.level === 'province' ? 'city' : props.level === 'city' ? 'district' : null
      if (nextLevel && lastClickName === name && now - lastClickTime < DBL_CLICK_THRESHOLD) {
        lastClickName = ''
        lastClickTime = 0
        // 首次点击若落在已选区块上会触发「取消选中」，此处需重新选中，
        // 以保证下钻后右侧仍展示该区域详情（与「先单击选中再点进入按钮」的既有路径一致）
        if (props.selectedRegion !== name) {
          emit('select-region', name, value)
        }
        emit('change-level', nextLevel, { zoom: 0.9, center: [], parentRegion: name })
        return
      }

      // 普通单击：选中或取消选中
      lastClickName = name
      lastClickTime = now
      if (props.selectedRegion === name) {
        clearSelection()
        emit('select-region', '', 0) // emit empty string to signal clear
      } else {
        emit('select-region', name, value)
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

  const nameMap = buildNameMap(geoJson)

  const rgbStr = currentTheme.value.rgb
  const bgRgb = isDarkMode ? [30, 41, 59] : [244, 244, 245]
  
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
      min: 1,
      max: max,
      left: isMobile ? 'center' : 'left',
      bottom: isMobile ? 20 : 30,
      orient: isMobile ? 'horizontal' : 'vertical',
      text: ['高', '低'],
      calculable: true,
      inRange: { color: inRangeColors, opacity: 1 },
      textStyle: { color: isDarkMode ? '#cbd5e1' : '#475569' },
      itemWidth: isMobile ? 15 : 20,
      itemHeight: isMobile ? 100 : 140
    },
    series: [
      {
        name: '照片数量',
        type: 'map',
        map: mapName,
        roam: true,
        selectedMode: 'single',
        zoom: viewState?.zoom || (props.parentRegion ? 0.9 : 1.2),
        center: viewState?.center || undefined,
        nameMap: nameMap,
        data: data,
        label: {
          show: true,
          formatter: (params: any) => params.value > 0 ? params.name : '',
          color: isDarkMode ? '#e2e8f0' : currentTheme.value.primary,
          fontSize: props.level === 'province' ? (isMobile ? 10 : 12) : (isMobile ? 9 : 11),
          textBorderColor: isDarkMode ? 'rgba(0,0,0,0.8)' : 'rgba(255,255,255,0.9)',
          textBorderWidth: 2,
        },
        labelLayout: { hideOverlap: true },
        itemStyle: {
          areaColor: isDarkMode ? '#1e293b' : '#e2e8f0',
          borderColor: isDarkMode ? '#334155' : '#ffffff',
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
      iconStyle: { borderColor: isDarkMode ? '#cbd5e1' : '#475569' },
      emphasis: { iconStyle: { borderColor: isDarkMode ? '#fff' : '#0f172a' } }
    }
  }

  myMap.setOption(option)
}

watch(() => props.viewMode, (newMode) => {
  if (newMode === 'map') {
    nextTick(() => { initMap() })
  }
})

watch([() => props.level, () => props.parentRegion], ([newLevel, newParentRegion]) => {
  if (props.viewMode === 'map' && newLevel !== 'photo-map' && newLevel !== 'scene') {
    nextTick(() => { initMap() })
  }
})

watch([() => props.startDate, () => props.endDate], () => {
  if (props.viewMode === 'map' && props.level !== 'photo-map' && props.level !== 'scene') {
    nextTick(() => { initMap() })
  }
})

watch([isDark, currentTheme], () => {
  if (props.viewMode === 'map' && myMap) {
    if (cachedMapData) {
      renderMap(cachedMapData.data, cachedMapData.max, cachedMapData.geoJson, cachedMapData.mapName, cachedMapData.viewState)
    } else {
      initMap()
    }
  }
}, { deep: true })

watch(() => props.selectedRegion, (val) => {
  if (!val && myMap) {
    // If selectedRegion is cleared from parent
    const currentOption = myMap.getOption()
    if (currentOption) {
      myMap.dispatchAction({ type: 'downplay', seriesIndex: 0 })
      myMap.dispatchAction({ type: 'unselect', seriesIndex: 0 })
    }
  }
})

const handleResize = () => {
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = setTimeout(() => { myMap?.resize() }, 200)
}

onMounted(() => {
  if (props.viewMode === 'map' && props.level !== 'photo-map') {
    nextTick(() => { initMap() })
  }
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (resizeTimer) clearTimeout(resizeTimer)
  myMap?.dispose()
  cachedMapData = null
})
</script>

<style scoped>
.animate-fade-in { animation: fadeIn 0.3s ease-in-out; }
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(5px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
