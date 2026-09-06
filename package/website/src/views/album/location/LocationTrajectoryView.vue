<template>
  <div class="trajectory-cockpit relative flex h-full w-full flex-col overflow-hidden md:flex-row">
    <section class="trajectory-map-stage relative order-1 h-full min-h-0 flex-1 md:order-2">
      <div id="trajectory-map" class="h-full w-full overflow-hidden" />
      <div class="map-vignette pointer-events-none absolute inset-0" aria-hidden="true" />

      <div v-if="timelineNodes.length" class="journey-hud hidden md:block">
        <div class="hud-kicker">{{ selectedJourney ? 'SELECTED JOURNEY' : 'ALL JOURNEYS' }}</div>
        <div class="mt-1 text-base font-semibold text-white">{{ selectedJourney?.title || '全部足迹总览' }}</div>
        <div class="mt-1 flex items-center gap-3 text-xs text-[#7891aa]">
          <template v-if="selectedJourney">
            <span>{{ selectedJourney.dateRange }}</span>
            <span>{{ selectedJourney.nodes.length }} 个停留点</span>
            <span>{{ selectedJourney.photoCount }} 张照片</span>
            <span class="route-mode-badge">{{ routeModeLabel }}</span>
          </template>
          <template v-else>
            <span>{{ journeyGroups.length }} 段旅程</span>
            <span>{{ timelineNodes.length }} 个地点节点</span>
            <span>点击左侧旅程查看 GPS 细节</span>
          </template>
        </div>
      </div>

      <div v-if="selectedJourney && (!isMobile || !showMobileList)" class="playback-dock">
        <button
          class="play-button focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          :title="isPlaying ? '暂停旅行回放' : '播放旅行回放'"
          @click="togglePlayback"
        >
          <Pause v-if="isPlaying" class="h-4 w-4" />
          <Play v-else class="h-4 w-4 fill-current" />
        </button>
        <div class="min-w-0 flex-1">
          <div class="flex items-center justify-between text-[11px] text-[#8ca4ba]">
            <span>{{ playbackLabel }}</span>
            <span>{{ playbackIndex }}/{{ selectedJourney.nodes.length }}</span>
          </div>
          <div class="playback-track mt-2">
            <div :style="{ width: `${playbackProgress}%` }" />
          </div>
        </div>
        <button class="speed-button focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none" @click="cycleSpeed">{{ playbackSpeed }}×</button>
      </div>

      <div v-if="loading || detailLoading" class="loading-chip">
        <LoaderCircle class="h-4 w-4 animate-spin text-primary-500" />
        {{ detailLoading ? '正在加载 GPS 精细轨迹' : '正在整理旅行足迹' }}
      </div>
    </section>

    <aside
      :class="[
        'journey-panel z-20 flex flex-col border-t transition-all duration-300 md:order-1 md:h-full md:w-[352px] md:border-r md:border-t-0',
        isMobile ? 'journey-panel-mobile absolute inset-x-0 max-h-[62vh] rounded-t-2xl' : ''
      ]"
    >
      <button
        v-if="isMobile"
        class="flex w-full justify-center py-3 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
        aria-label="展开或收起旅程列表"
        @click="toggleMobileList"
      >
        <span class="h-1 w-11 rounded-full bg-[#587087]" />
      </button>

      <div v-show="!isMobile || showMobileList" class="custom-scrollbar flex-1 overflow-y-auto px-4 pb-5 pt-1 md:px-5 md:pt-24">
        <header class="mb-5">
          <div class="panel-kicker">JOURNEY ARCHIVE</div>
          <div class="mt-1 flex items-end justify-between">
            <div>
              <h2 class="text-lg font-bold text-white">旅行轨迹</h2>
              <p class="mt-1 text-xs text-[#7891aa]">按连续旅行时间自动整理</p>
            </div>
            <div class="text-right">
              <div class="text-lg font-semibold text-primary-500">{{ journeyGroups.length }}</div>
              <div class="text-[10px] text-[#617b93]">段旅程</div>
            </div>
          </div>
        </header>

        <div v-if="!journeyGroups.length && !loading" class="flex flex-col items-center justify-center py-16 text-[#7891aa]">
          <Map class="mb-3 h-10 w-10 opacity-50" />
          <p class="text-sm">暂无轨迹数据</p>
        </div>

        <div v-else class="space-y-3">
          <button
            class="overview-card focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
            :class="{ active: !selectedJourneyKey }"
            @click="selectOverview"
          >
            <span class="overview-icon"><Map class="h-4 w-4" /></span>
            <span class="min-w-0 flex-1">
              <span class="block text-sm font-semibold text-[#e4f2ff]">全部足迹总览</span>
              <span class="mt-1 block text-[11px] text-[#7891aa]">汇聚所有地点与历史轨迹</span>
            </span>
            <ChevronRight class="h-4 w-4 text-primary-500" />
          </button>

          <article
            v-for="journey in journeyGroups"
            :key="journey.key"
            class="journey-card"
            :class="{ active: journey.key === selectedJourneyKey }"
          >
            <button
              class="w-full rounded-xl p-3 text-left focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none"
              @click="selectJourney(journey.key)"
            >
              <div class="flex items-start gap-3">
                <img v-if="journey.coverId" :src="getThumbnailUrl(journey.coverId)" class="h-14 w-14 shrink-0 rounded-xl object-cover" loading="lazy" />
                <div v-else class="grid h-14 w-14 shrink-0 place-items-center rounded-xl bg-[#132b42] text-primary-500"><Route class="h-5 w-5" /></div>
                <div class="min-w-0 flex-1">
                  <div class="flex items-start justify-between gap-2">
                    <h3 class="truncate text-sm font-semibold text-[#e4f2ff]">{{ journey.title }}</h3>
                    <span class="journey-count">{{ journey.photoCount }}</span>
                  </div>
                  <div class="mt-1 text-[11px] text-[#7891aa]">{{ journey.dateRange }}</div>
                  <div class="mt-2 flex items-center gap-1 overflow-hidden text-[11px] text-[#9fb5c8]">
                    <template v-for="(location, index) in journey.locations.slice(0, 3)" :key="location">
                      <ChevronRight v-if="index" class="h-3 w-3 shrink-0 text-primary-500" />
                      <span class="truncate">{{ location }}</span>
                    </template>
                  </div>
                </div>
              </div>
            </button>

            <div v-if="journey.key === selectedJourneyKey" class="journey-stops">
              <button
                v-for="(node, index) in journey.nodes"
                :key="`${node.startDate}-${node.locationName}`"
                class="stop-row focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
                :class="{ current: isPlaying && index === playbackIndex - 1 }"
                @click="panToNode(node)"
              >
                <span class="stop-index">{{ index + 1 }}</span>
                <span class="min-w-0 flex-1">
                  <span class="block truncate text-xs text-[#c7d9e9]">{{ node.locationName }}</span>
                  <span class="block text-[10px] text-[#617b93]">{{ formatNodeDate(node) }}</span>
                </span>
                <span class="text-[10px] text-[#7891aa]">{{ node.photoCount }} 张</span>
              </button>
            </div>
          </article>
        </div>
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, computed, nextTick } from 'vue'
import { ChevronRight, LoaderCircle, Map, Pause, Play, Route } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { locationService } from '@/api/location'
import type { TimelineNode, TrajectoryPoint } from '@/types/location'
import { getTiandituTileTemplate, loadMapScript } from '@/utils/mapLoader'
import { thumbnailUrl } from '@/utils/mediaUrl'
import { ElMessage } from 'element-plus'
import { injectTheme } from '@/composables/useTheme'

