import { computed, ref, shallowRef, watch } from 'vue'
import { acceptHMRUpdate, defineStore } from 'pinia'
import { footprintApi } from '@/api/footprint'
import { useUserStore } from '@/stores/user'
import { getServerUrl } from '@/config/server'
import type { FootprintData, FootprintMode, FootprintLayers } from '@/types/footprint'

// Bounded, owner/server scoped snapshots. Logout's trailsnap: cleanup removes
// these alongside the app's other private caches. No map-provider tiles cached.
const CACHE_TTL = 24 * 60 * 60 * 1000
const CACHE_PREFIX = 'trailsnap:footprint:v1:'

export const useFootprintStore = defineStore('footprint', () => {
  const user = useUserStore()
  const data = shallowRef<FootprintData | null>(null)
  const viewport = shallowRef<FootprintData | null>(null)
  const year = ref<number | null>(null)
  const mode = ref<FootprintMode>('3d')
  const layers = ref<FootprintLayers>({ photos: true, routes: true, heatmap: false, boundaries: true, terrain: false })
  const selectedCityId = ref<string | null>(null)
  const loading = ref(false)
  const offline = ref(false)
  const error = ref('')
  const cachedAt = ref<number | null>(null)
  const mapCities = computed(() => viewport.value?.cities ?? data.value?.cities ?? [])
  const mapRoutes = computed(() => viewport.value?.routes ?? data.value?.routes ?? [])
  const selectedCity = computed(() => mapCities.value.find(city => city.id === selectedCityId.value) ?? data.value?.cities.find(city => city.id === selectedCityId.value) ?? null)
  let requestId = 0
  let controller: AbortController | undefined
  let viewportController: AbortController | undefined
  let viewportRequest = 0
  let viewportBounds: string | null = null
  let active = false
  const cacheKey = () => `${CACHE_PREFIX}${encodeURIComponent(getServerUrl() || location.origin)}:${user.userInfo?.id || 'unknown'}:${year.value ?? 'all'}`

  function readCache(): { data: FootprintData; at: number } | null {
    if (!user.userInfo?.id) return null
    try {
      const record = JSON.parse(localStorage.getItem(cacheKey()) || 'null')
      if (record && Date.now() - record.at < CACHE_TTL && Array.isArray(record.data?.cities)) return record
    } catch { /* Private browsing / exhausted storage still supports online use. */ }
    return null
  }

  function saveCache(value: FootprintData) {
    if (!user.userInfo?.id) return
    try {
      const keys = Object.keys(localStorage).filter(key => key.startsWith(CACHE_PREFIX))
      // Five snapshots maximum across years, users and servers.
      if (keys.length >= 5 && !keys.includes(cacheKey())) localStorage.removeItem(keys[0]!)
      localStorage.setItem(cacheKey(), JSON.stringify({ at: Date.now(), data: value }))
    } catch { /* Optional cache must not interrupt the map. */ }
  }

  async function load() {
    if (!user.token) { cancel(); data.value = null; return }
    active = true
    controller?.abort()
    controller = new AbortController()
    const id = ++requestId
    resetViewport()
    const snapshot = readCache()
    data.value = snapshot?.data ?? null
    cachedAt.value = snapshot?.at ?? null
    selectedCityId.value = null
    offline.value = false
    error.value = ''
    loading.value = true
    if (!navigator.onLine && snapshot) {
      offline.value = true
      loading.value = false
      return
    }
    try {
      const value = await footprintApi.overview(year.value, controller.signal)
      if (id !== requestId) return
      data.value = value
      cachedAt.value = Date.now()
      saveCache(value)
    } catch (reason: any) {
      if (id !== requestId || reason?.code === 'ERR_CANCELED') return
      // A rejected authenticated request must never reveal a cached result.
      const status = reason?.response?.status
      if (snapshot && (!status || status >= 500) && user.token) offline.value = true
      else {
        data.value = null
        error.value = '足迹加载失败，请检查服务连接后重试。'
      }
    } finally {
      if (id === requestId) loading.value = false
    }
  }

  function resetViewport() {
    viewportController?.abort(); ++viewportRequest; viewport.value = null; viewportBounds = null
  }
  async function loadViewport(bbox: string | null) {
    // Small albums already fit the bounded overview; only large collections
    // need additional region queries after the user moves/zooms the camera.
    if (!bbox || !data.value?.sampled || offline.value) { resetViewport(); return }
    if (bbox === viewportBounds) return
    viewportController?.abort()
    viewportController = new AbortController()
    viewportBounds = bbox
    const id = ++viewportRequest
    const currentYear = year.value
    try {
      const result = await footprintApi.overview(currentYear, viewportController.signal, bbox)
      if (id === viewportRequest && year.value === currentYear) viewport.value = result
    } catch { if (id === viewportRequest) viewportBounds = null }
  }
  function cancel() { active = false; controller?.abort(); ++requestId; resetViewport(); loading.value = false }
  // Watch scalar identities, not a freshly-created array: rotating an access
  // token for the same owner must not clear a perfectly valid map.
  watch([() => user.userInfo?.id, () => !!user.token, () => getServerUrl()], () => {
    const shouldReload = active
    cancel()
    data.value = null
    selectedCityId.value = null
    year.value = null
    if (shouldReload && user.token) void load()
  })
  return { data, mapCities, mapRoutes, year, mode, layers, selectedCityId, selectedCity, loading, offline, cachedAt, error, load, loadViewport, resetViewport, cancel }
})

if (import.meta.hot) import.meta.hot.accept(acceptHMRUpdate(useFootprintStore, import.meta.hot))
