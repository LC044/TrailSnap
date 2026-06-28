import type { APIRequestContext } from '@playwright/test'

import { e2eEnv } from '../../../playwright/e2e-env'

/**
 * P1 测试数据探针。
 *
 * P1 用例（夜间构建）依赖生产级数据量（>100 张照片、多种类型、
 * 多个相册 / 标签）。本地 `dev` 套件和 `system` 套件（e2e-up 起的
 * docker compose）所看到的数据规模差异极大：
 *
 *   - dev 套件: 由开发者本地准备，可能为空
 *   - system 套件: bootstrap 会添加测试目录并等任务结算
 *
 * 因此每个 P1 用例先调 API 探测数据，缺失时 testInfo.skip
 * + 明确 reason，避免环境噪声把整个 nightly 跑挂。Helper
 * 返回 false 表示"已 skip，调用方应立即 return"。
 */

export interface BaseResponse<T> {
  code: number
  message?: string
  msg?: string
  data: T
}

export interface PhotoSummary {
  id: string
  filename?: string
  file_type?: 'image' | 'video' | 'live_photo'
  make?: string | null
  model?: string | null
}

export interface AlbumSummary {
  id: string
  name: string
  type: 'user' | 'custom' | 'conditional' | 'smart' | 'system'
  num_photos?: number
}

export interface TagSummary {
  id: string
  tag_name: string
  count: number
}

interface SkipCapable {
  skip: (condition: boolean, reason: string) => void
}

async function tryGet<T>(request: APIRequestContext, path: string): Promise<{ ok: true; data: T } | { ok: false; status: number }> {
  try {
    const res = await request.get(`${e2eEnv.apiBaseUrl}${path}`, { timeout: 5_000 })
    if (!res.ok()) return { ok: false, status: res.status() }
    // 大多数列表端点直接返回数组；个别返回 BaseResponse[data]
    const body = await res.json()
    return { ok: true, data: body as T }
  } catch {
    return { ok: false, status: 0 }
  }
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

/** 探测照片总数，< minCount 时 skip。返回 false 表示已 skip。 */
export async function requirePhotos(
  request: APIRequestContext,
  testInfo: SkipCapable,
  minCount = 1,
  limit = 50,
): Promise<{ ok: true; photos: PhotoSummary[] } | { ok: false }> {
  const res = await tryGet<PhotoSummary[] | BaseResponse<PhotoSummary[]>>(
    request,
    `/api/photos?skip=0&limit=${limit}`,
  )
  if (!res.ok) {
    if (skipIfUnreachable(testInfo, res.status)) return { ok: false }
    testInfo.skip(true, `Photos endpoint failed (HTTP ${res.status})`)
    return { ok: false }
  }
  const photos = Array.isArray(res.data) ? res.data : (res.data as BaseResponse<PhotoSummary[]>).data ?? []
  if (photos.length < minCount) {
    testInfo.skip(true, `Need at least ${minCount} photo(s) for this P1 case, found ${photos.length}. Seed via /api/medias upload or system bootstrap.`)
    return { ok: false }
  }
  return { ok: true, photos }
}

/** 探测指定 file_type 是否存在。 */
export async function requirePhotoOfType(
  request: APIRequestContext,
  testInfo: SkipCapable,
  fileType: 'image' | 'video' | 'live_photo',
): Promise<{ ok: true; photo: PhotoSummary } | { ok: false }> {
  const probe = await requirePhotos(request, testInfo, 1, 200)
  if (!probe.ok) return { ok: false }
  const match = probe.photos.find((p) => p.file_type === fileType)
  if (!match) {
    testInfo.skip(true, `No photo with file_type="${fileType}" in the first 200 photos; this P1 case requires a real seeded asset.`)
    return { ok: false }
  }
  return { ok: true, photo: match }
}

/** 探测 EXIF 字段（make / model）是否非空。 */
export async function requirePhotoWithExif(
  request: APIRequestContext,
  testInfo: SkipCapable,
): Promise<{ ok: true; photo: PhotoSummary } | { ok: false }> {
  const probe = await requirePhotos(request, testInfo, 1, 200)
  if (!probe.ok) return { ok: false }
  const withExif = probe.photos.find((p) => (p.make && p.make.trim()) || (p.model && p.model.trim()))
  if (!withExif) {
    testInfo.skip(true, `No photo with EXIF make/model in the first 200 photos; this P1 case requires a real camera asset.`)
    return { ok: false }
  }
  return { ok: true, photo: withExif }
}

/** 探测至少一个用户相册。 */
export async function requireAnyAlbum(
  request: APIRequestContext,
  testInfo: SkipCapable,
): Promise<{ ok: true; album: AlbumSummary } | { ok: false }> {
  const res = await tryGet<AlbumSummary[] | BaseResponse<AlbumSummary[]>>(request, `/api/albums?limit=100`)
  if (!res.ok) {
    if (skipIfUnreachable(testInfo, res.status)) return { ok: false }
    testInfo.skip(true, `Albums endpoint failed (HTTP ${res.status})`)
    return { ok: false }
  }
  const albums = Array.isArray(res.data) ? res.data : (res.data as BaseResponse<AlbumSummary[]>).data ?? []
  if (albums.length === 0) {
    testInfo.skip(true, `Need at least 1 album for this P1 case, found 0. Create one via /album first.`)
    return { ok: false }
  }
  return { ok: true, album: albums[0] }
}

/** 探测至少一个分类标签（智能分类页用）。 */
export async function requireAnyTag(
  request: APIRequestContext,
  testInfo: SkipCapable,
): Promise<{ ok: true; tag: TagSummary } | { ok: false }> {
  const res = await tryGet<TagSummary[] | BaseResponse<TagSummary[]>>(request, `/api/tags?limit=100`)
  if (!res.ok) {
    if (skipIfUnreachable(testInfo, res.status)) return { ok: false }
    testInfo.skip(true, `Tags endpoint failed (HTTP ${res.status})`)
    return { ok: false }
  }
  const tags = Array.isArray(res.data) ? res.data : (res.data as BaseResponse<TagSummary[]>).data ?? []
  if (tags.length === 0) {
    testInfo.skip(true, `Need at least 1 tag for this P1 case, found 0. Run CLASSIFY_IMAGE task first.`)
    return { ok: false }
  }
  return { ok: true, tag: tags[0] }
}