// Declare T globally
declare const T: any

const props = defineProps<{
  startDate?: string
  endDate?: string
  level: string,
  viewMode: string
}>()

const loading = ref(false)
const limit = 100

const router = useRouter()
const { currentTheme } = injectTheme()
const timelineNodes = ref<TimelineNode[]>([])
const map = ref<any>(null)
const currentApiKey = ref('')
const isMobile = computed(() => window.innerWidth <= 768)
const showMobileList = ref(!isMobile.value)
const selectedJourneyKey = ref('')
const detailPoints = ref<TrajectoryPoint[]>([])
const detailLoading = ref(false)
const isPlaying = ref(false)
const playbackIndex = ref(0)
const playbackSpeed = ref(1)
let playbackTimer: ReturnType<typeof setInterval> | null = null
let detailRequestId = 0

interface JourneyGroup {
  key: string
  title: string
  dateRange: string
  nodes: TimelineNode[]
  locations: string[]
  photoCount: number
  coverId?: string
}

const toggleMobileList = () => {
  showMobileList.value = !showMobileList.value
}

// Format date helper
const formatDate = (dateStr: string) => {
  const date = new Date(dateStr)
  const months = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']
  
  return {
    full: `${date.getFullYear()}年${months[date.getMonth()]}${date.getDate()}日`,
    short: `${months[date.getMonth()]}${date.getDate()}日`
  }
}

