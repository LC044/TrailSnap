import type { APIRequestContext } from '@playwright/test'

import { e2eEnv } from '../../../playwright/e2e-env'
import { ensureApiAccessToken } from './auth'
import { preparePhotoFixtures, type SkipCapable } from './photo-fixtures'

/**
 * P1/P0 测试数据探针：位置相册。
 *
 * 位置相册需要带 GPS 坐标的照片才会出现在 level=city/province/district 列表里。
 * 默认 dev / system 套件下的 fixture 扫描准备阶段（preparePhotoFixtures）会扫描
 * TS_PHOTO_HOST_DIR/smoke|p0 子目录并触发 EXIF_LOCATION 任务，但不保证所有照片
 * 都能拿到坐标。本模块对 location 数据做最小依赖：能查到就继续，0 数据就 skip。
 */

export interface BaseResponse<T> {
  code: number
  message?: string
  msg?: string
  data: T
}

export interface LocationSummary {
  id?: string
  is_custom?: boolean
  name: string
  level: 'city' | 'province' | 'district' | 'scene'
  count: number
  cover?: unknown
}

export interface SceneSummary {
  id: string
  name: string
  is_custom: boolean
  description?: string
  level?: number
  address?: string
  latitude?: number
  longitude?: number
  radius?: number
  polygon?: number[][]
  photo_count?: number
}

async function tryGet<T>(request: APIRequestContext, path: string, token?: string): Promise<{ ok: true; data: T } | { ok: false; status: number }> {
  try {
    const res = await request.get(`${e2eEnv.apiBaseUrl}${path}`, {
      timeout: 5_000,
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    })
    if (!res.ok()) return { ok: false, status: res.status() }
    const body = await res.json()
    return { ok: true, data: body as T }
  } catch {
    return { ok: false, status: 0 }
  }
}

function asArray<T>(body: T[] | BaseResponse<T[]>): T[] {
  if (Array.isArray(body)) return body
  if (body && typeof body === 'object' && 'data' in body) {
    const data = (body as BaseResponse<T[]>).data
    return Array.isArray(data) ? data : []
  }
  return []
}

function skipIfUnreachable(testInfo: SkipCapable, status: number): boolean {
  if (status === 0) {
    testInfo.skip(true, `Backend not reachable at ${e2eEnv.apiBaseUrl}`)
    return true
  }
  if (status === 401 || status === 403) {
    testInfo.skip(true, `Auth missing or insufficient (HTTP ${status}); ensure ${e2eEnv.testUsername} is registered`)
    return true
  }
  return false
}

async function ensureLocationFixtures(
  request: APIRequestContext,
  testInfo: SkipCapable,
  bucket: 'smoke' | 'p0' = 'p0',
): Promise<string> {
  const token = await ensureApiAccessToken(request, testInfo)
  if (!token) return ''
  const prepared = await preparePhotoFixtures(request, {
    bucket,
    token,
    testInfo,
    onUnavailable: 'skip',
  })
  return prepared ? token : ''
}

/**
 * 探测至少一个位置（默认 level=city）。需要至少一张带 GPS 坐标的照片。
 * 空库 / EXIF_LOCATION 任务未完成 / 测试目录下无照片时跳过。
 */
export async function requireAnyLocation(
  request: APIRequestContext,
  testInfo: SkipCapable,
): Promise<{ ok: true; location: LocationSummary } | { ok: false }> {
  const token = await ensureLocationFixtures(request, testInfo)
  if (!token) return { ok: false }

  const res = await tryGet<LocationSummary[] | BaseResponse<LocationSummary[]>>(
    request,
    '/locations?level=city&skip=0&limit=20',
    token,
  )
  if (!res.ok) {
    if (skipIfUnreachable(testInfo, res.status)) return { ok: false }
    testInfo.skip(true, `Locations endpoint failed (HTTP ${res.status})`)
    return { ok: false }
  }
  const locations = asArray(res.data)
  if (locations.length === 0) {
    testInfo.skip(
      true,
      `Need at least 1 location for this P0 case, found 0. Run EXIF_LOCATION task on p0 photos first.`,
    )
    return { ok: false }
  }
  return { ok: true, location: locations[0] }
}

/**
 * 探测至少一个含照片的位置（count > 0）。这种位置点击进入详情页可看到照片。
 */
export async function requireLocationWithPhotos(
  request: APIRequestContext,
  testInfo: SkipCapable,
): Promise<{ ok: true; location: LocationSummary } | { ok: false }> {
  const probe = await requireAnyLocation(request, testInfo)
  if (!probe.ok) return { ok: false }
  if (!probe.location.count || probe.location.count <= 0) {
    testInfo.skip(
      true,
      `Found location "${probe.location.name}" but count=${probe.location.count}. Need a location with photos.`,
    )
    return { ok: false }
  }
  return { ok: true, location: probe.location }
}

/**
 * 探测至少一个景区（不限是否打卡）。场景卡片列表在 level=景区 时加载。
 * 没有景区的环境会 testInfo.skip + 明确 reason。
 */
export async function requireAnyScene(
  request: APIRequestContext,
  testInfo: SkipCapable,
): Promise<{ ok: true; scene: SceneSummary } | { ok: false }> {
  const token = await ensureLocationFixtures(request, testInfo)
  if (!token) return { ok: false }

  const res = await tryGet<SceneSummary[] | BaseResponse<SceneSummary[]>>(
    request,
    '/locations/scenes/list?skip=0&limit=100',
    token,
  )
  if (!res.ok) {
    if (skipIfUnreachable(testInfo, res.status)) return { ok: false }
    testInfo.skip(true, `Scenes list endpoint failed (HTTP ${res.status})`)
    return { ok: false }
  }
  const scenes = asArray(res.data)
  if (scenes.length === 0) {
    testInfo.skip(
      true,
      `Need at least 1 scene for this P1 case, found 0. Create one via /api/locations/scenes POST first.`,
    )
    return { ok: false }
  }
  return { ok: true, scene: scenes[0] }
}
