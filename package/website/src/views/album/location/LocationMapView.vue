<template>
  <div class="location-map-cockpit flex flex-col md:flex-row w-full h-full relative">
    <!-- 左侧地图区域（移动端撑满，抽屉浮于其上） -->
    <!-- min-h-0 让 flex-1 在移动端 flex-col 下正确分配高度（见 LocationPuzzleView 同名注释） -->
    <div class="map-stage flex-1 min-h-0 relative overflow-hidden md:h-full">
      <div class="map-grid" aria-hidden="true" />
      <div class="map-radar" aria-hidden="true"><span /><span /><span /></div>
      <MapContainer
        ref="mapContainerRef"
        :level="level"
        :view-mode="viewMode"
        :start-date="startDate"
        :end-date="endDate"
        :parent-region="parentRegion"
        :selected-region="selectedRegion"
        @change-level="(l, state) => emit('change-level', l, state)"
        @select-region="handleSelectRegion"
        @update-top-regions="(regions) => topRegions = regions"
      />

      <div v-if="timelineYears.length" class="journey-timeline hidden md:flex" aria-label="足迹年份时间轴">
        <button
          class="timeline-play focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          :title="isPlaying ? '暂停足迹巡游' : '播放足迹巡游'"
          @click="togglePlayback"
        >
          <Pause v-if="isPlaying" class="h-4 w-4" />
          <Play v-else class="h-4 w-4 fill-current" />
        </button>
        <div class="min-w-0 flex-1">
          <div class="timeline-rail">
            <button
              v-for="item in timelineYears"
              :key="item.year"
              class="timeline-node focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
              :class="{ active: selectedYear === item.year }"
              :style="{ '--node-weight': String(item.weight) }"
              :title="`${item.year} 年足迹`"
              @click="emit('select-year', selectedYear === item.year ? null : item.year)"
            >
              <span class="timeline-dot" />
              <span class="timeline-label">{{ item.year }}</span>
            </button>
          </div>
          <div class="timeline-summary">
            <span><CalendarDays class="h-3.5 w-3.5" /> {{ selectedYear ? `${selectedYear} 年足迹` : '全部旅行记忆' }}</span>
            <span>{{ selectedYear ? '正在回看该年地图' : `${timelineYears.length} 个足迹年份` }}</span>
            <button v-if="selectedYear" @click="emit('select-year', null)">查看全部</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 右侧信息面板：移动端为 fixed 底部抽屉（peek/expand），桌面端为侧栏 -->
    <div
      class="location-insight-panel fixed md:static inset-x-0 bottom-[calc(var(--ts-tabbar-h)+env(safe-area-inset-bottom))] md:inset-auto z-30 md:z-auto flex flex-col h-auto md:h-full md:w-80 lg:w-96 backdrop-blur-xl border-t md:border-t-0 md:border-l rounded-t-2xl md:rounded-none shadow-2xl transition-[height] duration-300 ease-out"
      :class="{ '!transition-none': isDragging }"
      :style="isMobile ? { height: sheetHeight + 'px' } : {}"
    >
      <!-- 拖拽手柄区（仅移动端：点击切换 peek/expand，拖拽连续调高度） -->
      <div
        class="md:hidden shrink-0 h-8 flex items-center justify-center cursor-grab active:cursor-grabbing touch-none select-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
        @pointerdown="onHandlePointerDown"
        @click="onHandleClick"
        @keydown.enter="onHandleClick"
        @keydown.space.prevent="onHandleClick"
        role="button"
        tabindex="0"
        aria-label="拖动调整信息面板高度"
      >
        <div class="w-10 h-1.5 rounded-full bg-slate-300 dark:bg-slate-600" />
      </div>

      <el-scrollbar class="flex-1">
        <div class="p-4 md:p-5 space-y-6">
          
          <RegionDetailsPanel
            v-if="selectedRegion"
            :level="level"
            :selected-region="selectedRegion"
            :selected-region-count="selectedRegionCount"
            :region-photos="regionPhotos"
            :region-time-span="regionTimeSpan"
            :region-first-visit="regionFirstVisit"
            :region-tags="regionTags"
            :region-sub-level="regionSubLevel"
            :region-explored-count="regionExploredCount"
            :region-total-count="regionTotalCount"
            :region-top-sub-regions="regionTopSubRegions"
            :region-recent-visits="regionRecentVisits"
            @clear-selection="clearSelection"
            @click-location="(name, overrideLevel) => emit('click-location', name, overrideLevel)"
            @change-level="(l, state) => emit('change-level', l, state)"
          />

          <GlobalOverviewPanel
            v-else
            :global-stats="globalStats"
            :top-regions="topRegions"
            :recent-trips="recentTrips"
            :raw-timeline-data="rawTimelineData"
            @select-region="handleSelectRegion"
            @click-location="(name, overrideLevel) => emit('click-location', name, overrideLevel)"
          />

        </div>
      </el-scrollbar>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import { locationService } from '@/api/location'
