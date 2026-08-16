<template>
  <div class="relative w-full h-full flex flex-col md:flex-row bg-white dark:bg-gray-900">
    <!-- Map Area -->
    <div class="flex-1 relative w-full h-full md:h-auto z-10 order-1 md:order-2">
      <div id="trajectory-map" class="w-full h-full z-10 overflow-hidden"></div>
      
      <!-- Loading Overlay -->
      <div v-if="loading" class="absolute inset-0 z-50 flex items-center justify-center bg-white/50 backdrop-blur-sm">
        <div class="w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full animate-spin"></div>
      </div>
    </div>

    <!-- Timeline List Area -->
    <div 
      :class="[
        'bg-white dark:bg-gray-900 border-t md:border-t-0 md:border-r border-gray-200 dark:border-gray-800 transition-all duration-300 z-20 flex flex-col',
        isMobile ? 'absolute bottom-0 left-0 right-0 max-h-[50vh] rounded-t-2xl shadow-[0_-4px_20px_rgba(0,0,0,0.1)]' : 'w-80 h-full order-2 md:order-1'
      ]"
    >
      <div v-if="isMobile" class="w-full flex justify-center py-2 cursor-pointer" @click="toggleMobileList">
        <div class="w-12 h-1.5 bg-gray-300 dark:bg-gray-600 rounded-full"></div>
      </div>

      <div v-show="!isMobile || showMobileList" class="flex-1 overflow-y-auto custom-scrollbar p-4 md:pt-24" @scroll="handleScroll">
        <div v-if="!timelineNodes.length && !loading && !loadingMore" class="flex flex-col items-center justify-center py-10 text-gray-500">
          <Map class="w-10 h-10 mb-2 text-gray-300 dark:text-gray-600" />
          <p class="text-sm">暂无轨迹数据</p>
        </div>
        
        <div v-else class="space-y-4">
          <div v-for="(node, index) in timelineNodes" :key="index" class="relative pl-8 py-2">
            <!-- Timeline vertical line -->
            <div v-if="index !== timelineNodes.length - 1" class="absolute left-[11px] top-1/2 w-0.5 h-full bg-gray-200 dark:bg-gray-700"></div>
            
            <!-- Dot -->
            <div class="absolute left-0 top-1/2 -translate-y-1/2 w-[24px] h-[24px] rounded-full bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center border-2 border-white dark:border-gray-900 z-10 cursor-pointer" @click="panToNode(node)">
              <div class="w-2 h-2 rounded-full bg-primary-500"></div>
            </div>
            
            <div class="cursor-pointer group flex items-center justify-between w-full" @click="panToNode(node)">
              <div class="flex-1 pr-4">
                <div class="text-sm font-bold text-gray-900 dark:text-white mb-1" v-if="node.startDate === node.endDate">{{ formatDate(node.startDate).full }}</div>
                <div class="text-sm font-bold text-gray-900 dark:text-white mb-1" v-else>{{ formatDate(node.startDate).short }} - {{ formatDate(node.endDate).short }}</div>
                <div class="text-xs text-primary-600 dark:text-primary-400 font-medium">{{ node.locationName }}</div>
              </div>
              
              <!-- Photos preview -->
              <div v-if="node.coverId" class="flex-shrink-0">
                <div 
                  class="w-16 h-16 rounded-md overflow-hidden bg-gray-100 dark:bg-gray-800 relative cursor-pointer group/more"
                  @click="goToLocationDetail(node)"
                >
                  <img :src="getThumbnailUrl(node.coverId)" class="w-full h-full object-cover transition-transform duration-300 group-hover/more:scale-105" loading="lazy" />
                  <div 
                    v-if="node.photoCount > 1"
                    class="absolute inset-0 bg-black/40 opacity-0 group-hover/more:opacity-100 transition-opacity flex items-center justify-center"
                  >
                    <span class="text-white font-medium text-xs">+{{ node.photoCount - 1 }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
          
          <!-- Loading More Indicator -->
          <div v-if="loadingMore" class="flex justify-center items-center py-4">
            <div class="animate-spin rounded-full h-6 w-6 border-4 border-primary-500 border-t-transparent"></div>
          </div>
          <div v-if="!hasMore && timelineNodes.length > 0" class="text-center text-gray-400 py-4 text-xs">
            没有更多数据了
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, computed, nextTick } from 'vue'
import { Map, Plane } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { locationService } from '@/api/location'
import type { TimelineNode } from '@/types/location'
import type { Photo } from '@/types/album'
import { loadMapScript } from '@/utils/mapLoader'
import { isNativeApp } from '@/config/server'
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

const emit = defineEmits<{
  (e: 'click-photo', photo: Photo, contextPhotos: Photo[]): void
}>()

const loading = ref(false)
const loadingMore = ref(false)
const hasMore = ref(true)
const skip = ref(0)
const limit = 100

const router = useRouter()
const { currentTheme } = injectTheme()
const timelineNodes = ref<TimelineNode[]>([])
const map = ref<any>(null)
const currentApiKey = ref('')
const isMobile = computed(() => window.innerWidth <= 768)
const showMobileList = ref(true)

let animationId: number | null = null
let currentArrow: any = null

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

const getThumbnailUrl = (photoId: string) => {
  // return `https://picsum.photos/seed/${photoId}/400/600`
  return `/api/medias/${photoId}/thumbnail`
}

