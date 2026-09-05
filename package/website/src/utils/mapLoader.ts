import { settingsApi } from '@/api/settings'
import { isMobileApp, isNativeApp, toServerUrl } from '@/config/server'

export class MapLoadError extends Error {
  code: string
  constructor(message: string, code: string) {
    super(message)
    this.code = code
  }
}

let loadingPromise: Promise<string> | null = null

/**
 * Return the TrailSnap nginx tile proxy when the current runtime can reach it.
 *
 * The Capacitor app is served from its own WebView origin, so a relative tile
 * URL would point at the app shell instead of the server selected by the user.
 * Tauri is deliberately excluded because its bundled backend has no nginx tile
 * route and must keep using Tianditu's default layers.
 */
export const getTiandituTileTemplate = (layer: 'vec_w' | 'cva_w', key: string): string | null => {
  const nginxPath = `/tianditu-tiles/DataServer?T=${layer}&x={x}&y={y}&l={z}&tk=${encodeURIComponent(key)}`
  const serverPath = `/api/system/map-proxy/t0.tianditu.gov.cn/DataServer?T=${layer}&x={x}&y={y}&l={z}&tk=${encodeURIComponent(key)}`

  if (isMobileApp()) return toServerUrl(serverPath)
  if (import.meta.env.PROD && !isNativeApp()) return nginxPath
  return null
}

export const loadMapScript = async (): Promise<string> => {
  if (loadingPromise) return loadingPromise

  loadingPromise = (async () => {
    // 1. Get Settings
    let settings
    try {
        settings = await settingsApi.getSettings()
    } catch (e) {
        throw new MapLoadError('Failed to fetch settings', 'SETTINGS_ERROR')
    }

    const mapSettings = settings.map
    
    let apiKey = ''
    if (mapSettings && mapSettings.api_keys && mapSettings.api_keys.length > 0) {
      // Randomly select one key
      const keys = mapSettings.api_keys
      apiKey = keys[Math.floor(Math.random() * keys.length)]
    } else if (mapSettings && mapSettings.api_key) {
      apiKey = mapSettings.api_key
    }

    if (!apiKey) {
      throw new MapLoadError('Map API Key is missing', 'MAP_KEY_MISSING')
    }

    const { provider } = mapSettings

    // 2. Load Provider Script
    if (provider === 'tianditu') {
      await loadTianditu(apiKey)
      return apiKey
    } else {
        // Placeholder for other providers
        throw new MapLoadError(`Provider ${provider} is not supported yet`, 'UNSUPPORTED_PROVIDER')
    }
  })()

  return loadingPromise.catch(e => {
      loadingPromise = null // Reset on error so we can retry
      throw e
  })
}

const loadTianditu = (key: string) => {
  return new Promise<void>((resolve, reject) => {
    if ((window as any).T) {
      resolve()
      return
    }

    const script = document.createElement('script')
    // Capacitor must never contact Tianditu directly.  The self-hosted server
    // is the sole network boundary and proxies (and caches) every SDK request.
    // Keep the browser path direct in development so existing web deployments
    // are not forced to expose this endpoint.
    script.src = isMobileApp()
      ? toServerUrl(`/api/system/map-proxy/api.tianditu.gov.cn/api?v=4.0&tk=${encodeURIComponent(key)}`)
      : `https://api.tianditu.gov.cn/api?v=4.0&tk=${encodeURIComponent(key)}`
    script.type = 'text/javascript'
    script.onload = () => resolve()
    script.onerror = () => reject(new MapLoadError('Failed to load map script', 'SCRIPT_LOAD_ERROR'))
    document.head.appendChild(script)
  })
}