const formatNodeDate = (node: TimelineNode) => {
  if (node.startDate === node.endDate) return formatDate(node.startDate).full
  return `${formatDate(node.startDate).full} — ${formatDate(node.endDate).short}`
}

const nodeStartTime = (node: TimelineNode) => new Date(node.startTime || `${node.startDate}T00:00:00`).getTime()
const nodeEndTime = (node: TimelineNode) => new Date(node.endTime || `${node.endDate}T23:59:59`).getTime()

const journeyGroups = computed<JourneyGroup[]>(() => {
  const nodes = [...timelineNodes.value]
    .filter(node => node.lat != null && node.lng != null)
    .sort((a, b) => nodeStartTime(a) - nodeStartTime(b))

  const groups: TimelineNode[][] = []
  const maxGap = 7 * 24 * 60 * 60 * 1000
  const maxJourneySpan = 21 * 24 * 60 * 60 * 1000
  nodes.forEach((node) => {
    const current = groups.at(-1)
    if (!current) {
      groups.push([node])
      return
    }
    const previous = current.at(-1)!
    const gap = nodeStartTime(node) - nodeEndTime(previous)
    const journeySpan = nodeEndTime(node) - nodeStartTime(current[0])
    // 地点时间段可能横跨数月；限制整段旅程的跨度，避免常驻城市把相邻旅行串成长链。
    if (gap > maxGap || journeySpan > maxJourneySpan) groups.push([node])
    else current.push(node)
  })

  return groups.reverse().map((group, index) => {
    const first = group[0]
    const last = group.at(-1)!
    const locations = [...new Set(group.map(node => node.locationName))]
    const title = locations.length === 1
      ? locations[0]
      : `${locations[0]} → ${locations.at(-1)}`
    const start = formatDate(first.startDate)
    const end = formatDate(last.endDate)
    const dateRange = first.startDate === last.endDate
      ? start.full
      : `${start.full} — ${end.full}`
    return {
      key: `${first.startDate}-${last.endDate}-${index}`,
      title,
      dateRange,
      nodes: group,
      locations,
      photoCount: group.reduce((sum, node) => sum + node.photoCount, 0),
      coverId: last.coverId || first.coverId,
    }
  })
})

const selectedJourney = computed(() =>
  journeyGroups.value.find(journey => journey.key === selectedJourneyKey.value)
)

const overviewNodes = computed(() => [...timelineNodes.value].sort((a, b) => nodeStartTime(a) - nodeStartTime(b)))

const gpsRouteNodes = computed<TimelineNode[]>(() => detailPoints.value.map(point => ({
  type: 'gps',
  startDate: point.capturedAt.slice(0, 10),
  endDate: (point.endAt || point.capturedAt).slice(0, 10),
  startTime: point.capturedAt,
  endTime: point.endAt || point.capturedAt,
  locationName: point.locationName,
  level: point.level,
  lat: point.lat,
  lng: point.lng,
  photoCount: point.photoCount,
  coverId: point.coverId,
})))

