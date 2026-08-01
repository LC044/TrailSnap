import { ref, onUnmounted, nextTick, watch } from 'vue'
import { loadMapScript, MapLoadError } from '@/utils/mapLoader'
import { injectTheme } from '@/composables/useTheme'

declare const T: any

interface LocationMapOptions {
  containerId: string
  initialLat?: number
  initialLng?: number
  initialZoom?: number
  enableDrag?: boolean
}

export interface LocationDetail {
  address: string
  province: string
  city: string
  district: string
  country: string
}

export function useLocationMap(callbacks?: {
  onPositionChange?: (lat: number, lng: number, locationDetail?: LocationDetail) => void
}) {
  let map: any = null
  let marker: any = null
  let searchService: any = null
  let geocoder: any = null
  let autocompleteCallback: ((results: any[]) => void) | null = null
  let activeContainerId: string | null = null

  const currentLat = ref(0)
  const currentLng = ref(0)
  const currentLocationDetail = ref<LocationDetail | null>(null)
  const mapReady = ref(false)
  const mapError = ref<string | null>(null)
  const theme = injectTheme()

  const applyDarkMode = (containerId?: string) => {
    const id = containerId || activeContainerId
    if (!id) return
    const container = document.getElementById(id)
    if (!container) return
    if (theme.isDarkMode.value) {
      container.style.filter = 'invert(0.92) hue-rotate(180deg)'
    } else {
      container.style.filter = ''
    }
  }

  watch(() => theme.isDarkMode.value, () => {
    applyDarkMode()
  })

  const initMap = async (opts: LocationMapOptions) => {
    try {
      await loadMapScript()
    } catch (e: any) {
      mapError.value = e instanceof MapLoadError ? e.code : 'UNKNOWN'
      return
    }

    await nextTick()
    const container = document.getElementById(opts.containerId)
    if (!container) {
      mapError.value = 'CONTAINER_NOT_FOUND'
      return
    }
    container.innerHTML = ''
    activeContainerId = opts.containerId

    const hasCoords = opts.initialLat && opts.initialLng
    const center = hasCoords
      ? new T.LngLat(opts.initialLng, opts.initialLat)
      : new T.LngLat(104.195, 35.861)
    const zoom = opts.initialZoom || (hasCoords ? 14 : 4)

    map = new T.Map(opts.containerId)
    map.centerAndZoom(center, zoom)
    map.enableScrollWheelZoom()

    searchService = new T.LocalSearch(map, {
      pageCapacity: 10,
      onSearchComplete: (result: any) => {
        parseSearchResult(result)
      }
    })

    geocoder = new T.Geocoder()

    if (hasCoords) {
      setMarker(opts.initialLat!, opts.initialLng!)
      currentLat.value = opts.initialLat!
      currentLng.value = opts.initialLng!
    }

    if (opts.enableDrag && marker) {
      enableMarkerDrag()
    }

    // 无初始坐标时没有 marker，拖动无从谈起；允许点击地图落点（覆盖有/无坐标两种场景）。
    // 仅在可编辑（enableDrag）地图启用，避免影响只读地图。
    if (opts.enableDrag && map) {
      map.addEventListener('click', (e: any) => {
        const ll = e?.lnglat
        if (!ll) return
        const lng = typeof ll.getLng === 'function' ? ll.getLng() : ll.lng
        const lat = typeof ll.getLat === 'function' ? ll.getLat() : ll.lat
        if (typeof lat !== 'number' || typeof lng !== 'number') return
        setMarker(lat, lng)
        enableMarkerDrag()
        reverseGeocode(lat, lng)
      })
    }

    applyDarkMode(opts.containerId)
    mapReady.value = true
  }

  const setMarker = (lat: number, lng: number) => {
    if (!map) return
    if (marker) map.removeOverLay(marker)

    const point = new T.LngLat(lng, lat)
    marker = new T.Marker(point)
    map.addOverLay(marker)
    currentLat.value = lat
    currentLng.value = lng
  }

  const enableMarkerDrag = () => {
    if (!marker) return
    marker.enableDragging()
    marker.addEventListener('dragend', () => {
      const pos = marker.getLngLat()
      currentLat.value = pos.lat
      currentLng.value = pos.lng
      reverseGeocode(pos.lat, pos.lng)
    })
  }

  const disableMarkerDrag = () => {
    if (!marker) return
    marker.disableDragging()
  }

  const centerOnPosition = (lat: number, lng: number, zoom?: number) => {
    if (!map) return
    const point = new T.LngLat(lng, lat)
    map.centerAndZoom(point, zoom || 14)
  }

  const searchLocation = (keyword: string, callback: (results: any[]) => void) => {
    if (!searchService || !keyword) {
      callback([])
      return
    }
    autocompleteCallback = callback
    searchService.search(keyword, 4)
  }

  const searchAndSelect = (keyword: string) => {
    if (!searchService) return
    searchService.search(keyword, 7)
  }

  const parseSearchResult = (result: any) => {
    const type = parseInt(result.getResultType())

    if (type === 4) {
      if (autocompleteCallback) {
        const suggests = result.getSuggests()
        if (suggests) {
          const data = suggests.map((item: any) => ({
            value: item.name,
            address: item.address,
            ...item
          }))
          autocompleteCallback(data)
        } else {
          autocompleteCallback([])
        }
        autocompleteCallback = null
      }
      return
    }

    if (autocompleteCallback) {
      autocompleteCallback([])
      autocompleteCallback = null
    }

    if (type === 1) {
      const pois = result.getPois()
      if (pois && pois.length > 0) {
        const first = pois[0]
        updatePositionFromSearch(first.lonlat, first.address)
      }
    } else if (type === 3) {
      const area = result.getArea()
      if (area && area.lonlat) {
        updatePositionFromSearch(area.lonlat, area.name)
      }
    }
  }

  const reverseGeocode = (lat: number, lng: number) => {
    if (!geocoder) {
      callbacks?.onPositionChange?.(lat, lng, undefined)
      return
    }
    const lnglat = new T.LngLat(lng, lat)
    geocoder.getLocation(lnglat, (result: any) => {
      if (result && result.getStatus() === 0) {
        const addr = result.getAddress()
        const comp = result.getAddressComponent()
        // 天地图 getAddressComponent() 返回结构：
        //   { addressComponent: { province, city, county, town, nation, ... }, city, ... }
        // 区县字段叫 county（不是 district），且真正的字段表在 addressComponent 下；
        // 顶层只平铺了部分字段（如 city），province/county 必须取 addressComponent。
        const ac = comp?.addressComponent || comp || {}
        const detail: LocationDetail = {
          address: typeof addr === 'string' ? addr : (addr?.address || ''),
          province: ac?.province || '',
          city: ac?.city || '',
          district: ac?.district || ac?.county || '',
          country: ac?.nation || '中国'
        }
        currentLocationDetail.value = detail
        callbacks?.onPositionChange?.(lat, lng, detail)
      } else {
        currentLocationDetail.value = null
        callbacks?.onPositionChange?.(lat, lng, undefined)
      }
    })
  }

  const updatePositionFromSearch = (lnglatStr: string, address: string) => {
    let lat: number, lng: number
    if (typeof lnglatStr === 'string') {
      const parts = lnglatStr.split(/[\s,]+/)
      lng = parseFloat(parts[0])
      lat = parseFloat(parts[1])
    } else {
      return
    }

    if (!isNaN(lat) && !isNaN(lng)) {
      const point = new T.LngLat(lng, lat)
      map.centerAndZoom(point, 14)
      setMarker(lat, lng)
      enableMarkerDrag()
      reverseGeocode(lat, lng)
    }
  }

  const destroy = () => {
    if (map) {
      // 天地图 T.Map 没有 Leaflet 风格的 remove()，直接调用会抛
      // "map.remove is not a function"，而该方法在 el-dialog 的 @closed
      // 过渡钩子中执行，抛错会中断弹窗关闭生命周期，导致再次打开时不显示。
      // 这里做能力探测 + try/catch，确保销毁永不抛错。
      try {
        if (typeof map.clearOverLay === 'function') {
          map.clearOverLay()
        }
        if (typeof map.remove === 'function') {
          map.remove()
        }
      } catch (e) {
        // 忽略地图销毁异常，避免污染弹窗过渡
      }
      map = null
    }
    marker = null
    searchService = null
    geocoder = null
    autocompleteCallback = null
    activeContainerId = null
    mapReady.value = false
    mapError.value = null
    currentLat.value = 0
    currentLng.value = 0
  }

  onUnmounted(() => destroy())

  return {
    currentLat, currentLng, currentLocationDetail, mapReady, mapError,
    initMap, setMarker, enableMarkerDrag, disableMarkerDrag,
    centerOnPosition, searchLocation, searchAndSelect, destroy,
    applyDarkMode
  }
}
