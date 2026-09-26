<template>
  <div ref="pageRoot" class="footprint-page dark" :class="{ 'ui-hidden': uiHidden }" :style="themeStyle" data-testid="footprint-page">
    <aside class="footprint-nav" aria-label="足迹导航">
      <RouterLink to="/" class="brand-link" aria-label="TrailSnap 首页"><img src="@/assets/logo.svg" alt="TrailSnap" /></RouterLink>
      <span class="nav-divider" />
      <button class="nav-item active" aria-label="3D 足迹地图"><Globe2 /><span>足迹</span></button>
      <RouterLink to="/album/location" class="nav-item"><MapPin /><span>位置</span></RouterLink>
      <RouterLink to="/album" class="nav-item"><Images /><span>相册</span></RouterLink>
      <RouterLink to="/settings" class="nav-item nav-bottom"><Settings2 /><span>设置</span></RouterLink>
    </aside>

    <main class="footprint-stage">
      <FootprintGlobe v-if="!sceneError" ref="globe" :cities="mapCities" :routes="playbackKind === 'route' && activeRouteIndex >= 0 ? data?.routes || [] : mapRoutes" :year="year" :mode="mode" :layers="layers"
        :selected-city-id="selectedCityId" :active-route-index="activeRouteIndex" :playing="playing" :rotating="rotating" :playback-speed="speed"
        @select-city="selectCity" @ready="sceneReady = true" @error="sceneError = $event" @status="sceneStatus = $event" @view-change="store.loadViewport" />
      <FootprintFallback v-else :cities="mapCities" :routes="mapRoutes" :mode="mode" :layers="layers" :selected-city-id="selectedCityId" :active-route-index="activeRouteIndex" :playing="playing" :rotating="rotating" @select-city="selectCity" />
      <div class="stage-shade" aria-hidden="true" />

      <header class="footprint-header">
        <div class="header-title"><span class="status-dot" />足迹地图 <small>TRAILSNAP</small></div>
        <div class="header-tools">
          <label class="year-control glass"><CalendarDays /><select v-model="year" aria-label="足迹年份" :disabled="loading"><option :value="null">全部年份</option><option v-for="value in years" :key="value" :value="value">{{ value }} 年</option></select></label>
          <div class="mode-switch glass" role="group" aria-label="地图视角"><button v-for="item in modes" :key="item.value" :class="{ active: mode === item.value }" :aria-pressed="mode === item.value" :aria-label="item.description" :title="item.description" @click="setMode(item.value)">{{ item.label }}</button></div>
          <div ref="searchBox" class="search-box glass"><Search /><input v-model="search" aria-label="搜索足迹城市" placeholder="搜索你的足迹城市…" @focus="searchFocused = true" @keydown.escape="searchFocused = false" />
            <div v-if="searchFocused && search.trim()" class="search-results glass"><button v-for="city in searchResults" :key="city.id" @click="selectCity(city.id); searchFocused = false; search = ''"><MapPin /><span>{{ city.name }}<small>{{ city.province || city.country }}</small></span><small>{{ format(city.photo_count) }} 张</small></button><p v-if="!searchResults.length">这个时间范围内没有匹配的足迹</p></div>
          </div>
          <button class="icon-button glass panel-toggle" :aria-expanded="showPanel" aria-label="切换足迹统计面板" @click="showPanel = !showPanel"><ChartNoAxesColumnIncreasing /></button>
          <div ref="layerMenu" class="layer-control"><button class="icon-button glass" aria-label="地图图层" :aria-expanded="showLayers" @click="showLayers = !showLayers"><Layers /></button>
            <div v-if="showLayers" class="layer-menu glass"><strong>地图图层</strong><label v-for="item in layerOptions" :key="item.key"><input v-model="layers[item.key]" type="checkbox" />{{ item.label }}</label><p>地形需要网络；底图不可用时自动显示本地地球。</p></div>
          </div>
          <button class="icon-button glass" :aria-label="fullscreen ? '退出全屏' : '全屏沉浸查看'" :title="fullscreen ? '退出全屏' : '全屏沉浸查看'" @click="toggleFullscreen"><Minimize v-if="fullscreen" /><Maximize v-else /></button>
        </div>
      </header>

      <div class="map-hero"><p class="eyebrow">EVERY PLACE TELLS A STORY</p><h1>去过的地方<br /><em>都是生活的答案</em></h1><p>{{ format(data?.summary.province_count) }} 个省份 <span>·</span> {{ format(data?.summary.city_count) }} 个城市 <span>·</span> {{ format(data?.summary.gps_photo_count) }} 张定位照片</p></div>

      <div v-if="loading || !sceneReady && !sceneError" class="loading-chip glass" role="status"><LoaderCircle class="spin" />{{ loading ? '正在整理你的旅行记忆' : '正在展开三维地球' }}</div>
      <div v-if="error || (!sceneError && !loading && data && !data.cities.length)" class="empty-state glass" role="status"><Globe2 /><h2>{{ error ? '暂时无法读取足迹' : '世界很大，留下你的第一枚足迹' }}</h2><p>{{ error || '上传带有 GPS 信息的照片后，城市和旅行路线会出现在这里。' }}</p><button v-if="error" class="primary-button" @click="store.load()">重新加载</button><RouterLink v-if="!error" to="/photos" class="primary-button">查看照片</RouterLink></div>

      <aside v-show="showPanel" class="insight-panel glass" :class="{ 'city-selected': !!selectedCity }" aria-label="足迹统计与城市详情">
        <template v-if="selectedCity">
          <div class="panel-heading"><span class="eyebrow">CITY MEMORIES</span><button class="small-button" aria-label="关闭城市详情" @click="selectedCityId = null"><X /></button></div>
          <h2>{{ selectedCity.name }}</h2><p class="muted city-region">{{ [selectedCity.province, selectedCity.country].filter(Boolean).join(' · ') }}</p>
          <div class="city-cover" v-if="selectedCity.cover_id"><img :src="thumbnailUrl(selectedCity.cover_id, 'medium')" :alt="`${selectedCity.name}的旅行记忆`" /></div>
          <div class="city-numbers"><div><strong>{{ format(selectedCity.photo_count) }}</strong><span>张照片</span></div><div><strong>{{ format(selectedCity.visit_count) }}</strong><span>次到访</span></div></div>
          <p class="visit-dates"><CalendarDays />{{ dateLabel(selectedCity.first_at) }} — {{ dateLabel(selectedCity.last_at) }}</p>
          <div class="section-heading"><h3>城市照片</h3><small>{{ photos.length }} / {{ selectedCity.photo_count }}</small></div>
          <p v-if="photoError" class="muted" role="alert">{{ photoError }}<button class="text-button" @click="loadPhotos(true)">重试</button></p>
          <div class="city-photos"><button v-for="(photo, index) in photos" :key="photo.id" :aria-label="`查看${selectedCity.name}的第${index + 1}张照片`" @click="openPhoto(index)"><img :src="thumbnailUrl(photo.id)" loading="lazy" :alt="photo.filename || `${selectedCity.name}的照片`" /></button></div>
          <button v-if="hasMorePhotos" class="load-more" :disabled="photosLoading" @click="loadPhotos(false)">{{ photosLoading ? '正在加载照片…' : '加载更多照片' }}</button>
        </template>
        <template v-else>
          <div class="panel-heading"><span class="eyebrow">YOUR WORLD, EXPLORED</span><button class="small-button mobile-only" aria-label="收起统计面板" @click="showPanel = false"><X /></button></div>
          <h2>{{ year ? `${year} 年的足迹` : '探索世界' }}</h2>
          <div class="exploration"><div class="exploration-orbit"><Globe2 /></div><div><strong>{{ format(data?.summary.country_count) }}<small> 个国家 / 地区</small></strong><p>用照片记住每一次出发</p></div></div>
          <div class="summary-grid"><div><strong>{{ format(data?.summary.province_count) }}</strong><span>省份</span></div><div><strong>{{ format(data?.summary.city_count) }}</strong><span>城市</span></div><div><strong>{{ format(data?.summary.gps_photo_count) }}</strong><span>定位照片</span></div></div>
          <div class="section-heading"><h3><MapPin />热门打卡地</h3><small>{{ rankedCities.length }} 个地点</small></div>
          <div class="city-ranking"><button v-for="(city, index) in rankedCities.slice(0, showAllCities ? 100 : 5)" :key="city.id" @click="selectCity(city.id)"><span class="rank" :class="{ top: index < 3 }">{{ index + 1 }}</span><span class="rank-name">{{ city.name }}</span><small>{{ format(city.photo_count) }} 张</small><ChevronRight /></button></div>
          <button v-if="rankedCities.length > 5" class="text-button more-cities" @click="showAllCities = !showAllCities">{{ showAllCities ? '收起排行' : '查看更多城市' }}<ChevronDown /></button>
          <div class="section-heading"><h3><ChartNoAxesColumnIncreasing />足迹趋势</h3><small>按照片拍摄年份</small></div><FootprintTrend :items="data?.timeline || []" :year="year" @select="chooseYear" />
          <p class="data-note">统计来自你的照片；{{ format(data?.summary.photo_count) }} 张照片中，{{ format(data?.summary.gps_photo_count) }} 张具有有效 GPS。</p>
        </template>
      </aside>

      <div class="map-controls glass" aria-label="地图操作"><button aria-label="放大地图" @click="globe?.zoomIn()"><Plus /></button><button aria-label="缩小地图" @click="globe?.zoomOut()"><Minus /></button><button aria-label="复位地图视角" @click="globe?.resetView()"><LocateFixed /></button><button :aria-pressed="rotating" :class="{ active: rotating }" aria-label="自动旋转地球" @click="toggleRotation"><Orbit /></button><button :aria-pressed="uiHidden" aria-label="隐藏或显示面板" @click="uiHidden = !uiHidden"><Eye v-if="uiHidden" /><EyeOff v-else /></button></div>
      <button v-if="uiHidden" class="restore-ui glass" @click="leaveImmersion"><Minimize />退出沉浸</button>

      <section v-if="data?.years.length" class="timeline-dock glass" aria-label="足迹时光回放">
        <div class="timeline-top"><div class="playback-heading"><span class="eyebrow">TRAVEL THROUGH TIME</span><strong>{{ activeRoute ? `${activeRoute.from_name} → ${activeRoute.to_name}` : year ? `${year} · 这一年走过的地方` : '时光回放 · 再次出发' }}</strong></div><div class="playback-tools"><select v-model="playbackKind" aria-label="回放内容"><option value="route">旅程回放</option><option value="year">年份巡游</option></select><button class="speed-button" aria-label="切换回放速度" @click="cycleSpeed">{{ speed }}×</button></div></div>
        <div class="timeline-main"><button class="play-button" :disabled="loading || (playbackKind === 'route' && !data.routes.length)" :aria-label="playing ? '暂停足迹回放' : '播放足迹回放'" @click="togglePlayback"><Pause v-if="playing" /><Play v-else /></button><div class="year-rail"><button :class="{ active: year === null }" @click="chooseYear(null)"><i />全部</button><button v-for="value in years" :key="value" :class="{ active: year === value }" @click="chooseYear(value)"><i />{{ value }}</button></div></div>
        <div v-if="playbackKind === 'route' && data.routes.length" class="route-progress"><span>{{ activeRoute ? dateLabel(activeRoute.start_at) : '按拍摄时间连接地点' }}</span><input type="range" min="-1" :max="data.routes.length - 1" :value="activeRouteIndex" aria-label="旅程回放进度" @input="seekRoute" /><span>{{ activeRouteIndex + 1 }} / {{ data.routes.length }}</span></div>
        <p class="route-note">地点连线表示照片的拍摄顺序，不代表实际交通路线；照片间隔超过 7 天时按不同旅程分段。{{ data.sampled ? '当前点位与路线已抽样显示。' : '' }}</p>
      </section>
      <footer class="map-status"><span v-if="offline" role="status">离线快照 · {{ cachedAt ? new Date(cachedAt).toLocaleString() : '' }}</span><span v-else>{{ sceneStatus || '拖动探索 · 滚轮缩放 · 右键拖动倾斜视角' }}</span></footer>
    </main>
    <PhotoLightbox v-if="photoIndex >= 0" :visible="true" :image="photoImages[photoIndex] || null" :images="photoImages" :current-index="photoIndex" :has-prev="photoIndex > 0" :has-next="photoIndex < photoImages.length - 1 || hasMorePhotos" @close="photoIndex = -1" @prev="photoIndex = Math.max(0, photoIndex - 1)" @next="nextPhoto" @select="photoIndex = $event" />
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { onClickOutside } from '@vueuse/core'
import { CalendarDays, ChartNoAxesColumnIncreasing, ChevronDown, ChevronRight, Eye, EyeOff, Globe2, Images, Layers, LoaderCircle, LocateFixed, MapPin, Maximize, Minimize, Minus, Orbit, Pause, Play, Plus, Search, Settings2, X } from 'lucide-vue-next'
import { useFootprintStore } from '@/stores/footprintStore'
import { footprintApi } from '@/api/footprint'
import { thumbnailUrl } from '@/utils/mediaUrl'
import { mapPhotoToImage } from '@/stores/photoStore'
import { injectTheme } from '@/composables/useTheme'
import type { FootprintCity, FootprintMode, FootprintLayers } from '@/types/footprint'
import type { Photo } from '@/types/album'
import FootprintTrend from '@/components/footprint/FootprintTrend.vue'
import FootprintFallback from '@/components/footprint/FootprintFallback.vue'
const FootprintGlobe = defineAsyncComponent(() => import('@/components/footprint/FootprintGlobe.vue'))
const PhotoLightbox = defineAsyncComponent(() => import('@/components/PhotoLightbox.vue'))
const { themeStyle } = injectTheme()
const store = useFootprintStore()
const { data, mapCities, mapRoutes, year, mode, layers, selectedCityId, selectedCity, loading, offline, cachedAt, error } = storeToRefs(store)
const pageRoot = ref<HTMLElement>()
const globe = ref<{ flyToCity: (city: FootprintCity) => void; resetView: () => void; zoomIn: () => void; zoomOut: () => void; resize: () => void }>()
const sceneReady = ref(false)
const sceneError = ref('')
const sceneStatus = ref('')
const uiHidden = ref(false)
const fullscreen = ref(false)
const showPanel = ref(window.innerWidth >= 768)
const showLayers = ref(false)
const showAllCities = ref(false)
const layerMenu = ref<HTMLElement>()
const searchBox = ref<HTMLElement>()
const search = ref('')
const searchFocused = ref(false)
const years = computed(() => [...(data.value?.years || [])].sort((a, b) => a - b))
const rankedCities = computed(() => [...(data.value?.cities || [])].sort((a, b) => b.photo_count - a.photo_count))
const searchResults = computed(() => rankedCities.value.filter(city => `${city.name} ${city.province} ${city.country}`.toLocaleLowerCase().includes(search.value.trim().toLocaleLowerCase())).slice(0, 10))
const modes: { value: FootprintMode; label: string; description: string }[] = [
  { value: '2d', label: '2D', description: '二维俯视地图，可自由平移和缩放' },
  { value: '3d', label: '3D', description: '聚焦中国的三维透视，可平移、倾斜和缩放' },
  { value: 'globe', label: '地球', description: '完整地球视角，缩放时保持地球居中' },
]
const layerOptions: { key: keyof FootprintLayers; label: string }[] = [{ key: 'photos', label: '城市照片' }, { key: 'routes', label: '旅行连线' }, { key: 'heatmap', label: '照片热力' }, { key: 'boundaries', label: '省份边界' }, { key: 'terrain', label: '三维地形' }]
const format = (value?: number) => (value || 0).toLocaleString('zh-CN')
const dateLabel = (value: string | null) => value ? value.slice(0, 10).replaceAll('-', '.') : '时间未知'
onClickOutside(layerMenu, () => { showLayers.value = false })
onClickOutside(searchBox, () => { searchFocused.value = false })

