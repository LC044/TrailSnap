<template>
  <div class="footprint-globe" data-testid="footprint-globe" :data-ready="isReady" :data-mode="mode">
    <div ref="container" class="globe-canvas" aria-label="可拖动和缩放的足迹地图" />
    <div v-if="!isReady && !failure" class="globe-loading" role="status">
      <span class="loading-orbit" />
      <span>正在展开你的世界</span>
    </div>
    <div v-if="failure" class="globe-failure" role="alert">
      <i class="mgc_earth_line text-4xl" aria-hidden="true" />
      <p>{{ failure }}</p>
      <span>城市列表和照片仍可查看</span>
    </div>
    <div v-if="isReady" class="globe-hint" aria-hidden="true">{{ mode === '2d' ? '拖动平移 · 滚轮缩放' : '拖动旋转 · 滚轮缩放 · 右键倾斜' }}</div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type * as Cesium from 'cesium'
import 'cesium/Build/Cesium/Widgets/widgets.css'
import { settingsApi } from '@/api/settings'
import { toServerUrl } from '@/config/server'
import { injectTheme } from '@/composables/useTheme'
import { thumbnailUrl } from '@/utils/mediaUrl'
import { arcCoordinates, boundaryLines, validPosition, type ArcPosition, type BoundaryLine } from '@/utils/footprintScene'
import type { FootprintCity, FootprintRoute } from '@/types/footprint'

const props = withDefaults(defineProps<{
  cities: FootprintCity[]
  routes: FootprintRoute[]
  mode: '2d' | '3d' | 'globe'
  layers: { photos: boolean; routes: boolean; heatmap: boolean; boundaries: boolean; terrain: boolean }
  selectedCityId: string | null
  activeRouteIndex: number
  playing: boolean
  rotating: boolean
  playbackSpeed?: number
}>(), { cities: () => [], routes: () => [], playbackSpeed: 1 })
const emit = defineEmits<{
  'select-city': [id: string]
  ready: []
  error: [message: string]
  status: [message: string]
  'view-change': [bbox: string | null]
}>()

const container = ref<HTMLElement>()
const isReady = ref(false)
const failure = ref('')
const { currentTheme } = injectTheme()
let C: typeof import('@/utils/cesiumRuntime')
let viewer: Cesium.Viewer | undefined
let citySource: Cesium.CustomDataSource
let photoSource: Cesium.CustomDataSource
let routeSource: Cesium.CustomDataSource
let heatSource: Cesium.CustomDataSource
let borderSource: Cesium.CustomDataSource
let handler: Cesium.ScreenSpaceEventHandler | undefined
let resizeObserver: ResizeObserver | undefined
let worker: Worker | undefined
let disposed = false
let hidden = document.hidden
let routeGeneration = 0
let photoGeneration = 0
let borderGeneration = 0
let terrainGeneration = 0
let frame = 0
let previousFrame = 0
let animationProgress = 0
let cachedBorders: BoundaryLine[] | undefined
let terrain: Cesium.ArcGISTiledElevationTerrainProvider | undefined
let activeTrail: Cesium.Entity | undefined
let activeDot: Cesium.Entity | undefined
let routePaths: Cesium.Cartesian3[][] = []
let resizeTimer: ReturnType<typeof setTimeout> | undefined
let refreshTimer: ReturnType<typeof setTimeout> | undefined
let borderController: AbortController | undefined
let globeWheelListener: ((event: WheelEvent) => void) | undefined
const imageCache = new Map<string, HTMLCanvasElement>()
const pendingJobs = new Map<number, { resolve: (value: any) => void; reject: (error: Error) => void }>()
const cleanup: Array<() => void> = []
let nextJobId = 0
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')

function requestRender() { if (viewer && !viewer.isDestroyed()) viewer.scene.requestRender() }
function primary(alpha = 1) { return C.Color.fromCssColorString(currentTheme.value.primary).withAlpha(alpha) }
function gold(alpha = 1) { return C.Color.fromCssColorString('#ffc779').withAlpha(alpha) }
function isMobile() { return !!container.value && container.value.clientWidth < 700 }
function geographicPosition(city: FootprintCity, height = 1800) { return C.Cartesian3.fromDegrees(city.lng, city.lat, height) }

function syncRenderQuality() {
  if (!viewer || viewer.isDestroyed()) return
  // Cesium renders labels and billboards into the WebGL canvas. Capping mobile
  // devices at 1.25 made that canvas visibly softer than the surrounding DOM
  // on common 2.5x/3x phone displays. 2x keeps text crisp without the cost of
  // rendering the full native DPR on high-density screens.
  viewer.resolutionScale = Math.min(window.devicePixelRatio || 1, 2)
  viewer.scene.globe.maximumScreenSpaceError = isMobile() ? 2.5 : 2
}

