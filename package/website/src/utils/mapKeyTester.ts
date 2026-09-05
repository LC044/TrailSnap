export type MapKeyTestResult = {
  valid: boolean
  reason?: string
}

/**
 * 从当前浏览器执行一次真实的天地图逆地理编码。
 * 浏览器会携带页面 Referer，因此权限类型与域名白名单校验和地图实际使用时一致。
 * 只有服务返回成功状态和有效地址时才判定 Key 可用，避免仅加载 SDK 造成假阳性。
 */
export async function testTiandituBrowserKey(
  apiKey: string,
  timeoutMs = 10_000,
): Promise<MapKeyTestResult> {
  const key = apiKey.trim()
  if (!key) return { valid: false, reason: '请先输入 API Key' }

  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  const params = new URLSearchParams({
    postStr: JSON.stringify({ lon: 116.397, lat: 39.908, ver: 1 }),
    type: 'geocode',
    tk: key,
  })

  try {
    const { isMobileApp, toServerUrl } = await import('@/config/server')
    const endpoint = isMobileApp()
      ? toServerUrl(`/api/system/map-proxy/api.tianditu.gov.cn/geocoder?${params}`)
      : `https://api.tianditu.gov.cn/geocoder?${params}`
    const response = await fetch(endpoint, {
      signal: controller.signal,
    })
    let data: any = null
    try {
      data = await response.json()
    } catch {
      // 非 JSON 响应会在下面作为无效结果处理。
    }

    const address = data?.result?.formatted_address
    if (response.ok && String(data?.status) === '0' && typeof address === 'string' && address.trim()) {
      return { valid: true }
    }

    const reason = data?.msg || data?.message || data?.resolve
    if (reason) return { valid: false, reason: String(reason) }
    if (!response.ok) return { valid: false, reason: `天地图返回 HTTP ${response.status}` }
    return { valid: false, reason: '逆地理编码未返回有效地址，Key 不可用或权限不足' }
  } catch (error: any) {
    if (error?.name === 'AbortError') {
      return { valid: false, reason: '连接天地图超时，请检查网络或 Key 白名单' }
    }
    return { valid: false, reason: '无法访问天地图逆地理编码服务，请检查网络和域名白名单' }
  } finally {
    window.clearTimeout(timer)
  }
}