import { albumService } from '@/api/album'
import type { LocationStatistics, TimelineNode } from '@/types/location'
import type { AlbumImage } from '@/types/album'
import { mapPhotoToImage } from '@/stores/photoStore'
import request from '@/utils/request'

import MapContainer from './components/MapContainer.vue'
import GlobalOverviewPanel from './components/GlobalOverviewPanel.vue'
import RegionDetailsPanel from './components/RegionDetailsPanel.vue'
import { CalendarDays, Pause, Play } from 'lucide-vue-next'

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
  selectedYear?: number | null
  availableYears?: number[]
}>()

const emit = defineEmits<{
  (e: 'click-location', name: string, level?: string): void
  (e: 'change-level', level: string, viewState: { zoom: number, center: number[], parentRegion?: string }): void
  (e: 'select-year', year: number | null): void
}>()

const mapContainerRef = ref<InstanceType<typeof MapContainer> | null>(null)

// 状态
const selectedRegion = ref<string | null>(null)
const selectedRegionCount = ref(0)
const regionPhotos = ref<AlbumImage[]>([])
const regionTimeSpan = ref<string>('')
const regionFirstVisit = ref<string>('')
const regionTags = ref<{name: string, count: number}[]>([])
const globalStats = ref<LocationStatistics | null>(null)
const topRegions = ref<{name: string, count: number}[]>([])
const recentTrips = ref<TimelineNode[]>([])
const rawTimelineData = ref<any[]>([])
const isPlaying = ref(false)
let playbackTimer: ReturnType<typeof setInterval> | null = null

const timelineYears = computed(() => {
  const locationYears = new Set(props.availableYears || [])
  const totals = new Map<number, number>()
  rawTimelineData.value.forEach((item) => {
    const year = Number(item.year)
    if (!Number.isFinite(year) || !locationYears.has(year)) return
    totals.set(year, (totals.get(year) || 0) + Number(item.count || 0))
  })
  locationYears.forEach(year => {
    if (!totals.has(year)) totals.set(year, 0)
  })
  const max = Math.max(...totals.values(), 1)
  return [...totals.entries()]
    .sort(([a], [b]) => a - b)
    .map(([year, count]) => ({ year, count, weight: 0.45 + (count / max) * 0.55 }))
})

const stopPlayback = () => {
  isPlaying.value = false
  if (playbackTimer) clearInterval(playbackTimer)
  playbackTimer = null
}

const togglePlayback = () => {
  if (isPlaying.value) {
    stopPlayback()
    return
  }
  if (!timelineYears.value.length) return
  isPlaying.value = true
  let index = Math.max(timelineYears.value.findIndex(item => item.year === props.selectedYear), -1)
  const advance = () => {
    index = (index + 1) % timelineYears.value.length
    emit('select-year', timelineYears.value[index].year)
  }
  advance()
  playbackTimer = setInterval(advance, 1800)
}

const regionPhotoCache = new Map<string, { photos: AlbumImage[], count: number, timeSpan: string, firstVisit: string, tags: { name: string, count: number }[] }>()
const regionSubDataCache = new Map<string, { subLevel: string, exploredCount: number, totalCount: number, topSubRegions: { name: string, count: number }[], recentVisits: TimelineNode[] }>()

const regionSubLevel = ref<string>('')
const regionExploredCount = ref(0)
const regionTotalCount = ref(0)
const regionTopSubRegions = ref<{ name: string, count: number }[]>([])
const regionRecentVisits = ref<TimelineNode[]>([])