async function processCoordinates(kind: 'routes' | 'boundaries', payload: any): Promise<any> {
  if (!worker) return kind === 'boundaries' ? boundaryLines(payload) : payload.routes.map((r: FootprintRoute) => arcCoordinates(r.from, r.to, payload.raised))
  const id = ++nextJobId
  return new Promise((resolve, reject) => {
    pendingJobs.set(id, { resolve, reject })
    // Vue props can contain proxies, which cannot be structured-cloned.
    worker!.postMessage({ id, kind, payload: JSON.parse(JSON.stringify(payload)) })
  }).catch(() => kind === 'boundaries' ? boundaryLines(payload) : payload.routes.map((r: FootprintRoute) => arcCoordinates(r.from, r.to, payload.raised)))
}

function glowImage(color: string, heat = false): HTMLCanvasElement {
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = 96
  const ctx = canvas.getContext('2d')!
  const gradient = ctx.createRadialGradient(48, 48, 0, 48, 48, 48)
  gradient.addColorStop(0, heat ? 'rgba(255,230,150,0.95)' : '#ffffff')
  gradient.addColorStop(heat ? 0.22 : 0.12, color)
  gradient.addColorStop(heat ? 0.6 : 0.3, `${color}77`)
  gradient.addColorStop(1, `${color}00`)
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, 96, 96)
  return canvas
}