const haversineKm = (a: TimelineNode, b: TimelineNode) => {
  const toRad = (value: number) => value * Math.PI / 180
  const lat1 = toRad(a.lat || 0)
  const lat2 = toRad(b.lat || 0)
  const dLat = lat2 - lat1
  const dLng = toRad((b.lng || 0) - (a.lng || 0))
  const value = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2
  return 6371.0088 * 2 * Math.asin(Math.sqrt(value))
}

const gpsExtentKm = computed(() => {
  if (gpsRouteNodes.value.length < 2) return 0
  const minLat = Math.min(...gpsRouteNodes.value.map(node => node.lat!))
  const maxLat = Math.max(...gpsRouteNodes.value.map(node => node.lat!))
  const minLng = Math.min(...gpsRouteNodes.value.map(node => node.lng!))
  const maxLng = Math.max(...gpsRouteNodes.value.map(node => node.lng!))
  return haversineKm(
    { lat: minLat, lng: minLng } as TimelineNode,
    { lat: maxLat, lng: maxLng } as TimelineNode,
  )
})

const isLocalJourney = computed(() => Boolean(selectedJourney.value) && (
  selectedJourney.value!.locations.length === 1 || gpsExtentKm.value <= 80
))

const routeModeLabel = computed(() => {
  if (detailLoading.value) return '正在加载 GPS'
  if (!detailPoints.value.length) return '行政区轨迹'
  return isLocalJourney.value ? 'GPS 精细轨迹' : '跨区域混合轨迹'
})

const visibleJourneyNodes = computed(() => {
  const nodes = selectedJourney.value?.nodes || []
  return isPlaying.value ? nodes.slice(0, playbackIndex.value) : nodes
})

const playbackProgress = computed(() => {
  const total = selectedJourney.value?.nodes.length || 0
  return total ? Math.round((playbackIndex.value / total) * 100) : 0
})

const playbackLabel = computed(() => {
  if (!selectedJourney.value) return '暂无旅程'
  if (!isPlaying.value) return '完整路线'
  const current = selectedJourney.value.nodes[Math.max(0, playbackIndex.value - 1)]
  return current ? `${formatDate(current.startDate).short} · ${current.locationName}` : '准备出发'
})

const stopPlayback = (showFullRoute = true) => {
  isPlaying.value = false
  if (playbackTimer) clearInterval(playbackTimer)
  playbackTimer = null
  playbackIndex.value = showFullRoute ? (selectedJourney.value?.nodes.length || 0) : 0
}

const startPlaybackTimer = () => {
  if (playbackTimer) clearInterval(playbackTimer)
  const interval = Math.max(450, 1500 / playbackSpeed.value)
  playbackTimer = setInterval(() => {
    const total = selectedJourney.value?.nodes.length || 0
    if (playbackIndex.value >= total) {
      stopPlayback(true)
      drawTrajectory()
      return
    }
    playbackIndex.value += 1
    drawTrajectory()
    const current = selectedJourney.value?.nodes[playbackIndex.value - 1]
    if (current?.lat != null && current.lng != null) {
      map.value?.panTo(new T.LngLat(current.lng, current.lat))
    }
  }, interval)
}

const togglePlayback = () => {
  if (!selectedJourney.value) return
  if (isPlaying.value) {
    stopPlayback(true)
    drawTrajectory()
    return
  }
  playbackIndex.value = 1
  isPlaying.value = true
  drawTrajectory()
  startPlaybackTimer()
}

const cycleSpeed = () => {
  playbackSpeed.value = playbackSpeed.value === 1 ? 1.5 : playbackSpeed.value === 1.5 ? 2 : 1
  if (isPlaying.value) startPlaybackTimer()
}

const selectJourney = (key: string) => {
  stopPlayback(false)
  selectedJourneyKey.value = key
  detailPoints.value = []
  if (isMobile.value) showMobileList.value = false
  nextTick(() => {
    playbackIndex.value = selectedJourney.value?.nodes.length || 0
    drawTrajectory(true)
    void fetchJourneyDetail()
  })
}

