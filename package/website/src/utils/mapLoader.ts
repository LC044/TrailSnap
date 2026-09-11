import { settingsApi } from '@/api/settings'
import { toServerUrl } from '@/config/server'

export class MapLoadError extends Error {
  code: string
  constructor(message: string, code: string) {
    super(message)
    this.code = code
  }
}

let loadingPromise: Promise<string> | null = null

/**
 * Return a tile URL on the selected TrailSnap Server. The scoped token identifies
 * the user's server-side map configuration without exposing the provider key.
 */
export const getTiandituTileTemplate = (layer: 'vec_w' | 'cva_w', accessToken: string): string => {
  const serverPath = `/api/system/map-proxy/${encodeURIComponent(accessToken)}/t0.tianditu.gov.cn/DataServer?T=${layer}&x={x}&y={y}&l={z}`
  return toServerUrl(serverPath)
}

export const loadMapScript = async (): Promise<string> => {
  if (loadingPromise) return loadingPromise

  loadingPromise = (async () => {
    // 1. Ask the Server for a scoped map token; the real provider key never
    // leaves the Server.
    let runtime
    try {
        runtime = await settingsApi.getMapRuntime()
    } catch (e) {
        const detail = (e as any)?.response?.data?.detail
        if (detail === 'Map API Key is missing') {
          throw new MapLoadError('Map API Key is missing', 'MAP_KEY_MISSING')
        }
        throw new MapLoadError('Failed to fetch map runtime', 'SETTINGS_ERROR')
    }

    const accessToken = runtime?.access_token || ''
    if (!accessToken) {
      throw new MapLoadError('Map API Key is missing', 'MAP_KEY_MISSING')
    }

    const { provider } = runtime

    // 2. Load Provider Script
    if (provider === 'tianditu') {
      await loadTianditu(accessToken)
      return accessToken
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

const loadTianditu = (accessToken: string) => {
  return new Promise<void>((resolve, reject) => {
    if ((window as any).T) {
      resolve()
      return
    }

    const script = document.createElement('script')
    // Every runtime loads the SDK through TrailSnap Server. The response is
    // rewritten so SDK subrequests keep using the same scoped map token.
    script.src = toServerUrl(`/api/system/map-proxy/${encodeURIComponent(accessToken)}/api.tianditu.gov.cn/api?v=4.0`)
    script.type = 'text/javascript'
    script.onload = () => resolve()
    script.onerror = () => reject(new MapLoadError('Failed to load map script', 'SCRIPT_LOAD_ERROR'))
    document.head.appendChild(script)
  })
}