function renderCities() {
  if (!viewer) return
  citySource.entities.suspendEvents()
  citySource.entities.removeAll()
  const glow = glowImage(currentTheme.value.primary)
  const selectedGlow = glowImage('#ffc779')
  const visibleCities = props.cities.filter(city => validPosition([city.lng, city.lat]))
  for (const city of visibleCities) {
    const selected = city.id === props.selectedCityId
    citySource.entities.add({
      id: `city:${city.id}`,
      name: city.name,
      position: geographicPosition(city),
      billboard: {
        image: selected ? selectedGlow : glow,
        width: selected ? 45 : 30, height: selected ? 45 : 30,
        scaleByDistance: new C.NearFarScalar(300000, 1.1, 18000000, 0.65),
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
      label: {
        text: city.name,
        font: `${selected ? '600' : '400'} ${isMobile() ? 11 : 13}px sans-serif`,
        fillColor: selected ? gold() : C.Color.WHITE,
        outlineColor: C.Color.fromCssColorString('#061420'),
        outlineWidth: 3, style: C.LabelStyle.FILL_AND_OUTLINE,
        pixelOffset: new C.Cartesian2(0, 18),
        distanceDisplayCondition: new C.DistanceDisplayCondition(0, selected ? 50000000 : 14000000),
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    })
  }
  citySource.entities.resumeEvents()
  renderHeatmap()
  void renderPhotos()
  requestRender()
}

function renderHeatmap() {
  if (!viewer) return
  heatSource.entities.removeAll()
  heatSource.show = props.layers.heatmap
  if (!props.layers.heatmap) return
  const max = Math.max(1, ...props.cities.map(city => city.photo_count))
  const texture = glowImage('#ff9b45', true)
  for (const city of props.cities) {
    if (!validPosition([city.lng, city.lat])) continue
    const weight = Math.log(1 + city.photo_count) / Math.log(1 + max)
    heatSource.entities.add({
      id: `heat:${city.id}`, position: geographicPosition(city, 1000),
      ellipse: {
        semiMajorAxis: 22000 + weight * 130000,
        semiMinorAxis: 22000 + weight * 130000,
        height: 1200,
        material: new C.ImageMaterialProperty({ image: texture, transparent: true, color: C.Color.WHITE.withAlpha(0.58) }),
      },
    })
  }
  requestRender()
}

async function photoCard(city: FootprintCity): Promise<HTMLCanvasElement | null> {
  if (!city.cover_id) return null
  const key = `${city.cover_id}:${city.name}:${currentTheme.value.primary}`
  if (imageCache.has(key)) return imageCache.get(key)!
  const image = new Image()
  image.crossOrigin = 'anonymous'
  const loaded = await new Promise<boolean>(resolve => {
    const timeout = window.setTimeout(() => { image.onload = image.onerror = null; image.src = ''; resolve(false) }, 8000)
    image.onload = () => { window.clearTimeout(timeout); resolve(true) }
    image.onerror = () => { window.clearTimeout(timeout); resolve(false) }
    image.src = thumbnailUrl(city.cover_id!)
  })
  if (!loaded || disposed) return null
  const canvas = document.createElement('canvas')
  canvas.width = 148; canvas.height = 182
  const ctx = canvas.getContext('2d')!
  ctx.fillStyle = currentTheme.value.primary
  ctx.beginPath(); ctx.roundRect(2, 2, 144, 168, 12); ctx.fill()
  ctx.save()
  ctx.beginPath(); ctx.roundRect(5, 5, 138, 162, 9); ctx.clip()
  ctx.fillStyle = '#081928'; ctx.fillRect(5, 5, 138, 162)
  const side = Math.min(image.width, image.height)
  ctx.drawImage(image, (image.width - side) / 2, (image.height - side) / 2, side, side, 5, 5, 138, 128)
  ctx.fillStyle = '#eaf5ff'; ctx.font = '500 21px sans-serif'; ctx.textAlign = 'center'
  ctx.fillText(city.name, 74, 157, 124)
  ctx.restore()
  ctx.beginPath(); ctx.moveTo(66, 169); ctx.lineTo(82, 169); ctx.lineTo(74, 182); ctx.closePath(); ctx.fillStyle = currentTheme.value.primary; ctx.fill()
  if (imageCache.size >= 32) imageCache.delete(imageCache.keys().next().value!)
  imageCache.set(key, canvas)
  return canvas
}

async function renderPhotos() {
  if (!viewer) return
  const generation = ++photoGeneration
  photoSource.entities.removeAll()
  photoSource.show = props.layers.photos
  if (!props.layers.photos) return
  const candidates = props.cities.filter(city => city.cover_id && validPosition([city.lng, city.lat]))
    .sort((a, b) => Number(b.id === props.selectedCityId) - Number(a.id === props.selectedCityId) || b.photo_count - a.photo_count)
  // Keep cards separated in screen space; cities always remain visible below.
  const positions: Cesium.Cartesian2[] = []
  const chosen: FootprintCity[] = []
  for (const city of candidates) {
    const world = geographicPosition(city)
    if (viewer.scene.mode === C.SceneMode.SCENE3D && !new C.Occluder(new C.BoundingSphere(C.Cartesian3.ZERO, C.Ellipsoid.WGS84.minimumRadius), viewer.camera.positionWC).isPointVisible(world)) continue
    const point = C.SceneTransforms.worldToWindowCoordinates(viewer.scene, world)
    if (!point || point.x < 0 || point.y < 70 || point.x > viewer.canvas.clientWidth || point.y > viewer.canvas.clientHeight) continue
    if (positions.some(other => C.Cartesian2.distance(point, other) < (isMobile() ? 115 : 125))) continue
    positions.push(point); chosen.push(city)
    if (chosen.length >= (isMobile() ? 4 : 9)) break
  }
  // Three image requests at a time avoids a burst against the thumbnail service.
  for (let i = 0; i < chosen.length; i += 3) {
    await Promise.all(chosen.slice(i, i + 3).map(async city => {
      const image = await photoCard(city)
      if (!image || disposed || !viewer || generation !== photoGeneration) return
      photoSource.entities.add({
        id: `photo:${city.id}`, position: geographicPosition(city, 2000),
        billboard: {
          image, width: isMobile() ? 53 : 64, height: isMobile() ? 65 : 79,
          verticalOrigin: C.VerticalOrigin.BOTTOM, pixelOffset: new C.Cartesian2(0, -20),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
          scaleByDistance: new C.NearFarScalar(200000, 1.1, 20000000, 0.8),
        },
      })
      requestRender()
    }))
    if (disposed || generation !== photoGeneration) return
  }
}

async function renderRoutes() {
  if (!viewer) return
  const generation = ++routeGeneration
  const routes = props.routes.slice(0, 800)
  const coordinates: ArcPosition[][] = await processCoordinates('routes', { routes, raised: props.mode !== '2d' }).catch(() => [])
  if (disposed || !viewer || generation !== routeGeneration) return
  routeSource.entities.suspendEvents()
  routeSource.entities.removeAll()
  routeSource.show = props.layers.routes
  activeTrail = activeDot = undefined
  routePaths = coordinates.map(arc => arc.map(point => C.Cartesian3.fromDegrees(...point)))
  routes.forEach((route, index) => {
    if (!routePaths[index]?.length) return
    routeSource.entities.add({
      id: `route:${index}`, name: `${route.from_name} → ${route.to_name}`,
      polyline: {
        positions: routePaths[index], width: 2,
        arcType: C.ArcType.NONE,
        material: new C.PolylineGlowMaterialProperty({ glowPower: 0.16, taperPower: 0.4, color: gold(0.7) }),
        depthFailMaterial: new C.PolylineGlowMaterialProperty({ glowPower: 0.1, color: gold(0.25) }),
      },
    })
  })
  activeDot = routeSource.entities.add({
    id: 'route-progress', show: false,
    point: { pixelSize: 7, color: C.Color.WHITE, outlineColor: gold(), outlineWidth: 4, disableDepthTestDistance: Number.POSITIVE_INFINITY },
  })
  activeTrail = routeSource.entities.add({
    id: 'route-trail', show: false,
    polyline: { positions: [], width: 4, arcType: C.ArcType.NONE, material: new C.PolylineGlowMaterialProperty({ color: gold(), glowPower: 0.25 }) },
  })
  routeSource.entities.resumeEvents()
  updateRouteSelection()
  requestRender()
}

function updateRouteSelection() {
  if (!viewer) return
  animationProgress = 0
  routeSource.entities.values.forEach(entity => {
    if (!entity.id.startsWith('route:')) return
    const index = Number(entity.id.slice(6))
    const selected = props.activeRouteIndex < 0 || index === props.activeRouteIndex
    if (entity.polyline) {
      entity.polyline.width = new C.ConstantProperty(selected ? 2.5 : 1.3)
      entity.polyline.material = new C.PolylineGlowMaterialProperty({ glowPower: selected ? 0.22 : 0.1, color: gold(selected ? 0.9 : 0.22) })
    }
  })
  const path = routePaths[props.activeRouteIndex]
  if (activeDot) {
    activeDot.show = !!path?.length && props.playing
    if (path?.length) activeDot.position = new C.ConstantPositionProperty(path[0])
  }
  if (activeTrail) activeTrail.show = false
  if (path?.length && props.playing) {
    const sphere = C.BoundingSphere.fromPoints(path)
    viewer.camera.flyToBoundingSphere(sphere, {
      duration: prefersReducedMotion.matches ? 0 : 1,
      offset: new C.HeadingPitchRange(0, props.mode === '2d' ? -Math.PI / 2 : C.Math.toRadians(-53), Math.max(450000, sphere.radius * 4)),
    })
  }
  syncAnimation()
  requestRender()
}

async function loadBoundaries() {
  if (!viewer) return
  const generation = ++borderGeneration
  borderSource.show = props.layers.boundaries
  if (!props.layers.boundaries) return
  try {
    if (!cachedBorders) {
      borderController?.abort()
      borderController = new AbortController()
      const response = await fetch(toServerUrl('/api/medias/geojson?level=province'), { signal: borderController.signal, cache: 'force-cache' })
      if (!response.ok) throw new Error('省界数据暂不可用')
      cachedBorders = await processCoordinates('boundaries', await response.json())
    }
    if (disposed || !viewer || generation !== borderGeneration) return
    borderSource.entities.suspendEvents()
    borderSource.entities.removeAll()
    for (const border of cachedBorders || []) {
      borderSource.entities.add({
        name: border.name,
        polyline: {
          positions: C.Cartesian3.fromDegreesArrayHeights(border.positions.flatMap(([lng, lat]) => [lng, lat, 1400])),
          width: 1.5,
          material: new C.PolylineGlowMaterialProperty({ color: primary(0.75), glowPower: 0.18 }),
          // Keep boundaries above high terrain without drawing the far hemisphere.
          depthFailMaterial: new C.PolylineGlowMaterialProperty({ color: primary(0.2), glowPower: 0.1 }),
        },
      })
    }
    borderSource.entities.resumeEvents()
    requestRender()
  } catch (error) {
    if (!disposed && (error as Error).name !== 'AbortError') emit('status', '省界数据暂不可用，城市和照片仍可浏览')
  }
}

async function setTerrain() {
  if (!viewer) return
  const generation = ++terrainGeneration
  if (!props.layers.terrain || props.mode === '2d') {
    viewer.terrainProvider = new C.EllipsoidTerrainProvider()
    requestRender()
    return
  }
  try {
    if (!terrain) {
      emit('status', '正在加载山脉与地形')
      terrain = await C.ArcGISTiledElevationTerrainProvider.fromUrl('https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer')
    }
    if (disposed || !viewer || generation !== terrainGeneration) return
    viewer.terrainProvider = terrain
    viewer.scene.verticalExaggeration = 1.5
    emit('status', '三维地形已开启')
    requestRender()
  } catch {
    if (!disposed && viewer && generation === terrainGeneration) {
      viewer.terrainProvider = new C.EllipsoidTerrainProvider()
      emit('status', '地形服务暂不可用，已保留球面地图')
    }
  }
}

async function loadImagery() {
  if (!viewer) return
  const fallback = new C.UrlTemplateImageryProvider({
    url: '/cesium/Assets/Textures/NaturalEarthII/{z}/{x}/{reverseY}.jpg',
    tilingScheme: new C.GeographicTilingScheme(), maximumLevel: 2,
    credit: new C.Credit('Natural Earth', true),
  })
  const localLayer = viewer.imageryLayers.addImageryProvider(fallback)
  localLayer.brightness = 0.72; localLayer.saturation = 0.7
  requestRender()
  try {
    const runtime = await settingsApi.getMapRuntime()
    if (disposed || !viewer) return
    if (runtime?.provider !== 'tianditu' || !runtime?.access_token) throw new Error('没有卫星影像配置')
    const template = toServerUrl(`/api/system/map-proxy/${encodeURIComponent(runtime.access_token)}/t0.tianditu.gov.cn/DataServer?T=img_w&x={x}&y={y}&l={z}`)
    // Probe once before Cesium fans out tile requests. A configured key can
    // still be temporarily unreachable; in that case Natural Earth remains
    // visible without flooding the console and proxy with failed requests.
    const probeUrl = template.replace('{x}', '3').replace('{y}', '1').replace('{z}', '2')
    const probe = await fetch(probeUrl, { signal: AbortSignal.timeout(5000) })
    if (!probe.ok) throw new Error('卫星影像服务不可用')
    const satellite = new C.UrlTemplateImageryProvider({
      url: template, tilingScheme: new C.WebMercatorTilingScheme(), minimumLevel: 1, maximumLevel: 18,
      credit: new C.Credit('影像 © 天地图', true),
    })
    const layer = viewer.imageryLayers.addImageryProvider(satellite)
    layer.brightness = 0.66; layer.contrast = 1.12; layer.saturation = 0.64; layer.gamma = 0.9
    let failures = 0
    cleanup.push(satellite.errorEvent.addEventListener(() => {
      if (++failures === 8 && !disposed && viewer) {
        layer.show = false
        emit('status', '卫星影像暂不可用，已切换为内置地球底图')
        requestRender()
      }
    }))
    emit('status', '天地图卫星影像 · WGS84 足迹')
  } catch {
    if (!disposed) emit('status', '当前使用内置地球底图；配置天地图后可显示高清卫星影像')
  }
  requestRender()
}

function resetView(duration = 1.2) {
  if (!viewer) return
  const camera = viewer.camera
  if (props.mode === '2d') {
    camera.flyTo({ destination: C.Rectangle.fromDegrees(72, 16, 138, 55), duration: prefersReducedMotion.matches ? 0 : duration })
  } else if (props.mode === 'globe') {
    centerGlobe(isMobile() ? 28500000 : 24500000, duration, C.Cartesian3.fromDegrees(108, 27))
  } else {
    const target = C.Cartesian3.fromDegrees(106, 32)
    const offset = new C.HeadingPitchRange(0, C.Math.toRadians(-53), isMobile() ? 11500000 : 8100000)
    camera.flyToBoundingSphere(new C.BoundingSphere(target, 0), { offset, duration: prefersReducedMotion.matches ? 0 : duration })
  }
  requestRender()
}

function globeOrientation(position: Cesium.Cartesian3) {
  const direction = C.Cartesian3.normalize(C.Cartesian3.negate(position, new C.Cartesian3()), new C.Cartesian3())
  let up = C.Cartesian3.subtract(
    C.Cartesian3.UNIT_Z,
    C.Cartesian3.multiplyByScalar(direction, C.Cartesian3.dot(C.Cartesian3.UNIT_Z, direction), new C.Cartesian3()),
    new C.Cartesian3(),
  )
  if (C.Cartesian3.magnitudeSquared(up) < 0.0001) up = C.Cartesian3.clone(C.Cartesian3.UNIT_Y)
  C.Cartesian3.normalize(up, up)
  return { direction, up }
}

function centerGlobe(distanceFromCenter?: number, duration = 0, viewFrom?: Cesium.Cartesian3) {
  if (!viewer) return
  const camera = viewer.camera
  const current = viewFrom ?? camera.positionWC
  const fallback = C.Cartesian3.fromDegrees(108, 27, 19000000)
  const radial = C.Cartesian3.magnitudeSquared(current) > 1
    ? C.Cartesian3.normalize(current, new C.Cartesian3())
    : C.Cartesian3.normalize(fallback, new C.Cartesian3())
  const distance = C.Math.clamp(distanceFromCenter ?? C.Cartesian3.magnitude(current), 13200000, 32000000)
  const destination = C.Cartesian3.multiplyByScalar(radial, distance, new C.Cartesian3())
  const orientation = globeOrientation(destination)
  if (duration > 0 && !prefersReducedMotion.matches) camera.flyTo({ destination, orientation, duration })
  else camera.setView({ destination, orientation })
  requestRender()
}

function zoomGlobe(scale: number) {
  if (!viewer) return
  centerGlobe(C.Cartesian3.magnitude(viewer.camera.positionWC) * scale)
}

function flyToCity(city: FootprintCity) {
  if (!viewer || !validPosition([city.lng, city.lat])) return
  if (props.mode === '2d') {
    viewer.camera.flyTo({ destination: C.Cartesian3.fromDegrees(city.lng, city.lat, 350000), duration: prefersReducedMotion.matches ? 0 : 1.4 })
  } else {
    viewer.camera.flyToBoundingSphere(new C.BoundingSphere(geographicPosition(city, 0), 0), { offset: new C.HeadingPitchRange(0, C.Math.toRadians(-48), 320000), duration: prefersReducedMotion.matches ? 0 : 1.4 })
  }
  requestRender()
}

function changeMode() {
  if (!viewer) return
  viewer.camera.cancelFlight()
  if (props.mode === '2d') viewer.scene.morphTo2D(0)
  else if (viewer.scene.mode !== C.SceneMode.SCENE3D) viewer.scene.morphTo3D(0)
  resetView(0.9)
  void renderRoutes()
  void setTerrain()
  syncAnimation()
}

function animate(time: number) {
  frame = 0
  if (!viewer || disposed || hidden) return
  const elapsed = Math.min(0.05, (time - (previousFrame || time)) / 1000)
  previousFrame = time
  if (props.rotating && props.mode === 'globe' && !prefersReducedMotion.matches) viewer.camera.rotate(C.Cartesian3.UNIT_Z, -elapsed * 0.018)
  if (props.playing && props.layers.routes) {
    const path = routePaths[Math.max(0, props.activeRouteIndex)]
    if (path?.length && activeDot && activeTrail) {
      animationProgress = Math.min(1, animationProgress + elapsed * Math.max(0.25, props.playbackSpeed || 1) / 3.6)
      const position = animationProgress * (path.length - 1)
      const index = Math.floor(position)
      const head = C.Cartesian3.lerp(path[index], path[Math.min(path.length - 1, index + 1)], position - index, new C.Cartesian3())
      activeDot.show = true
      activeDot.position = new C.ConstantPositionProperty(head)
      activeTrail.show = true
      activeTrail.polyline!.positions = new C.ConstantProperty([...path.slice(Math.max(0, index - 7), index + 1), head])
      if (animationProgress >= 1) {
        activeDot.show = false
        activeTrail.show = false
      }
    }
  }
  requestRender()
  frame = requestAnimationFrame(animate)
}

function syncAnimation() {
  if (frame) cancelAnimationFrame(frame)
  frame = 0; previousFrame = 0
  if (!viewer || hidden || disposed) return
  if ((props.rotating && props.mode === 'globe' && !prefersReducedMotion.matches) || (props.playing && props.layers.routes)) frame = requestAnimationFrame(animate)
  if (!props.playing) {
    if (activeDot) activeDot.show = false
    if (activeTrail) activeTrail.show = false
  }
  requestRender()
}

function resize() {
  if (!viewer) return
  syncRenderQuality()
  viewer.resize()
  requestRender()
  clearTimeout(resizeTimer)
  resizeTimer = setTimeout(() => { void renderPhotos() }, 180)
}
function zoomIn() {
  if (!viewer) return
  if (props.mode === 'globe') zoomGlobe(0.78)
  else { viewer.camera.zoomIn(viewer.camera.positionCartographic.height * 0.35); requestRender() }
}
function zoomOut() {
  if (!viewer) return
  if (props.mode === 'globe') zoomGlobe(1.28)
  else { viewer.camera.zoomOut(viewer.camera.positionCartographic.height * 0.45); requestRender() }
}

function visibilityChanged() {
  hidden = document.hidden
  if (viewer) viewer.useDefaultRenderLoop = !hidden
  syncAnimation()
}

function emitViewChange() {
  if (!viewer) return
  const rectangle = viewer.camera.computeViewRectangle()
  if (!rectangle || viewer.camera.positionCartographic.height > 8000000) { emit('view-change', null); return }
  const west = C.Math.toDegrees(rectangle.west)
  const east = C.Math.toDegrees(rectangle.east)
  // Date-line crossing views cannot be represented by a single API bbox.
  if (east <= west) { emit('view-change', null); return }
  emit('view-change', [west, C.Math.toDegrees(rectangle.south), east, C.Math.toDegrees(rectangle.north)].map(value => value.toFixed(4)).join(','))
}

onMounted(async () => {
  try {
    C = await import('@/utils/cesiumRuntime')
    if (disposed || !container.value) return
    viewer = new C.Viewer(container.value, {
      baseLayer: false, baseLayerPicker: false, geocoder: false, homeButton: false,
      sceneModePicker: false, navigationHelpButton: false, animation: false, timeline: false,
      fullscreenButton: false, selectionIndicator: false, infoBox: false,
      showRenderLoopErrors: false, requestRenderMode: true, maximumRenderTimeChange: Infinity,
      sceneMode: props.mode === '2d' ? C.SceneMode.SCENE2D : C.SceneMode.SCENE3D,
      scene3DOnly: false, shouldAnimate: false,
      contextOptions: { webgl: { alpha: false, antialias: true, powerPreference: 'high-performance' } },
    })
    syncRenderQuality()
    viewer.scene.backgroundColor = C.Color.fromCssColorString('#020810')
    viewer.scene.globe.baseColor = C.Color.fromCssColorString('#07182a')
    viewer.scene.globe.enableLighting = false
    viewer.scene.globe.showGroundAtmosphere = true
    viewer.scene.globe.tileCacheSize = isMobile() ? 128 : 256
    viewer.scene.fog.density = 0.0001
    viewer.scene.postProcessStages.fxaa.enabled = true
    if (viewer.scene.skyAtmosphere) {
      viewer.scene.skyAtmosphere.show = true
      viewer.scene.skyAtmosphere.brightnessShift = 0.12
    }
    viewer.scene.screenSpaceCameraController.minimumZoomDistance = 800
    viewer.scene.screenSpaceCameraController.maximumZoomDistance = 42000000
    viewer.cesiumWidget.screenSpaceEventHandler.removeInputAction(C.ScreenSpaceEventType.LEFT_DOUBLE_CLICK)
    globeWheelListener = event => {
      if (!viewer || props.mode !== 'globe') return
      event.preventDefault()
      event.stopImmediatePropagation()
      zoomGlobe(Math.exp(C.Math.clamp(event.deltaY, -240, 240) * 0.0015))
    }
    viewer.canvas.addEventListener('wheel', globeWheelListener, { capture: true, passive: false })
    citySource = new C.CustomDataSource('footprint-cities')
    photoSource = new C.CustomDataSource('footprint-photos')
    routeSource = new C.CustomDataSource('footprint-routes')
    heatSource = new C.CustomDataSource('footprint-heat')
    borderSource = new C.CustomDataSource('footprint-boundaries')
    for (const source of [borderSource, heatSource, routeSource, citySource, photoSource]) await viewer.dataSources.add(source)
    citySource.clustering.enabled = true
    citySource.clustering.pixelRange = isMobile() ? 35 : 42
    citySource.clustering.minimumClusterSize = 4
    citySource.clustering.clusterEvent.addEventListener((entities: Cesium.Entity[], cluster: any) => {
      cluster.label.show = true
      cluster.label.text = `${entities.length} 城市`
      cluster.label.font = '12px sans-serif'
      cluster.label.fillColor = C.Color.WHITE
      cluster.label.showBackground = true
      cluster.label.backgroundColor = primary(0.78)
      cluster.label.backgroundPadding = new C.Cartesian2(10, 7)
      cluster.label.outlineWidth = 0
      cluster.label.id = entities
      cluster.billboard.show = false
      cluster.point.show = false
    })
    try {
      worker = new Worker(new URL('../../workers/footprintScene.worker.ts', import.meta.url), { type: 'module' })
      worker.onmessage = event => {
        const job = pendingJobs.get(event.data.id)
        if (!job) return
        pendingJobs.delete(event.data.id)
        if (event.data.error) job.reject(new Error(event.data.error))
        else job.resolve(event.data.result)
      }
      worker.onerror = () => {
        pendingJobs.forEach(job => job.reject(new Error('地图计算已切换到兼容模式')))
        pendingJobs.clear(); worker?.terminate(); worker = undefined
      }
    } catch { worker = undefined }
    handler = new C.ScreenSpaceEventHandler(viewer.canvas)
    handler.setInputAction((movement: { position: Cesium.Cartesian2 }) => {
      if (!viewer) return
      const picked = viewer.scene.pick(movement.position)
      const entity = picked?.id
      if (Array.isArray(entity) && entity.length) {
        const positions = entity.map(item => item.position?.getValue(C.JulianDate.now())).filter(Boolean)
        if (positions.length) viewer.camera.flyToBoundingSphere(C.BoundingSphere.fromPoints(positions), { duration: 0.8, offset: new C.HeadingPitchRange(0, -Math.PI / 3, 0) })
      } else if (entity?.id?.startsWith('city:') || entity?.id?.startsWith('photo:')) {
        emit('select-city', entity.id.slice(entity.id.indexOf(':') + 1))
      }
    }, C.ScreenSpaceEventType.LEFT_CLICK)
    handler.setInputAction((movement: { endPosition: Cesium.Cartesian2 }) => {
      if (!viewer) return
      const picked = viewer.scene.pick(movement.endPosition)
      viewer.canvas.style.cursor = picked?.id ? 'pointer' : 'grab'
    }, C.ScreenSpaceEventType.MOUSE_MOVE)
    cleanup.push(viewer.camera.moveEnd.addEventListener(() => {
      clearTimeout(refreshTimer)
      refreshTimer = setTimeout(() => { void renderPhotos(); emitViewChange() }, 200)
    }))
    cleanup.push(viewer.scene.renderError.addEventListener(() => {
      failure.value = '当前设备的图形渲染出现问题，请刷新页面后重试'
      emit('error', failure.value)
      if (frame) cancelAnimationFrame(frame)
    }))
    const onContextLost = (event: Event) => { event.preventDefault(); failure.value = '图形资源暂不可用，请刷新页面恢复三维地图'; emit('error', failure.value) }
    viewer.canvas.addEventListener('webglcontextlost', onContextLost)
    cleanup.push(() => viewer?.canvas.removeEventListener('webglcontextlost', onContextLost))
    resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(container.value)
    document.addEventListener('visibilitychange', visibilityChanged)
    prefersReducedMotion.addEventListener('change', syncAnimation)
    resetView(0)
    renderCities()
    void renderRoutes()
    void loadBoundaries()
    void loadImagery()
    void setTerrain()
    isReady.value = true
    emit('ready')
    visibilityChanged()
  } catch (error) {
    if (disposed) return
    console.error('Footprint globe initialization failed', error)
    failure.value = '当前浏览器无法开启三维地图，请使用支持 WebGL 的浏览器并开启硬件加速'
    emit('error', failure.value)
  }
})

watch(() => props.cities, renderCities)
watch(() => props.routes, () => { void renderRoutes() })
watch(() => props.mode, changeMode)
watch(() => props.selectedCityId, renderCities)
watch(() => props.activeRouteIndex, updateRouteSelection)
watch(() => [props.playing, props.rotating], syncAnimation)
watch(() => props.layers.photos, () => { void renderPhotos() })
watch(() => props.layers.heatmap, renderHeatmap)
watch(() => props.layers.routes, value => { if (routeSource) routeSource.show = value; syncAnimation() })
watch(() => props.layers.boundaries, () => { void loadBoundaries() })
watch(() => props.layers.terrain, () => { void setTerrain() })
watch(() => currentTheme.value.primary, () => { if (viewer) { renderCities(); void loadBoundaries() } })

onBeforeUnmount(() => {
  disposed = true
  ++photoGeneration; ++routeGeneration; ++borderGeneration; ++terrainGeneration
  if (frame) cancelAnimationFrame(frame)
  clearTimeout(resizeTimer); clearTimeout(refreshTimer)
  borderController?.abort()
  worker?.terminate()
  pendingJobs.forEach(job => job.reject(new Error('地图已关闭')))
  pendingJobs.clear()
  resizeObserver?.disconnect()
  document.removeEventListener('visibilitychange', visibilityChanged)
  prefersReducedMotion.removeEventListener('change', syncAnimation)
  if (globeWheelListener) viewer?.canvas.removeEventListener('wheel', globeWheelListener, true)
  cleanup.forEach(remove => remove())
  handler?.destroy()
  if (viewer && !viewer.isDestroyed()) viewer.destroy()
  viewer = undefined
  imageCache.clear()
})

defineExpose({ flyToCity, resetView, zoomIn, zoomOut, resize })
</script>

<style scoped>
.footprint-globe, .globe-canvas { position: absolute; inset: 0; overflow: hidden; background: #020810; }
.globe-canvas :deep(.cesium-viewer), .globe-canvas :deep(.cesium-widget), .globe-canvas :deep(canvas) { width: 100%; height: 100%; }
.globe-canvas :deep(.cesium-viewer-bottom) { left: 14px; bottom: 5px; max-width: calc(100% - 28px); font-size: 9px; opacity: .7; }
.globe-canvas :deep(.cesium-credit-logoContainer) { display: inline-flex; align-items: center; }
.globe-canvas :deep(.cesium-credit-logoContainer img) { max-height: 18px; }
.globe-canvas :deep(.cesium-credit-textContainer) { color: #9ca3af; }
.globe-canvas :deep(.cesium-widget-credits a:focus-visible) { outline: 2px solid var(--theme-primary); outline-offset: 2px; }
.globe-loading, .globe-failure { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 18px; color: #e5e7eb; background: radial-gradient(ellipse at center, #0c2035, #020810 70%); }
.globe-loading { font-size: 13px; letter-spacing: .2em; }
.loading-orbit { width: 64px; height: 64px; border: 1px solid rgba(var(--theme-rgb), .15); border-top-color: var(--theme-primary); border-radius: 50%; animation: orbit 1.4s linear infinite; box-shadow: 0 0 38px rgba(var(--theme-rgb), .15); }
.globe-failure { padding: 32px; text-align: center; font-size: 15px; }
.globe-failure span { color: #9ca3af; font-size: 12px; }
.globe-hint { position: absolute; bottom: 7px; right: 14px; color: #9ca3af; font-size: 10px; pointer-events: none; opacity: .7; }
@keyframes orbit { to { transform: rotate(360deg); } }
@media (max-width: 700px) { .globe-hint { display: none; } .globe-canvas :deep(.cesium-viewer-bottom) { font-size: 8px; } }
@media (prefers-reduced-motion: reduce) { .loading-orbit { animation: none; } }
</style>
