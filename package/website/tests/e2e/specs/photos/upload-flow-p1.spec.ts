import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { test, expect } from '@playwright/test'
import type { APIRequestContext } from '@playwright/test'

import { ensureApiAccessToken, authHeaders } from '../../helpers/auth'
import { e2eEnv } from '../../../../playwright/e2e-env'

/**
 * P1 - 上传照片完整链路
 *
 * 回归本次修复的 bug（fix(photo): 修复上传照片后 metadata 404 且下游任务未派发）：
 *   1) POST /medias 上传后立即 GET /metadata?photo_id=xxx 应返回 200（修复前 404）
 *   2) 上传后应派发 6 个下游任务：EXTRACT_METADATA / RECOGNIZE_FACE / OCR /
 *      CLASSIFY_IMAGE / VISUAL_DESCRIPTION / IMAGE_EMBEDDING
 *   3) 重复上传同名文件仍应正确补齐 metadata 并派发下游任务（幂等）
 *
 * 断言下游任务时不依赖 worker 真的跑完（AI 模型加载慢，跑完可能要分钟级），
 * 只要任务被派发到队列（GET /tasks/ 能看到 payload.photo_id 匹配的 6 种类型即可）。
 */

// 6 个必须被派发的下游任务类型（对应 basic.py::handle_completion 里的入队清单）
const EXPECTED_DOWNSTREAM_TYPES = [
  'EXTRACT_METADATA',
  'RECOGNIZE_FACE',
  'OCR',
  'CLASSIFY_IMAGE',
  'VISUAL_DESCRIPTION',
  'IMAGE_EMBEDDING',
] as const

const SAMPLE_IMAGE = path.resolve(
  __dirname,
  '../../../../../official-site/public/examples/images/zhoushan-seaside.jpg',
)

/** 上传一张图片，返回后端分配的 photo id。 */
async function uploadPhoto(
  request: APIRequestContext,
  token: string,
  filePath: string,
  filename: string,
): Promise<string> {
  const buffer = await fs.promises.readFile(filePath)
  const res = await request.post(`${e2eEnv.apiBaseUrl}/medias`, {
    headers: authHeaders(token),
    multipart: {
      file: {
        name: filename,
        mimeType: 'image/jpeg',
        buffer,
      },
    },
    timeout: 30_000,
  })
  expect(res.ok(), `upload failed: ${res.status()} ${await res.text()}`).toBeTruthy()
  const body = (await res.json()) as { id: string }
  expect(body.id, 'upload response must contain photo id').toBeTruthy()
  return body.id
}

/** 拉最新一批任务，客户端按 payload.photo_id 过滤出属于目标照片的任务类型集合。 */
async function getDispatchedTaskTypes(
  request: APIRequestContext,
  token: string,
  photoId: string,
): Promise<Set<string>> {
  const res = await request.get(`${e2eEnv.apiBaseUrl}/tasks/?limit=200`, {
    headers: authHeaders(token),
    timeout: 10_000,
  })
  if (!res.ok()) return new Set()
  const body = (await res.json()) as { data?: Array<{ type: string; payload?: Record<string, unknown> | null }> }
  const types = new Set<string>()
  for (const t of body.data ?? []) {
    if (t.payload && (t.payload as Record<string, unknown>).photo_id === photoId) {
      types.add(t.type)
    }
  }
  return types
}

/** 轮询等待 6 个下游任务全部出现（不等其执行完成，只要出现在队列即可）。 */
async function waitDownstreamDispatched(
  request: APIRequestContext,
  token: string,
  photoId: string,
  timeoutMs = 30_000,
): Promise<Set<string>> {
  const deadline = Date.now() + timeoutMs
  let types = new Set<string>()
  while (Date.now() < deadline) {
    types = await getDispatchedTaskTypes(request, token, photoId)
    if (EXPECTED_DOWNSTREAM_TYPES.every((x) => types.has(x))) return types
    await new Promise((r) => setTimeout(r, 1_000))
  }
  return types
}

/** 用完把上传的照片软删除，避免污染后续 P1 用例的数据计数。 */
async function cleanupPhoto(request: APIRequestContext, token: string, photoId: string): Promise<void> {
  try {
    await request.delete(`${e2eEnv.apiBaseUrl}/photos/${photoId}`, {
      headers: authHeaders(token),
      timeout: 5_000,
    })
  } catch {
    // 清理失败不影响用例结论
  }
}

