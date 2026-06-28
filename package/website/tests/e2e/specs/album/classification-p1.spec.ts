import { test, expect, type APIRequestContext } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'
import { requireAnyTag, requirePhotos, type BaseResponse, type TagSummary } from '../../helpers/data-probe'
import { e2eEnv } from '../../../../playwright/e2e-env'

/**
 * P1 - 智能分类（/album/classification, /album/classification/:name）
 *
 * 覆盖 doc/e2e-test-checklist.md §2.3。Nightly 用例，不带 @smoke 标签。
 *
 * 数据假设：需要至少 1 个由 YOLO 分类产生的 Tag（CLASSIFY_IMAGE 任务完成后）。
 * 没有 tag 的环境会 testInfo.skip，不阻塞 nightly 其它用例。
 */

async function getTagPhotos(request: APIRequestContext, name: string): Promise<Array<{ id: string; filename?: string }>> {
  const res = await request.get(
    `${e2eEnv.apiBaseUrl}/api/tags/${encodeURIComponent(name)}/photos?skip=0&limit=200`,
  )
  if (!res.ok()) return []
  const body = (await res.json()) as Array<{ id: string; filename?: string }> | BaseResponse<Array<{ id: string; filename?: string }>>
  return Array.isArray(body) ? body : body.data ?? []
}

async function setTagCover(request: APIRequestContext, name: string, photoId: string): Promise<void> {
  const res = await request.post(
    `${e2eEnv.apiBaseUrl}/api/tags/${encodeURIComponent(name)}/cover`,
    { data: { photo_id: photoId } },
  )
  expect(res.ok(), `set cover for ${name}`).toBeTruthy()
}

async function removePhotosFromTag(
  request: APIRequestContext,
  name: string,
  photoIds: string[],
): Promise<void> {
  const res = await request.post(
    `${e2eEnv.apiBaseUrl}/api/tags/${encodeURIComponent(name)}/remove-photos`,
    { data: { photo_ids: photoIds } },
  )
  expect(res.ok(), `remove ${photoIds.length} photo(s) from ${name}`).toBeTruthy()
}

test.describe('P1 - 智能分类', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo))) return
  })

  test('2.3.1 分类网格 - YOLO 标签列表正确渲染', async ({ page, request }, testInfo) => {
    const probe = await requireAnyTag(request, testInfo)
    if (!probe.ok) return
    await page.goto('/album/classification')

    // 列表头
    await expect(page.getByRole('heading', { name: '智能分类' })).toBeVisible({ timeout: 10_000 })

    // 至少 1 个 tag 卡片
    const tagCard = page.locator('h3[title]').first()
    await expect(tagCard).toBeVisible({ timeout: 15_000 })
    const tagName = await tagCard.textContent()
    expect(tagName?.trim().length).toBeGreaterThan(0)

    // 数量文案 "X 个项目"
    await expect(page.getByText(/\d+\s*个项目/).first()).toBeVisible()
  })

  test('2.3.2 分类详情 - 进入 tag 后列出匹配照片', async ({ page, request }, testInfo) => {
    const probe = await requireAnyTag(request, testInfo)
    if (!probe.ok) return
    const name = probe.tag.tag_name

    await page.goto(`/album/classification/${encodeURIComponent(name)}`)

    // 详情页头（ClassificationDetail 通过 :title="name" 渲染）
    await expect(page.getByText(name).first()).toBeVisible({ timeout: 15_000 })

    // API 拉过 tag 的照片（getTagPhotos -> /api/tags/{name}/photos）
    await page.waitForResponse(
      (res) => res.url().includes(`/api/tags/${encodeURIComponent(name)}/photos`) && res.status() === 200,
      { timeout: 15_000 },
    )

    // 至少 1 张图渲染
    const img = page.locator('img').first()
    await expect(img).toBeVisible({ timeout: 15_000 })
  })

  test('2.3.3 设为封面 - 选 1 张照片设为该 tag 封面', async ({ page, request }, testInfo) => {
    const probe = await requireAnyTag(request, testInfo)
    if (!probe.ok) return
    const name = probe.tag.tag_name

    const photos = await getTagPhotos(request, name)
    if (photos.length === 0) {
      testInfo.skip(true, `Tag "${name}" has 0 photos; cannot test set-cover.`)
      return
    }
    const target = photos[0]

    // 直接调 setCover API（UI 路径需要进 lightbox + 批量操作，依赖选择模式触发，路径长）
    // 这里覆盖核心行为：API 调通 + 列表重新拉取时能看到新 cover
    await setTagCover(request, name, target.id)

    // 重新拉 tag 列表
    const listRes = await request.get(`${e2eEnv.apiBaseUrl}/api/tags?limit=200`)
    const listBody = (await listRes.json()) as TagSummary[] | BaseResponse<TagSummary[]>
    const tags = Array.isArray(listBody) ? listBody : listBody.data ?? []
    const me = tags.find((t) => t.tag_name === name)
    expect(me, 'tag should still be in the list').toBeTruthy()
    expect(me!.count).toBeGreaterThan(0)
    // cover 字段被设置（不为 null）
    expect(me!.cover).toBeTruthy()
  })

  test('2.3.4 从分类中移除 - 选 1 张后该照片不再属于该 tag', async ({ page, request }, testInfo) => {
    const probe = await requireAnyTag(request, testInfo)
    if (!probe.ok) return
    const name = probe.tag.tag_name

    const before = await getTagPhotos(request, name)
    if (before.length === 0) {
      testInfo.skip(true, `Tag "${name}" has 0 photos; cannot test remove.`)
      return
    }
    const victim = before[0].id

    await removePhotosFromTag(request, name, [victim])

    const after = await getTagPhotos(request, name)
    expect(after.map((p) => p.id)).not.toContain(victim)
  })
})