// Map initialization
const initMap = () => {
  if (map.value) return
  
  const useTileProxy = import.meta.env.PROD && !isNativeApp()
  
  // 原生壳没有 Web 生产部署中的 /tianditu-tiles nginx 代理。
  if (useTileProxy) {
    map.value = new T.Map('trajectory-map', { layers: [] })
    const tk = currentApiKey.value;
    const vecLayer = new T.TileLayer(`/tianditu-tiles/DataServer?T=vec_w&x={x}&y={y}&l={z}&tk=${tk}`, { minZoom: 1, maxZoom: 18 });
    const cvaLayer = new T.TileLayer(`/tianditu-tiles/DataServer?T=cva_w&x={x}&y={y}&l={z}&tk=${tk}`, { minZoom: 1, maxZoom: 18 });
    map.value.addOverLay(vecLayer);
    map.value.addOverLay(cvaLayer);
  } else {
    map.value = new T.Map('trajectory-map')
  }

  map.value.centerAndZoom(new T.LngLat(104.195, 35.861), 4)
  map.value.enableScrollWheelZoom()
}

// Data fetching
const fetchTimelineData = async (isLoadMore = false) => {
  if (loading.value || loadingMore.value || (!hasMore.value && isLoadMore)) return

  if (isLoadMore) {
    loadingMore.value = true
  } else {
    loading.value = true
    skip.value = 0
    hasMore.value = true
  }
  timelineNodes.value = []
  try {
    while (hasMore.value) {
      const res = await locationService.getTimelineNodes(skip.value, limit, props.startDate, props.endDate, props.level)
      const newNodes = res.nodes
      if (newNodes.length < limit) {
        hasMore.value = false
      }
      timelineNodes.value.push(...newNodes)
      skip.value += limit
    }
    nextTick(() => {
       drawTrajectory()
    })
  } catch (e) {
    console.error('Failed to fetch timeline nodes', e)
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

const handleScroll = (e: Event) => {
  const target = e.target as HTMLElement
  if (target.scrollHeight - target.scrollTop <= target.clientHeight + 200) {
    fetchTimelineData(true)
  }
}

// Draw markers and lines on the map
const drawTrajectory = () => {
  if (!map.value) return
  map.value.clearOverLays()

  const points: any[] = []
  
  timelineNodes.value.forEach((node, index) => {
     const lat = (node as any).lat;
     const lng = (node as any).lng;
     if (!lat || !lng) return;

     const point = new T.LngLat(lng, lat);
     points.push(point);

     const photoCount = (node as any).photoCount || 1;
     // Adjust marker size based on photo count (min 30, max 60)
     const size = Math.min(60, Math.max(30, 20 + Math.sqrt(photoCount) * 5));
     const coverId = (node as any).coverId;
     const coverUrl = coverId ? getThumbnailUrl(coverId) : '';
     
     const dateLabel = node.startDate === node.endDate ? formatDate(node.startDate).short : formatDate(node.startDate).short + '-' + formatDate(node.endDate).short;

     const html = `
       <div class="trajectory-marker group relative cursor-pointer" style="width: ${size}px; height: ${size}px; z-index: ${index};">
         <div class="w-full h-full rounded-full border-[3px] border-white shadow-lg overflow-hidden bg-gray-200 transition-transform duration-300 group-hover:scale-110 group-hover:border-primary-500 group-hover:z-50 group-hover:shadow-xl">
           <img src="${coverUrl}" class="w-full h-full object-cover" onerror="this.style.display='none'" />
         </div>
         <div class="absolute -bottom-6 left-1/2 -translate-x-1/2 whitespace-nowrap bg-white/90 backdrop-blur-sm px-2 py-0.5 rounded shadow-sm text-xs font-bold text-gray-800 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
           ${dateLabel} · ${node.locationName}
         </div>
         ${photoCount > 1 ? `<div style="position: absolute; top: -6px; right: -6px; background-color: #ef4444; color: white; font-size: 11px; font-weight: 600; padding: 0 5px; height: 18px; line-height: 16px; border-radius: 9px; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.1); min-width: 18px; text-align: center;">${photoCount}</div>` : ''}
       </div>
     `;

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

  // Draw lines and directional arrows
  if (points.length > 1) {
     const line = new T.Polyline(points, {
       color: currentTheme.value.primary, // 跟随主题色
       weight: 3,
       opacity: 0.8,
       lineStyle: "dashed"
     });
     map.value.addOverLay(line)
     // Fit view to points
     map.value.setViewport(points)
  } else if (points.length === 1) {
     map.value.panTo(points[0], 10)
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
      fetchTimelineData()
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
    if (props.viewMode === 'trajectory' && props.level !== 'photo-map') {
      nextTick(() => {
        initMap()
      })
      await fetchTimelineData()
    }
  } catch (e: any) {
    ElMessage.error('地图加载失败: ' + (e.message || e))
  }
})

onUnmounted(() => {
  if (animationId) {
    cancelAnimationFrame(animationId)
  }
})

</script>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: rgba(156, 163, 175, 0.5);
  border-radius: 20px;
}
.dark .custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: rgba(75, 85, 99, 0.5);
}

.no-scrollbar::-webkit-scrollbar {
  display: none;
}
.no-scrollbar {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
</style>