const selectOverview = () => {
  detailRequestId += 1
  detailLoading.value = false
  detailPoints.value = []
  selectedJourneyKey.value = ''
  stopPlayback(false)
  if (isMobile.value) showMobileList.value = false
  nextTick(() => drawTrajectory(true))
}

const fetchJourneyDetail = async () => {
  const journey = selectedJourney.value
  if (!journey) return
  const requestId = ++detailRequestId
  detailLoading.value = true
  try {
    const response = await locationService.getTrajectory(journey.nodes[0].startDate, journey.nodes.at(-1)!.endDate)
    if (requestId !== detailRequestId) return
    detailPoints.value = response.points
    nextTick(() => drawTrajectory(true))
  } catch (error) {
    if (requestId === detailRequestId) console.warn('Failed to load GPS trajectory detail', error)
  } finally {
    if (requestId === detailRequestId) detailLoading.value = false
  }
}

const getThumbnailUrl = (photoId: string) => {
  // return `https://picsum.photos/seed/${photoId}/400/600`
  return thumbnailUrl(photoId)
}

const waitForOverlayApi = async () => {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    if (typeof T?.Label === 'function' && typeof T?.Polyline === 'function') return
    await new Promise(resolve => window.setTimeout(resolve, 100))
  }
  throw new Error('天地图覆盖物组件加载超时')
}

// Map initialization
const initMap = () => {
  if (map.value) return
  
  const vecTileUrl = getTiandituTileTemplate('vec_w', currentApiKey.value)
  const cvaTileUrl = getTiandituTileTemplate('cva_w', currentApiKey.value)
  
  // Capacitor 通过所选 TrailSnap 服务器的 nginx 代理加载瓦片。
  if (vecTileUrl && cvaTileUrl) {
    map.value = new T.Map('trajectory-map', { layers: [] })
    const vecLayer = new T.TileLayer(vecTileUrl, { minZoom: 1, maxZoom: 18 });
    const cvaLayer = new T.TileLayer(cvaTileUrl, { minZoom: 1, maxZoom: 18 });
    map.value.addOverLay(vecLayer);
    map.value.addOverLay(cvaLayer);
  } else {
    map.value = new T.Map('trajectory-map')
  }

  map.value.centerAndZoom(new T.LngLat(104.195, 35.861), 4)
  map.value.enableScrollWheelZoom()
}

// Data fetching
const fetchTimelineData = async () => {
  if (loading.value) return
  loading.value = true
  try {
    const incoming: TimelineNode[] = []
    let offset = 0
    let hasMore = true
    while (hasMore) {
      const res = await locationService.getTimelineNodes(offset, limit, props.startDate, props.endDate, props.level)
      const newNodes = res.nodes
      incoming.push(...newNodes)
      hasMore = newNodes.length === limit
      offset += limit
    }
    // 新数据完整到达后再一次性替换，筛选时不会先清空地图。
    timelineNodes.value = incoming
    selectedJourneyKey.value = ''
    detailPoints.value = []
    playbackIndex.value = 0
    nextTick(() => {
      drawTrajectory(true)
    })
  } catch (e) {
    console.error('Failed to fetch timeline nodes', e)
  } finally {
    loading.value = false
  }
}

