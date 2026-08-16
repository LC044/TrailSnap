<template>
  <div class="relative w-full h-full">
    <div id="tianditu-map" class="w-full h-full z-10 overflow-hidden"></div>
    
    <!-- Loading Overlay -->
    <div v-if="loading" class="absolute inset-0 z-50 flex items-center justify-center bg-white/50 backdrop-blur-sm">
      <div class="w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full animate-spin"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
// @ts-ignore  缺少 supercluster 类型声明，暂时忽略
import Supercluster from 'supercluster'
import { locationService } from '@/api/location'
import { useRouter } from 'vue-router'
import { useLocationStore } from '@/stores/locationStore'
import { loadMapScript } from '@/utils/mapLoader'
import { isNativeApp } from '@/config/server'
import { storeToRefs } from 'pinia'
import { ElMessageBox, ElMessage } from 'element-plus'

// Declare T globally
declare const T: any

const map = ref<any>(null)
const currentApiKey = ref('')
const loading = ref(false)
const index = new Supercluster({
  radius: 60,
  maxZoom: 18
})
const sceneCluster = new Supercluster({
  radius: 80,
  maxZoom: 16
})
const router = useRouter()
const locationStore = useLocationStore()
const { level } = storeToRefs(locationStore)

const props = defineProps<{
  filterStatus?: 'all' | 'checked' | 'unchecked',
  startDate?: string,
  endDate?: string
}>()

onMounted(async () => {
  try {
    currentApiKey.value = await loadMapScript()
    initMap()
    await loadContent()
  } catch (e: any) {
    if (e.code === 'MAP_KEY_MISSING') {
      ElMessageBox.confirm(
        '查看地图照片需要配置地图 API Key。是否立即前往设置？',
        '缺少配置',
        {
          confirmButtonText: '去设置',
          cancelButtonText: '取消',
          type: 'warning',
          center: true
        }
      ).then(() => {
        router.push('/settings#basic')
      }).catch(() => {
        // User cancelled
      })
    } else {
      ElMessage.error('地图加载失败: ' + e.message)
    }
  }
})

watch(level, async (newVal) => {
  if (!map.value) return
  map.value.clearOverLays()
  await loadContent()
})

watch(() => props.filterStatus, async () => {
  if (level.value === 'scene') {
    await loadContent()
  }
})

watch([() => props.startDate, () => props.endDate], async () => {
  await loadContent()
})

const initMap = () => {
  if (map.value) return
  
  const useTileProxy = import.meta.env.PROD && !isNativeApp()
  
  // Web 生产部署通过 nginx 代理并缓存瓦片。Tauri/Capacitor 没有该代理，
  // 必须让天地图 SDK 直接加载官方图层。
  if (useTileProxy) {
    // 初始化地图时不添加默认图层
    map.value = new T.Map('tianditu-map', {
      layers: []
    })
    
    // 添加代理图层
    const tk = currentApiKey.value;
    const vecLayer = new T.TileLayer(`/tianditu-tiles/DataServer?T=vec_w&x={x}&y={y}&l={z}&tk=${tk}`, {
      minZoom: 1,
      maxZoom: 18
    });
    const cvaLayer = new T.TileLayer(`/tianditu-tiles/DataServer?T=cva_w&x={x}&y={y}&l={z}&tk=${tk}`, {
      minZoom: 1,
      maxZoom: 18
    });
    
    map.value.addOverLay(vecLayer);
    map.value.addOverLay(cvaLayer);
  } else {
    // 开发环境下直接使用天地图默认图层
    map.value = new T.Map('tianditu-map')
  }

  // Load saved position
  let center = new T.LngLat(104.195, 35.861)
  let zoom = 4
  
  try {
    const savedState = localStorage.getItem('trailsnap_map_state')
    if (savedState) {
      const { lng, lat, z } = JSON.parse(savedState)
      if (lng && lat && z) {
        center = new T.LngLat(lng, lat)
        zoom = z
      }
    }
  } catch (e) {
    console.warn('Failed to load map state', e)
  }

  map.value.centerAndZoom(center, zoom)
  map.value.enableScrollWheelZoom()
  
  // Save position on change
  const saveState = () => {
    const center = map.value.getCenter()
    const zoom = map.value.getZoom()
    localStorage.setItem('trailsnap_map_state', JSON.stringify({
      lng: center.getLng(),
      lat: center.getLat(),
      z: zoom
    }))
  }
  
  map.value.addEventListener('moveend', saveState)
  map.value.addEventListener('zoomend', saveState)
}

