<template>
  <div class="immersive-map w-full h-full relative">
    <div ref="mapContainer" class="w-full h-full"></div>
    
    <!-- 面包屑导航 -->
    <div v-if="parentRegion" class="map-glass absolute top-20 left-6 z-10 flex items-center gap-2 backdrop-blur-md px-3 py-2 rounded-xl animate-fade-in">
      <button @click="emit('change-level', level === 'city' ? 'province' : 'city', { zoom: 1.2, center: [] })" class="p-1 rounded text-[#7891aa] hover:text-primary-500 transition-colors focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none" title="返回上一级">
        <ArrowLeft class="w-4 h-4" />
      </button>
      <div class="w-px h-4 bg-[#29425a]"></div>
      <button @click="emit('change-level', level === 'city' ? 'province' : 'city', { zoom: 1.2, center: [] })" class="text-sm font-medium text-[#7891aa] hover:text-primary-500 transition-colors flex items-center gap-1 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none">
        <MapPin class="w-4 h-4" />
        全国
      </button>
      <ChevronRight class="w-4 h-4 text-gray-400" />
      <span class="text-sm font-bold text-white pr-2">{{ parentRegion }}</span>
    </div>
    
    <!-- Map Controls Overlay -->
    <div class="absolute bottom-32 right-6 flex flex-col gap-2 z-10">
       <button @click="handleZoom('in')" class="map-control focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none" title="放大">
         <ZoomIn class="w-5 h-5" />
       </button>
       <button @click="handleZoom('out')" class="map-control focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none" title="缩小">
         <ZoomOut class="w-5 h-5" />
       </button>
       <button @click="resetMap" class="map-control focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none" title="重置视角">
         <RotateCcw class="w-5 h-5" />
       </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { echarts } from '@/utils/echarts'
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
let distributionRequestId = 0
const MOBILE_ROAM_ZOOM_DAMPING = 0.35

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
    maskColor: 'rgba(7, 17, 31, 0.84)',
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

    // ECharts applies a fixed 1.1x step for every touch pinch event. Mobile
    // browsers can emit many such events for a small finger movement, making
    // the map jump several zoom levels. Counter-adjust each mobile zoom event
    // to 35% of its original delta while leaving one-finger panning untouched.
    myMap.on('georoam', (params: any) => {
      if (!myMap || window.innerWidth >= 768 || typeof params.zoom !== 'number') return
      const series = (myMap.getOption() as any)?.series?.[0]
      const currentZoom = Number(series?.zoom) || 1
      const dampedFactor = 1 + (params.zoom - 1) * MOBILE_ROAM_ZOOM_DAMPING
      const zoom = currentZoom / params.zoom * dampedFactor
      myMap.setOption({ series: [{ zoom }] })
    })

  } catch (e) {
    console.error('Map init failed', e)
    myMap?.hideLoading()
  }
}

const renderMap = (data: any[], max: number, geoJson: any, mapName: string, viewState?: { zoom: number, center: number[] }) => {
  if (!myMap) return

  const isDarkMode = true
  const isMobile = window.innerWidth < 768

  const nameMap = buildNameMap(geoJson)

  const rgbStr = currentTheme.value.rgb
  const bgRgb = [11, 28, 48]
  
  const mixColor = (ratio: number) => {
    const [r1, g1, b1] = rgbStr.split(',').map(Number)
    const [r2, g2, b2] = bgRgb
    const r = Math.round(r1 * ratio + r2 * (1 - ratio))
    const g = Math.round(g1 * ratio + g2 * (1 - ratio))
    const b = Math.round(b1 * ratio + b2 * (1 - ratio))
    return `rgb(${r}, ${g}, ${b})`
  }

  const inRangeColors = [mixColor(0.24), mixColor(0.55), mixColor(0.92)]

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
        scaleLimit: { min: 0.7, max: 8 },
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
          areaColor: '#0d2238',
          borderColor: `rgba(${rgbStr}, 0.34)`,
          borderWidth: 0.9,
          shadowColor: `rgba(${rgbStr}, 0.16)`,
          shadowBlur: 8
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

// 时间筛选只更新地图数据，不销毁 ECharts 实例或重新加载 GeoJSON。
// 这样地图会一直留在画面中，并保留用户当前的缩放和拖拽位置。
const refreshDistribution = async () => {
  if (!myMap || !cachedMapData) {
    await initMap()
    return
  }

  const requestId = ++distributionRequestId
  const { geoJson, mapName } = cachedMapData

  try {
    let distribution = await locationService.getDistribution(
      props.level as 'city' | 'province' | 'district' | 'scene' | undefined,
      props.startDate,
      props.endDate
    )
    // 自动巡游或快速点击年份时，只应用最后一次请求，避免旧响应覆盖新年份。
    if (requestId !== distributionRequestId || !myMap) return

    if (props.parentRegion && geoJson.features) {
      const validNames = new Set(Object.keys(buildNameMap(geoJson)))
      distribution = distribution.filter(item =>
        validNames.has(item.name) || [...validNames].some(name => name.includes(item.name))
      )
    }

    const nameMap = buildNameMap(geoJson)
    const data = distribution.map(item => ({
      name: nameMap[item.name] || item.name,
      value: item.count,
    }))
    const topRegions = [...data]
      .sort((a, b) => b.value - a.value)
      .slice(0, 5)
      .map(item => ({ name: item.name, count: item.value }))
    emit('update-top-regions', topRegions)

    const values = data.map(item => item.value).sort((a, b) => a - b)
    const p90 = values[Math.floor(values.length * 0.9)] || 10
    const maxVal = Math.max(...values, 10)
    const visualMax = maxVal > p90 * 2 ? p90 * 1.5 : maxVal
    cachedMapData = { ...cachedMapData, data, max: visualMax, geoJson, mapName }

    myMap.setOption({
      visualMap: { max: visualMax },
      series: [{
        data,
        animationDurationUpdate: 480,
        animationEasingUpdate: 'cubicOut',
      }],
    })
  } catch (error) {
    console.error('Map distribution refresh failed', error)
  }
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
    nextTick(() => { void refreshDistribution() })
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
.immersive-map { z-index: 3; }
.map-glass {
  border: 1px solid rgba(var(--theme-rgb), 0.22);
  background: rgba(7, 17, 31, 0.82);
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.28), inset 0 1px rgba(255, 255, 255, 0.04);
}
.map-control {
  padding: 8px;
  border: 1px solid rgba(var(--theme-rgb), 0.2);
  border-radius: 10px;
  color: #a9bed1;
  background: rgba(7, 17, 31, 0.84);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.24);
  backdrop-filter: blur(14px);
  transition: color 180ms ease, border-color 180ms ease, background-color 180ms ease;
}
.map-control:hover {
  color: var(--theme-primary);
  border-color: rgba(var(--theme-rgb), 0.48);
  background: rgba(var(--theme-rgb), 0.1);
}
.animate-fade-in { animation: fadeIn 0.3s ease-in-out; }
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(5px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