// Draw markers and lines on the map
const drawTrajectory = (fitViewport = false) => {
  if (!map.value) return
  map.value.clearOverLays()

  const points: any[] = []
  const summaryNodes = selectedJourney.value ? visibleJourneyNodes.value : overviewNodes.value
  const detailedRoute = selectedJourney.value && !isPlaying.value ? gpsRouteNodes.value : []
  const routeNodes = detailedRoute.length > 1 ? detailedRoute : summaryNodes
  const representativeGpsNodes = (() => {
    if (!isLocalJourney.value || detailedRoute.length <= 18) return detailedRoute
    const result: TimelineNode[] = []
    const lastIndex = detailedRoute.length - 1
    for (let index = 0; index < 18; index += 1) {
      result.push(detailedRoute[Math.round(index * lastIndex / 17)])
    }
    return [...new Set(result)]
  })()
  // 区域内旅行显示有限数量的 GPS 照片节点；跨区域旅行保留行政区停留点。
  const markerNodes = isLocalJourney.value && representativeGpsNodes.length
    ? representativeGpsNodes
    : summaryNodes

  markerNodes.forEach((node, index) => {
     const lat = (node as any).lat;
     const lng = (node as any).lng;
     if (!lat || !lng) return;

     const point = new T.LngLat(lng, lat);
     const photoCount = (node as any).photoCount || 1;
     const size = isLocalJourney.value
       ? Math.min(42, Math.max(28, 24 + Math.sqrt(photoCount) * 2.2))
       : Math.min(52, Math.max(34, 27 + Math.sqrt(photoCount) * 2.8));
     const coverId = (node as any).coverId;
     const coverUrl = coverId ? getThumbnailUrl(coverId) : '';
     
     const dateLabel = node.startDate === node.endDate ? formatDate(node.startDate).short : formatDate(node.startDate).short + '-' + formatDate(node.endDate).short;

     const accent = currentTheme.value.primary
     const html = `
       <div style="position:relative;width:${size}px;height:${size}px;cursor:pointer;filter:drop-shadow(0 8px 14px rgba(0,0,0,.38));">
         <div style="width:100%;height:100%;overflow:hidden;border:2px solid ${accent};border-radius:999px;background:#10243a;box-shadow:0 0 0 4px rgba(7,17,31,.72),0 0 22px ${accent}55;">
           <img src="${coverUrl}" style="width:100%;height:100%;object-fit:cover;" onerror="this.style.display='none'" />
         </div>
         <div style="position:absolute;left:-5px;top:-6px;display:grid;width:20px;height:20px;place-items:center;border:2px solid #07111f;border-radius:999px;background:${accent};color:white;font:700 10px/1 sans-serif;">${index + 1}</div>
         <div style="position:absolute;right:-7px;bottom:-5px;min-width:22px;height:18px;padding:0 5px;border:1px solid ${accent}88;border-radius:9px;background:rgba(7,17,31,.92);color:#dcecff;font:600 10px/16px sans-serif;text-align:center;">${photoCount}</div>
         <div style="position:absolute;left:50%;bottom:-29px;transform:translateX(-50%);padding:3px 7px;border:1px solid ${accent}55;border-radius:7px;background:rgba(7,17,31,.9);color:#dcecff;font:600 10px/1.2 sans-serif;white-space:nowrap;">${dateLabel} · ${node.locationName}</div>
       </div>`;

     const label = new T.Label({
       text: html,
       position: point,
       offset: new T.Point(-size/2, -size/2)
     })
     label.setBackgroundColor("transparent")
     label.setBorderLine(0)
     
     label.addEventListener('click', () => {
         goToLocationDetail(node)
     })
     
     map.value.addOverLay(label)
  })

  routeNodes.forEach((node) => {
    if (node.lat == null || node.lng == null) return
    points.push(new T.LngLat(node.lng, node.lat))
  })

  // 一次只绘制选中旅程，避免跨年份节点被强行连接成蜘蛛网。
  if (points.length > 1) {
     const line = new T.Polyline(points, {
       color: currentTheme.value.primary,
       weight: 4,
       opacity: 0.9,
       lineStyle: "solid"
     });
     map.value.addOverLay(line)
     if (fitViewport) map.value.setViewport(points)
  } else if (points.length === 1) {
     if (fitViewport) map.value.centerAndZoom(points[0], 10)
  }
}

const panToNode = (node: TimelineNode) => {
  const lat = (node as any).lat;
  const lng = (node as any).lng;
  if (lat && lng && map.value) {
     map.value.centerAndZoom(new T.LngLat(lng, lat), 12)
     if (isMobile.value) {
         showMobileList.value = false;
     }
  }
}

const goToLocationDetail = (node: TimelineNode) => {
  router.push({
    name: 'LocationDetail',
    params: { name: node.locationName },
    query: { 
      level: node.level || 'city', 
      startDate: node.startDate,
      endDate: node.endDate
    }
  })
}