const scenesData = ref<any[]>([])
const scenesWithPhotos = ref<any[]>([])

const loadContent = async () => {
  // Remove listeners first to avoid conflicts
  if (map.value) {
      map.value.removeEventListener('moveend', updateClusters)
      map.value.removeEventListener('zoomend', updateClusters)
      map.value.removeEventListener('moveend', renderScenes)
      map.value.removeEventListener('zoomend', renderScenes)
  }

  if (level.value === 'scene') {
    if (map.value) {
        map.value.addEventListener('moveend', renderScenes)
        map.value.addEventListener('zoomend', renderScenes)
    }
    await loadScenes()
  } else {
    // Add listeners for clusters
    if (map.value) {
        map.value.addEventListener('moveend', updateClusters)
        map.value.addEventListener('zoomend', updateClusters)
    }
    await loadData()
  }
}

const loadScenes = async () => {
  loading.value = true
  try {
    let allScenes = await locationService.getScenesList(0, 10000, props.startDate, props.endDate)
    
    // Apply filter
    if (props.filterStatus === 'checked') {
      scenesData.value = allScenes.filter(s => s.photo_count && s.photo_count > 0)
    } else if (props.filterStatus === 'unchecked') {
      scenesData.value = allScenes.filter(s => !s.photo_count || s.photo_count === 0)
    } else {
      scenesData.value = allScenes
    }
    
    if (scenesData.value.length === 0) {
      map.value.clearOverLays()
      // ElMessage.info('暂无景区数据')
      return
    }

    // Split data
    scenesWithPhotos.value = scenesData.value.filter(s => s.photo_count && s.photo_count > 0)
    const scenesWithoutPhotos = scenesData.value.filter(s => !s.photo_count || s.photo_count === 0)

    // Load non-photo scenes into Supercluster
    const points = scenesWithoutPhotos.map(s => {
        let lng = s.longitude
        let lat = s.latitude
        // Use polygon center if point not available (fallback)
        if ((!lng || !lat) && s.polygon && s.polygon.length > 0) {
            lng = s.polygon[0][1]
            lat = s.polygon[0][0]
        }
        return {
            type: 'Feature' as const,
            properties: { 
                cluster: false, 
                sceneData: s
            },
            geometry: {
                type: 'Point' as const,
                coordinates: [lng, lat]
            }
        }
    }).filter(p => p.geometry.coordinates[0] && p.geometry.coordinates[1])

    sceneCluster.load(points)

    renderScenes()
    
    // Fit view to scenes if any
    // if (scenesData.value.length > 0) {
    //    const first = scenesData.value[0]
    //    if (first.latitude && first.longitude) {
    //        map.value.panTo(new T.LngLat(first.longitude, first.latitude))
    //    }
    // }

  } catch (e) {
    console.error('Failed to load scenes:', e)
  } finally {
    loading.value = false
  }
}