// 获取全局统计数据
const fetchGlobalData = async () => {
  try {
    globalStats.value = await locationService.getStatistics()
    
    // 获取最近足迹
    const trips = await locationService.getTimelineNodes(0, 3)
    if (trips && trips.nodes) {
      recentTrips.value = trips.nodes
    }

    // 获取时间轴数据
    const timelineData = await albumService.getTimelineStats()
    if (timelineData && timelineData.timeline) {
      rawTimelineData.value = timelineData.timeline
    }
  } catch (e) {
    console.error('Failed to fetch global stats', e)
  }
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

const handleSelectRegion = async (name: string, count: number) => {
  if (!name) {
    clearSelection()
    return
  }
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
  if (mapContainerRef.value) {
    mapContainerRef.value.clearSelection()
  }
  selectedRegion.value = null
  regionPhotos.value = []
  regionSubLevel.value = ''
  regionExploredCount.value = 0
  regionTotalCount.value = 0
  regionTopSubRegions.value = []
  regionRecentVisits.value = []
}

/* ----------------------- 移动端底部抽屉：peek / expand ----------------------- */
// 桌面端为侧栏（md:static md:h-full），sheetHeight 仅移动端生效（内联高度门控 isMobile）。
const PEEK_H = 208                                   // 收起态：露手柄 + 标题 + 探索进度卡
const expandedH = () => Math.min(                    // 展开态：~70vh，但至少留 header + 120px 地图可点
  Math.round(window.innerHeight * 0.7),
  window.innerHeight - 240
)
const sheetHeight = ref(PEEK_H)
const isDragging = ref(false)
let dragMoved = false
let dragOrigin = { startY: 0, startH: 0 }

const clampSheetH = (h: number) => Math.max(PEEK_H, Math.min(h, expandedH()))

const onHandlePointerDown = (e: PointerEvent) => {
  if (e.button !== 0) return
  dragOrigin = { startY: e.clientY, startH: sheetHeight.value }
  isDragging.value = true
  dragMoved = false
  window.addEventListener('pointermove', onHandlePointerMove)
  window.addEventListener('pointerup', onHandlePointerUp)
}

const onHandlePointerMove = (e: PointerEvent) => {
  if (!isDragging.value) return
  const dy = e.clientY - dragOrigin.startY
  if (Math.abs(dy) > 3) dragMoved = true
  // 上拖 dy<0 → 高度增大（抽屉向上展开）
  sheetHeight.value = clampSheetH(dragOrigin.startH - dy)
}

const onHandlePointerUp = () => {
  isDragging.value = false
  window.removeEventListener('pointermove', onHandlePointerMove)
  window.removeEventListener('pointerup', onHandlePointerUp)
  // 释放后按中点 snap 到最近档位
  const mid = (PEEK_H + expandedH()) / 2
  sheetHeight.value = sheetHeight.value > mid ? expandedH() : PEEK_H
}

const onHandleClick = () => {
  // 拖动产生的位移不触发切换
  if (dragMoved) return
  sheetHeight.value = sheetHeight.value > PEEK_H + 1 ? PEEK_H : expandedH()
}

// 移动端判定（沿用 MainLayout 的 ref + resize 监听模式，仓内无响应式 isMobile 组合式）
const isMobile = ref(false)
const updateIsMobile = () => { isMobile.value = window.innerWidth < 768 }

const onWindowResize = () => {
  updateIsMobile()
  if (isMobile.value) sheetHeight.value = clampSheetH(sheetHeight.value)
}

// 选中区块自动展开、清除自动收起（桌面端 sheetHeight 被 md:h-full 忽略，写入无害）
watch(selectedRegion, (v) => {
  if (isMobile.value) sheetHeight.value = v ? expandedH() : PEEK_H
})

onMounted(() => {
  updateIsMobile()
  window.addEventListener('resize', onWindowResize)
  fetchGlobalData()
})

onUnmounted(() => {
  stopPlayback()
  window.removeEventListener('resize', onWindowResize)
  window.removeEventListener('pointermove', onHandlePointerMove)
  window.removeEventListener('pointerup', onHandlePointerUp)
})

</script>

<style scoped>
.location-map-cockpit {
  color: #dcecff;
  background: #07111f;
}

.map-stage {
  background:
    radial-gradient(circle at 48% 44%, rgba(var(--theme-rgb), 0.12), transparent 36%),
    linear-gradient(145deg, #08182b 0%, #07111f 58%, #050c17 100%);
}

.map-grid {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.3;
  background-image:
    linear-gradient(rgba(var(--theme-rgb), 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(var(--theme-rgb), 0.08) 1px, transparent 1px);
  background-size: 64px 64px;
  mask-image: radial-gradient(circle at center, #000 0%, transparent 76%);
}

.map-radar {
  position: absolute;
  left: 42%;
  top: 46%;
  width: 130px;
  height: 130px;
  transform: translate(-50%, -50%);
  pointer-events: none;
  z-index: 2;
}

.map-radar span {
  position: absolute;
  inset: 50%;
  border: 1px solid rgba(var(--theme-rgb), 0.65);
  border-radius: 999px;
  animation: radar-wave 3.6s ease-out infinite;
  box-shadow: 0 0 18px rgba(var(--theme-rgb), 0.18);
}

.map-radar span:nth-child(2) { animation-delay: 1.2s; }
.map-radar span:nth-child(3) { animation-delay: 2.4s; }

.location-insight-panel {
  border-color: rgba(var(--theme-rgb), 0.2);
  background: linear-gradient(180deg, rgba(10, 25, 43, 0.96), rgba(5, 14, 26, 0.98));
  box-shadow: -18px 0 46px rgba(0, 0, 0, 0.3), inset 1px 0 rgba(255, 255, 255, 0.025);
}

.location-insight-panel :deep(.text-gray-900),
.location-insight-panel :deep(.text-gray-800),
.location-insight-panel :deep(.text-gray-700) { color: #dcecff !important; }
.location-insight-panel :deep(.text-gray-600),
.location-insight-panel :deep(.text-gray-500),
.location-insight-panel :deep(.text-gray-400) { color: #7891aa !important; }
.location-insight-panel :deep(.bg-white),
.location-insight-panel :deep(.bg-gray-50),
.location-insight-panel :deep(.bg-gray-100) { background-color: rgba(13, 31, 51, 0.7) !important; }
.location-insight-panel :deep(.border-gray-100),
.location-insight-panel :deep(.border-gray-200),
.location-insight-panel :deep(.border-gray-300) { border-color: rgba(var(--theme-rgb), 0.16) !important; }

.journey-timeline {
  position: absolute;
  z-index: 8;
  left: 24px;
  right: 24px;
  bottom: 20px;
  align-items: center;
  gap: 18px;
  min-height: 96px;
  padding: 15px 18px;
  border: 1px solid rgba(var(--theme-rgb), 0.2);
  border-radius: 16px;
  background: rgba(7, 17, 31, 0.84);
  box-shadow: 0 16px 50px rgba(0, 0, 0, 0.32), inset 0 1px rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(18px);
}

.timeline-play {
  display: grid;
  width: 42px;
  height: 42px;
  flex: 0 0 auto;
  place-items: center;
  border: 1px solid rgba(var(--theme-rgb), 0.5);
  border-radius: 999px;
  color: var(--theme-primary);
  background: rgba(var(--theme-rgb), 0.12);
  box-shadow: 0 0 24px rgba(var(--theme-rgb), 0.18);
}

.timeline-rail {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 32px;
}

.timeline-rail::before {
  content: '';
  position: absolute;
  left: 1%;
  right: 1%;
  top: 12px;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(var(--theme-rgb), 0.65), transparent);
}

.timeline-node {
  position: relative;
  display: flex;
  min-width: 30px;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  color: #7690aa;
  background: transparent;
}

.timeline-dot {
  z-index: 1;
  width: calc(7px + 5px * var(--node-weight));
  height: calc(7px + 5px * var(--node-weight));
  border: 2px solid #0b172a;
  border-radius: 999px;
  background: #5b7894;
}

.timeline-node:hover,
.timeline-node.active { color: #e5f5ff; }
.timeline-node:hover .timeline-dot,
.timeline-node.active .timeline-dot {
  background: var(--theme-primary);
  box-shadow: 0 0 0 4px rgba(var(--theme-rgb), 0.14), 0 0 16px rgba(var(--theme-rgb), 0.75);
}

.timeline-label { font-size: 10px; }
.timeline-summary {
  display: flex;
  gap: 14px;
  color: #7690aa;
  font-size: 11px;
}
.timeline-summary span:first-child { display: flex; align-items: center; gap: 5px; color: #b9cee2; }
.timeline-summary button { color: var(--theme-primary); }

@keyframes radar-wave {
  0% { inset: 50%; opacity: 0.9; }
  100% { inset: 0; opacity: 0; }
}

@media (prefers-reduced-motion: reduce) {
  .map-radar span { animation: none; opacity: 0.2; inset: 15%; }
}
</style>
