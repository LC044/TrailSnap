export type MapKeyTestResult = {
  valid: boolean
  reason?: string
}

import { settingsApi } from '@/api/settings'

/**
 * 由 TrailSnap Server 执行一次真实的天地图逆地理编码。
 * 只有服务返回成功状态和有效地址时才判定 Key 可用，避免仅加载 SDK 造成假阳性。
 */
export async function testTiandituServerKey(
  apiKey: string,
  timeoutMs = 10_000,
): Promise<MapKeyTestResult> {
  const key = apiKey.trim()
  if (!key) return { valid: false, reason: '请先输入 API Key' }

  try {
    void timeoutMs
    return await settingsApi.testMapKey(key)
  } catch (error: any) {
    return { valid: false, reason: error?.response?.data?.detail || '服务端无法访问天地图，请检查网络和 Key' }
  }
}