const renderScenes = () => {
  if (!map.value) return
  map.value.clearOverLays()

  const zoom = map.value.getZoom()
  const showPolygon = zoom >= 12
  const bounds = map.value.getBounds()
  const sw = bounds.getSouthWest()
  const ne = bounds.getNorthEast()
  const bbox = [sw.getLng(), sw.getLat(), ne.getLng(), ne.getLat()] as [number, number, number, number]

  // --- Helper Functions ---

  const createMarkerLabel = (position: any, type: 'blue' | 'orange' | 'cluster', text?: string, count?: number) => {
      let html = ''
      let offset = new T.Point(0, 0)
      
      if (type === 'blue') {
          // Blue marker for scenes with photos
          html = `<div class="w-5 h-5 bg-blue-500 rounded-full border-2 border-white shadow-lg cursor-pointer transform hover:scale-110 transition-transform"></div>`
          offset = new T.Point(-10, -10)
      } else if (type === 'orange') {
          // Orange marker for scenes without photos
          html = `<div class="w-3 h-3 bg-orange-500 rounded-full border border-white shadow cursor-pointer hover:bg-orange-600 transition-colors"></div>`
          offset = new T.Point(-6, -6)
      } else if (type === 'cluster') {
          // Cluster marker
          const size = count && count > 100 ? 40 : 30
          html = `<div class="flex items-center justify-center bg-orange-400/90 text-white rounded-full border-2 border-white shadow-md cursor-pointer hover:bg-orange-500 transition-colors" style="width: ${size}px; height: ${size}px; font-size: 12px; font-weight: bold;">${count}</div>`
          offset = new T.Point(-size/2, -size/2)
      }

      const label = new T.Label({
          text: html,
          position: position,
          offset: offset
      })
      label.setBackgroundColor("transparent")
      label.setBorderLine(0)
      return label
  }

  const createSimpleNameLabel = (position: any, name: string, isBlue: boolean) => {
    const label = new T.Label({
      text: `<div class="px-2 py-0.5 bg-white/90 rounded shadow-sm text-xs font-bold ${isBlue ? 'text-blue-600' : 'text-orange-600'} whitespace-nowrap border border-white/50">${name}</div>`,
      position: position,
      offset: new T.Point(-name.length * 4, isBlue ? 12 : 10)
    })
    label.setBackgroundColor("transparent")
    label.setBorderLine(0)
    return label
  }

  const createCoverCard = (position: any, scene: any, isBlue: boolean) => {
      const coverUrl = scene.cover ? `/api/medias/${scene.cover.id}/thumbnail` : null;
      if (!coverUrl) return null;
      
      const label = new T.Label({
        text: `
          <div class="flex flex-col items-center bg-white/95 backdrop-blur-sm rounded-lg shadow-xl border border-white/50 overflow-hidden">
            <div class="w-32 h-20 overflow-hidden bg-gray-100">
              <img src="${coverUrl}" class="w-full h-full object-cover" />
            </div>
          </div>
        `,
        position: position,
        offset: new T.Point(-64, -110)
      })
      label.setBackgroundColor("transparent")
      label.setBorderLine(0)
      return label
  }

  const drawPolygon = (scene: any, isBlue: boolean) => {
      if (scene.polygon && scene.polygon.length > 0) {
        const points = scene.polygon.map((p: any) => new T.LngLat(p[1], p[0]))
        const polygon = new T.Polygon(points, {
          color: isBlue ? "#3b82f6" : "#f97316", 
          weight: 3, 
          opacity: 0.8, 
          fillColor: isBlue ? "#3b82f6" : "#f97316", 
          fillOpacity: 0.2
        })
        map.value.addOverLay(polygon)
        return polygon
      }
      return null
  }

  // --- 1. Render Scenes WITH Photos (Always Visible Name) ---
  scenesWithPhotos.value.forEach((scene: any) => {
    // Determine center
    let centerPt = null
    if (scene.latitude && scene.longitude) {
        centerPt = new T.LngLat(scene.longitude, scene.latitude)
    } else if (scene.polygon && scene.polygon.length > 0) {
        centerPt = new T.LngLat(scene.polygon[0][1], scene.polygon[0][0])
    }
    if (!centerPt) return

    const handleClick = () => goToScene(scene.name)

    // Draw Marker
    const marker = createMarkerLabel(centerPt, 'blue')
    marker.addEventListener('click', handleClick)
    map.value.addOverLay(marker)

    // Draw Simple Name Label (Always visible for photos)
    const nameLabel = createSimpleNameLabel(centerPt, scene.name, true)
    nameLabel.addEventListener('click', handleClick)
    map.value.addOverLay(nameLabel)
    
    // Draw Cover Card (Hover only)
    const coverCard = createCoverCard(centerPt, scene, true)
    
    const showCover = () => coverCard && map.value.addOverLay(coverCard)
    const hideCover = () => coverCard && map.value.removeOverLay(coverCard)

    marker.addEventListener('mouseover', showCover)
    marker.addEventListener('mouseout', hideCover)

    // Draw Polygon if zoomed in
    if (showPolygon) {
        const polygon = drawPolygon(scene, true)
        if (polygon) {
            polygon.addEventListener('click', handleClick)
            polygon.addEventListener('mouseover', showCover)
            polygon.addEventListener('mouseout', hideCover)
        }
    }
  })

  // --- 2. Render Scenes WITHOUT Photos (Clustered) ---
  const clusters = sceneCluster.getClusters(bbox, zoom)
  
  clusters.forEach((cluster: any) => {
    const [lng, lat] = cluster.geometry.coordinates
    const isCluster = cluster.properties.cluster
    const point = new T.LngLat(lng, lat)

    if (isCluster) {
        const count = cluster.properties.point_count
        const marker = createMarkerLabel(point, 'cluster', undefined, count)
        
        marker.addEventListener('click', () => {
             const expansionZoom = sceneCluster.getClusterExpansionZoom(cluster.id)
             map.value.setZoom(expansionZoom)
             map.value.panTo(point)
        })
        map.value.addOverLay(marker)
    } else {
        // Single Scene (No Photos)
        const scene = cluster.properties.sceneData
        
        const handleClick = () => goToScene(scene.name)

        // Draw Marker
        const marker = createMarkerLabel(point, 'orange')
        marker.addEventListener('click', handleClick)
        map.value.addOverLay(marker)

        // Name Label (Hover only for no photos)
        const nameLabel = createSimpleNameLabel(point, scene.name, false)
        nameLabel.addEventListener('click', handleClick)
        
        const showLabel = () => map.value.addOverLay(nameLabel)
        const hideLabel = () => map.value.removeOverLay(nameLabel)

        marker.addEventListener('mouseover', showLabel)
        marker.addEventListener('mouseout', hideLabel)

        // Draw Polygon if zoomed in
        if (showPolygon) {
            const polygon = drawPolygon(scene, false)
            if (polygon) {
                polygon.addEventListener('click', handleClick)
                polygon.addEventListener('mouseover', showLabel)
                polygon.addEventListener('mouseout', hideLabel)
            }
        }
    }
  })
}