test.describe('P1 - 上传照片完整链路', () => {
  test.beforeAll(() => {
    if (!fs.existsSync(SAMPLE_IMAGE)) {
      throw new Error(`sample image missing: ${SAMPLE_IMAGE}`)
    }
  })

  test('P1 - 上传后 /metadata 立即可查且下游 6 类任务被派发', async ({ request }, testInfo) => {
    const token = await ensureApiAccessToken(request, testInfo)
    if (!token) return

    // 每次跑用唯一文件名，避免与前次残留冲突（file_path 由后端按 filename 组织）
    const tmpDir = await fs.promises.mkdtemp(path.join(os.tmpdir(), 'ts-e2e-upload-'))
    const uniqueName = `e2e-upload-${Date.now()}-${Math.random().toString(36).slice(2, 8)}.jpg`
    const tmpPath = path.join(tmpDir, uniqueName)
    await fs.promises.copyFile(SAMPLE_IMAGE, tmpPath)

    let photoId: string | null = null
    try {
      photoId = await uploadPhoto(request, token, tmpPath, uniqueName)

      // 断言 1：立即查 /metadata 应为 200（修复前是 404）
      const metaRes = await request.get(`${e2eEnv.apiBaseUrl}/metadata?photo_id=${photoId}`, {
        headers: authHeaders(token),
        timeout: 5_000,
      })
      expect(
        metaRes.status(),
        `expected 200 from /metadata immediately after upload, got ${metaRes.status()}`,
      ).toBe(200)

      // 断言 2：6 个下游任务应全部被派发（30s 内出现在 /tasks 列表里）
      const seen = await waitDownstreamDispatched(request, token, photoId)
      const missing = EXPECTED_DOWNSTREAM_TYPES.filter((x) => !seen.has(x))
      expect(missing, `these downstream task types were not dispatched: ${missing.join(', ')}`).toEqual([])
    } finally {
      if (photoId) await cleanupPhoto(request, token, photoId)
      await fs.promises.rm(tmpDir, { recursive: true, force: true })
    }
  })

  test('P1 - 重复上传同一文件仍能补齐 metadata 并派发下游任务', async ({ request }, testInfo) => {
    const token = await ensureApiAccessToken(request, testInfo)
    if (!token) return

    // 两次上传用同一 filename —— 后端会为每次上传生成独立 photo_id，
    // 但 storage.save_upload_file 可能命中同一 file_path（同名冲突处理策略取决于后端），
    // 命中冲突时正是本次修复的 "已存在" 分支要覆盖的场景。
    const tmpDir = await fs.promises.mkdtemp(path.join(os.tmpdir(), 'ts-e2e-upload-'))
    const dupName = `e2e-dup-${Date.now()}-${Math.random().toString(36).slice(2, 8)}.jpg`
    const tmpPath = path.join(tmpDir, dupName)
    await fs.promises.copyFile(SAMPLE_IMAGE, tmpPath)

    const uploadedIds: string[] = []
    try {
      for (let round = 0; round < 2; round++) {
        const photoId = await uploadPhoto(request, token, tmpPath, dupName)
        uploadedIds.push(photoId)

        const metaRes = await request.get(`${e2eEnv.apiBaseUrl}/metadata?photo_id=${photoId}`, {
          headers: authHeaders(token),
          timeout: 5_000,
        })
        expect(
          metaRes.status(),
          `round ${round + 1}: /metadata should be 200 for photo ${photoId}, got ${metaRes.status()}`,
        ).toBe(200)

        const seen = await waitDownstreamDispatched(request, token, photoId)
        const missing = EXPECTED_DOWNSTREAM_TYPES.filter((x) => !seen.has(x))
        expect(
          missing,
          `round ${round + 1}: downstream tasks not dispatched for ${photoId}: ${missing.join(', ')}`,
        ).toEqual([])
      }
    } finally {
      for (const id of uploadedIds) await cleanupPhoto(request, token, id)
      await fs.promises.rm(tmpDir, { recursive: true, force: true })
    }
  })
})