const photos = ref<Photo[]>([])
const photosLoading = ref(false)
const photoError = ref('')
const hasMorePhotos = ref(false)
const photoIndex = ref(-1)
const photoImages = computed(() => photos.value.map(mapPhotoToImage))
let photoController: AbortController | undefined
let photoRequest = 0
async function loadPhotos(reset = true) {
  if (!selectedCity.value) return
  photoController?.abort()
  photoController = new AbortController()
  const id = ++photoRequest
  if (reset) photos.value = []
  photosLoading.value = true
  photoError.value = ''
  try {
    const result = await footprintApi.photos(selectedCity.value.id, year.value, photos.value.length, photoController.signal)
    if (id !== photoRequest) return
    photos.value = [...photos.value, ...result]
    hasMorePhotos.value = result.length === 24
  } catch (reason: any) {
    if (id === photoRequest && reason?.code !== 'ERR_CANCELED') photoError.value = '照片加载失败，请稍后重试。'
  } finally { if (id === photoRequest) photosLoading.value = false }
}
function selectCity(id: string) {
  const city = mapCities.value.find(item => item.id === id) ?? data.value?.cities.find(item => item.id === id)
  if (!city) return
  pause()
  rotating.value = false
  selectedCityId.value = id
  showPanel.value = true
  uiHidden.value = false
  globe.value?.flyToCity(city)
}
watch(selectedCityId, () => {
  photoController?.abort(); ++photoRequest; photos.value = []; photoIndex.value = -1; hasMorePhotos.value = false; photoError.value = ''; photosLoading.value = false
  if (selectedCityId.value) void loadPhotos()
})
function openPhoto(index: number) { pause(); rotating.value = false; photoIndex.value = index }
async function nextPhoto() {
  if (photosLoading.value) return
  const currentCity = selectedCityId.value
  const currentIndex = photoIndex.value
  if (currentIndex >= photos.value.length - 1 && hasMorePhotos.value) await loadPhotos(false)
  if (currentCity === selectedCityId.value && photoIndex.value === currentIndex && currentIndex < photos.value.length - 1) photoIndex.value++
}