const goToScene = (name: string) => {
  const query: any = { level: 'scene' }
  if (props.startDate) {
    query.startDate = props.startDate
    query.endDate = props.endDate
  }
  router.push({
    name: 'LocationDetail',
    params: { name: name },
    query
  })
}

const loadData = async () => {
  loading.value = true
  try {
    const rawMarkers = await locationService.getMapMarkers(props.startDate, props.endDate)
    // Convert to GeoJSON features
    const points = rawMarkers.map(m => ({
      type: 'Feature' as const,
      properties: { 
        cluster: false, 
        photoId: m.id,
        thumbnail: `/api/medias/${m.id}/thumbnail` 
      },
      geometry: {
        type: 'Point' as const,
        coordinates: [m.lng, m.lat]
      }
    }))
    
    if (points.length === 0) {
      console.warn('No photo markers found.')
    }

    index.load(points)
    
    // Slight delay to ensure map bounds are ready
    setTimeout(() => {
        updateClusters()
    }, 100)
    
  } catch (e) {
    console.error('Failed to load map data:', e)
  } finally {
    loading.value = false
  }
}

const updateClusters = () => {
  if (!map.value) return

  const bounds = map.value.getBounds()
  const sw = bounds.getSouthWest()
  const ne = bounds.getNorthEast()
  const zoom = map.value.getZoom()
  map.value.clearOverLays()

  const bbox = [sw.getLng(), sw.getLat(), ne.getLng(), ne.getLat()] as [number, number, number, number]

  const clusters = index.getClusters(bbox, zoom)

  clusters.forEach((cluster: any) => {
    const [lng, lat] = cluster.geometry.coordinates
    const isCluster = cluster.properties.cluster
    const count = cluster.properties.point_count || 1

    // Get cover photo
    let coverUrl = ''
    let photoId = ''
    if (isCluster) {
      // Get leaves to find a cover photo
      const leaves = index.getLeaves(cluster.id, 1)
      coverUrl = leaves[0].properties.thumbnail
      photoId = leaves[0].properties.photoId // Just one of them
    } else {
      coverUrl = cluster.properties.thumbnail
      photoId = cluster.properties.photoId
    }

    // Create custom marker using T.Label
    // We use a div with background image and inline styles to ensure rendering
    const iconHtml = `
      <div class="map-marker-cluster" style="position: relative; display: flex; flex-direction: column; align-items: center; justify-content: center; cursor: pointer; transition: transform 0.2s cubic-bezier(0.175, 0.885, 0.32, 1.275);">
        <div style="width: 44px; height: 44px; border-radius: 8px; border: 2px solid white; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15); overflow: hidden; background-color: #e5e7eb;">
          <img src="${coverUrl}" style="width: 100%; height: 100%; object-fit: cover; display: block;" onerror="this.parentElement.style.backgroundColor='#e5e7eb'; this.style.display='none';" />
        </div>
        ${count > 1 ? `<div style="position: absolute; top: -6px; right: -6px; background-color: #ef4444; color: white; font-size: 11px; font-weight: 600; padding: 0 5px; height: 18px; line-height: 16px; border-radius: 9px; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.1); min-width: 18px; text-align: center;">${count}</div>` : ''}
      </div>
    `
    
    const label = new T.Label({
      text: iconHtml,
      position: new T.LngLat(lng, lat),
      offset: new T.Point(-22, -22)
    })
    
    label.setBackgroundColor("transparent")
    label.setBorderLine(0)
    label.setTitle(count > 1 ? `${count} photos` : 'Photo')
    
    // Removed JS hover listeners to fix "label.getObject is not a function" error
    // Hover effect is now handled by CSS
    
    label.addEventListener('click', () => {
      if (isCluster) {
        // If it's a cluster, check zoom. 
        // Optimized: Open detail earlier (zoom > 16) to avoid excessive clicking
        const expansionZoom = index.getClusterExpansionZoom(cluster.id)
        
        openClusterDetail(cluster.id)
      } else {
        // Single photo
        openPhotoDetail(photoId)
      }
    })
    
    map.value.addOverLay(label)
  })
}

const openClusterDetail = (clusterId: number) => {
  // Get all leaves
  const leaves = index.getLeaves(clusterId, Infinity)
  const ids = leaves.map((l: any) => l.properties.photoId)
  
  // Store IDs in store and navigate
  locationStore.setMapSelection(ids)
  router.push({
    name: 'LocationDetail',
    params: { name: 'map_selection' },
    query: { title: '地图精选' }
  })
}

const openPhotoDetail = (photoId: string) => {
  locationStore.setMapSelection([photoId])
  router.push({
    name: 'LocationDetail',
    params: { name: 'map_selection' },
    query: { title: '地图照片' }
  })
}

onUnmounted(() => {
  if (map.value) {
    // map.value.destroy() // Tianditu might not have destroy, usually safe to leave
  }
})
</script>

<style>
/* Ensure label doesn't have default styles interfering */
.tdt-label {
  box-shadow: none !important;
}

.map-marker-cluster:hover {
  transform: scale(1.15);
  z-index: 9999;
}
</style>