watch([() => props.startDate, () => props.endDate, () => props.level], () => {
  if (props.viewMode === 'trajectory' && props.level !== 'photo-map') {
      stopPlayback(false)
      detailRequestId += 1
      detailPoints.value = []
      void fetchTimelineData()
      nextTick(() => {
        initMap()
      })
    }
})

// 主题色变化时重绘轨迹（仅折线颜色变化，重绘所有 overlay 较重但保证一致性）
watch(() => currentTheme.value.primary, () => {
  if (map.value && timelineNodes.value.length > 0) {
    drawTrajectory()
  }
})

onMounted(async () => {
  try {
    currentApiKey.value = await loadMapScript()
    // 天地图主脚本就绪后，Label 等覆盖物组件仍可能异步注册。
    await waitForOverlayApi()
    if (props.viewMode === 'trajectory' && props.level !== 'photo-map') {
      await nextTick()
      initMap()
      await fetchTimelineData()
    }
  } catch (e: any) {
    ElMessage.error('地图加载失败: ' + (e.message || e))
  }
})

onUnmounted(() => {
  stopPlayback(false)
})

</script>

<style scoped>
.trajectory-cockpit { color: #dcecff; background: #07111f; }
.trajectory-map-stage { isolation: isolate; background: #07111f; }
#trajectory-map { background: #0a1727; }
#trajectory-map :deep(.tdt-tile-pane img) {
  filter: invert(0.88) hue-rotate(175deg) saturate(0.65) brightness(0.66) contrast(1.14);
}
.map-vignette {
  z-index: 3;
  background:
    radial-gradient(circle at 58% 46%, transparent 28%, rgba(4, 11, 20, 0.14) 64%, rgba(4, 11, 20, 0.58) 100%),
    linear-gradient(90deg, rgba(7, 17, 31, 0.46), transparent 18%);
  box-shadow: inset 0 0 90px rgba(0, 0, 0, 0.25);
}
.journey-panel {
  z-index: 1000;
  border-color: rgba(var(--theme-rgb), 0.18);
  background: linear-gradient(180deg, rgba(8, 21, 37, 0.98), rgba(5, 14, 26, 0.99));
  box-shadow: 16px 0 48px rgba(0, 0, 0, 0.24), inset -1px 0 rgba(255, 255, 255, 0.025);
}
.panel-kicker,
.hud-kicker {
  color: var(--theme-primary);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.16em;
}
.journey-card {
  overflow: hidden;
  border: 1px solid rgba(var(--theme-rgb), 0.12);
  border-radius: 15px;
  background: rgba(13, 31, 51, 0.64);
  transition: border-color 180ms ease, background-color 180ms ease, box-shadow 180ms ease;
}
.overview-card {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 11px;
  padding: 12px;
  border: 1px solid rgba(var(--theme-rgb), 0.14);
  border-radius: 15px;
  background: rgba(13, 31, 51, 0.58);
  text-align: left;
  transition: border-color 180ms ease, background-color 180ms ease, box-shadow 180ms ease;
}
.overview-card:hover,
.overview-card.active {
  border-color: rgba(var(--theme-rgb), 0.5);
  background: linear-gradient(135deg, rgba(var(--theme-rgb), 0.16), rgba(13, 31, 51, 0.82));
  box-shadow: 0 0 24px rgba(var(--theme-rgb), 0.08);
}
.overview-icon {
  display: grid;
  width: 36px;
  height: 36px;
  flex: 0 0 auto;
  place-items: center;
  border: 1px solid rgba(var(--theme-rgb), 0.34);
  border-radius: 11px;
  color: var(--theme-primary);
  background: rgba(var(--theme-rgb), 0.1);
}
.journey-card:hover { border-color: rgba(var(--theme-rgb), 0.34); }
.journey-card.active {
  border-color: rgba(var(--theme-rgb), 0.58);
  background: linear-gradient(135deg, rgba(var(--theme-rgb), 0.14), rgba(13, 31, 51, 0.82));
  box-shadow: 0 0 26px rgba(var(--theme-rgb), 0.08), inset 0 1px rgba(255, 255, 255, 0.035);
}
.journey-count {
  min-width: 24px;
  padding: 2px 6px;
  border: 1px solid rgba(var(--theme-rgb), 0.3);
  border-radius: 999px;
  color: var(--theme-primary);
  background: rgba(var(--theme-rgb), 0.1);
  font-size: 10px;
  text-align: center;
}
.journey-stops {
  margin: 0 12px 12px 30px;
  padding-left: 12px;
  border-left: 1px solid rgba(var(--theme-rgb), 0.24);
}
.stop-row {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 9px;
  padding: 7px 5px;
  border-radius: 8px;
  text-align: left;
  transition: background-color 160ms ease;
}
.stop-row:hover,
.stop-row.current { background: rgba(var(--theme-rgb), 0.09); }
.stop-index {
  display: grid;
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
  place-items: center;
  border: 1px solid rgba(var(--theme-rgb), 0.34);
  border-radius: 999px;
  color: var(--theme-primary);
  font-size: 9px;
}
.journey-hud {
  position: absolute;
  z-index: 1000;
  left: 24px;
  top: 84px;
  min-width: 280px;
  padding: 14px 16px;
  border: 1px solid rgba(var(--theme-rgb), 0.2);
  border-radius: 14px;
  background: rgba(7, 17, 31, 0.82);
  box-shadow: 0 14px 42px rgba(0, 0, 0, 0.3), inset 0 1px rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(16px);
}
.route-mode-badge {
  padding: 2px 7px;
  border: 1px solid rgba(var(--theme-rgb), 0.28);
  border-radius: 999px;
  color: var(--theme-primary);
  background: rgba(var(--theme-rgb), 0.09);
}
.playback-dock {
  position: absolute;
  z-index: 1000;
  left: 24px;
  right: 24px;
  bottom: 22px;
  display: flex;
  align-items: center;
  gap: 13px;
  max-width: 620px;
  min-height: 66px;
  padding: 12px 14px;
  border: 1px solid rgba(var(--theme-rgb), 0.24);
  border-radius: 15px;
  background: rgba(7, 17, 31, 0.86);
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.34), inset 0 1px rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(18px);
}
.play-button {
  display: grid;
  width: 38px;
  height: 38px;
  flex: 0 0 auto;
  place-items: center;
  border: 1px solid rgba(var(--theme-rgb), 0.5);
  border-radius: 999px;
  color: var(--theme-primary);
  background: rgba(var(--theme-rgb), 0.12);
  box-shadow: 0 0 20px rgba(var(--theme-rgb), 0.16);
}
.playback-track {
  height: 3px;
  overflow: hidden;
  border-radius: 999px;
  background: #1b3248;
}
.playback-track div {
  height: 100%;
  border-radius: inherit;
  background: var(--theme-primary);
  box-shadow: 0 0 12px rgba(var(--theme-rgb), 0.7);
  transition: width 300ms ease;
}
.speed-button {
  min-width: 38px;
  padding: 5px 7px;
  border: 1px solid rgba(var(--theme-rgb), 0.2);
  border-radius: 8px;
  color: #a9bed1;
  background: rgba(var(--theme-rgb), 0.08);
  font-size: 11px;
}
.loading-chip {
  position: absolute;
  z-index: 1001;
  left: 50%;
  top: 88px;
  display: flex;
  transform: translateX(-50%);
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid rgba(var(--theme-rgb), 0.2);
  border-radius: 999px;
  color: #a9bed1;
  background: rgba(7, 17, 31, 0.86);
  font-size: 11px;
  backdrop-filter: blur(14px);
}
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: rgba(var(--theme-rgb), 0.28);
  border-radius: 20px;
}

@media (max-width: 767px) {
  .journey-panel-mobile {
    bottom: 0;
    box-shadow: 0 -18px 48px rgba(0, 0, 0, 0.36);
  }
  .playback-dock {
    left: 12px;
    right: 12px;
    bottom: 48px;
  }
  .loading-chip { top: 70px; }
}
</style>