const playing = ref(false)
const rotating = ref(false)
const speed = ref(1)
const playbackKind = ref<'route' | 'year'>('route')
const activeRouteIndex = ref(-1)
const activeRoute = computed(() => data.value?.routes[activeRouteIndex.value])
let playbackTimer: ReturnType<typeof setTimeout> | undefined
function pause() { playing.value = false; clearTimeout(playbackTimer) }
function cycleSpeed() { speed.value = speed.value === 1 ? 2 : speed.value === 2 ? 4 : 1; if (playing.value) schedulePlayback() }
function schedulePlayback() {
  clearTimeout(playbackTimer)
  if (!playing.value) return
  playbackTimer = setTimeout(async () => {
    if (!playing.value) return
    if (playbackKind.value === 'route') {
      const length = data.value?.routes.length || 0
      if (activeRouteIndex.value >= length - 1) { pause(); return }
      activeRouteIndex.value++
    } else {
      const next = years.value.find(value => year.value === null || value > year.value)
      if (next === undefined) { pause(); return }
      year.value = next
      // The year watcher owns loading; let it finish before advancing again.
      await nextTick()
      return
    }
    schedulePlayback()
  }, 3600 / speed.value)
}
function togglePlayback() {
  if (playing.value) { pause(); return }
  rotating.value = false
  selectedCityId.value = null
  if (playbackKind.value === 'route') {
    if (!data.value?.routes.length) return
    layers.value.routes = true
    if (activeRouteIndex.value < 0 || activeRouteIndex.value >= data.value.routes.length - 1) activeRouteIndex.value = 0
  } else if (year.value === years.value.at(-1)) year.value = null
  playing.value = true
  schedulePlayback()
}
function seekRoute(event: Event) { pause(); layers.value.routes = true; activeRouteIndex.value = Number((event.target as HTMLInputElement).value) }
function chooseYear(value: number | null) { pause(); year.value = value }
function setMode(value: FootprintMode) { rotating.value = false; mode.value = value }
function toggleRotation() { pause(); if (mode.value !== 'globe') mode.value = 'globe'; rotating.value = !rotating.value }
watch(playbackKind, () => { pause(); activeRouteIndex.value = -1 })
watch(year, async () => { clearTimeout(playbackTimer); activeRouteIndex.value = -1; await store.load(); if (playing.value && !error.value) schedulePlayback(); else pause() })

async function toggleFullscreen() {
  if (fullscreen.value) { await leaveImmersion(); return }
  // Request the document so lightbox/dropdown portals remain visible in fullscreen.
  try { await document.documentElement.requestFullscreen?.() } catch { /* Mobile browsers retain the full-viewport immersive fallback. */ }
  fullscreen.value = true
  uiHidden.value = true
  await nextTick(); globe.value?.resize()
}
async function leaveImmersion() {
  if (document.fullscreenElement) await document.exitFullscreen().catch(() => {})
  fullscreen.value = false
  uiHidden.value = false
  await nextTick(); globe.value?.resize()
}
function onFullscreenChange() {
  fullscreen.value = !!document.fullscreenElement
  if (!fullscreen.value) uiHidden.value = false
  void nextTick(() => globe.value?.resize())
}
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && photoIndex.value < 0) { uiHidden.value = false; if (!document.fullscreenElement) fullscreen.value = false; showLayers.value = false; pause() }
}
function onVisibility() { if (document.hidden) { pause(); rotating.value = false } }
function onOnline() { if (offline.value) void store.load() }
onMounted(() => {
  void store.load()
  document.addEventListener('fullscreenchange', onFullscreenChange)
  document.addEventListener('keydown', onKeydown)
  document.addEventListener('visibilitychange', onVisibility)
  window.addEventListener('online', onOnline)
})
onBeforeUnmount(() => {
  pause(); store.cancel(); photoController?.abort(); ++photoRequest
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  document.removeEventListener('keydown', onKeydown)
  document.removeEventListener('visibilitychange', onVisibility)
  window.removeEventListener('online', onOnline)
  if (document.fullscreenElement) void document.exitFullscreen().catch(() => {})
})
</script>

<style scoped src="./footprint.css"></style>
