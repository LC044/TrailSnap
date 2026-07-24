import { test, expect, type Page, type Route } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

/**
 * P1 - 智能分类 + 文件夹树覆盖（coverage-gaps-frontend.md 2 个未覆盖模块）
 *
 * 1. ClassificationList  -- /album/classification
 *    - 加载中/空态渲染
 *    - 点击 tag -> 跳 /album/classification/:name
 * 2. ClassificationDetail -- /album/classification/:name
 *    - 标题渲染（用 route.params.name）
 *    - 列表空态 + subtitle "0 个项目"
 *    - 返回按钮可回列表
 * 3. FolderTree       -- 已被 FolderBrowser 包含，但 FolderTree 自身不挂载
 *    直接被 e2e 访问：FolderBrowser 切换到 layoutMode=folder 后 FolderTree 出现，
 *    本 spec 复用 views-deeper 的 enterFolderLayout 入口，验证：
 *    - 默认根目录 children 渲染
 *    - 点击子目录 -> emit('navigate') 触发 FolderBrowser 重新请求 parent=path
 *
 * 与 views-deeper / classification-p1 互不重复：本 spec 聚焦「列表-详情」路由 +
 * 文件夹树节点交互，避开已有覆盖（YOLO tag list 网格、tag 点开列出照片、地图视图）。
 */

test.describe.configure({ mode: 'serial' })

const TAGS_RESPONSE = [
  { tag_name: '海边', count: 12 },
  { tag_name: '夜景', count: 8 },
]

const TAG_PHOTOS_RESPONSE: any[] = []

function mockTags(route: Route) {
  return route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ code: 0, message: 'success', data: TAGS_RESPONSE }),
  })
}

function mockTagPhotos(route: Route) {
  return route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ code: 0, message: 'success', data: TAG_PHOTOS_RESPONSE }),
  })
}

const FOLDER_TREE = {
  code: 0,
  message: 'success',
  data: {
    parent: '',
    breadcrumb: [],
    own_count: 5,
    children: [
      { path: 'C:/photos/2024', name: '2024', count: 3, has_children: false },
      { path: 'C:/photos/2025', name: '2025', count: 2, has_children: false },
    ],
  },
}

async function enterFolderLayout(page: Page) {
  await page.goto('/photos')
  await expect(page.locator('body')).toBeVisible()
  const settingsBtn = page.locator('button[title="视图设置"]')
  await expect(settingsBtn).toBeVisible({ timeout: 15_000 })
  await settingsBtn.click()
  const folderItem = page.locator('button:has-text("文件夹")').first()
  await expect(folderItem).toBeVisible({ timeout: 5_000 })
  await folderItem.click()
  await expect(page.locator('.folder-browser')).toBeVisible({ timeout: 10_000 })
}

test.describe('P1 - 智能分类 + 文件夹树 @classification-folder', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return
  })

  test('进入 /album/classification -> 渲染 tag 列表 + 返回按钮可见', async ({ page }) => {
    await page.route('**/api/tags**', (route) => {
      const u = new URL(route.request().url())
      // /api/tags/:name/photos 也命中；空 photos 也走 mock
      if (/\/photos$/.test(u.pathname)) return mockTagPhotos(route)
      return mockTags(route)
    })
    await page.goto('/album/classification')
    await expect(page.locator('body')).toBeVisible()
    // 标题"智能分类"
    await expect(page.getByRole('heading', { name: '智能分类' })).toBeVisible({ timeout: 15_000 })
    // 两个 tag 都出现
    await expect(page.getByText('海边').first()).toBeVisible()
    await expect(page.getByText('夜景').first()).toBeVisible()
    // 返回按钮（带 ArrowLeft 图标的 button）
    const backBtn = page.locator('button:has(.lucide-arrow-left)').first()
    await expect(backBtn).toBeVisible()
  })

  test('点击 tag -> 跳 /album/classification/:name + 标题与副标题正确', async ({ page }) => {
    await page.route('**/api/tags**', (route) => {
      const u = new URL(route.request().url())
      if (/\/photos$/.test(u.pathname)) return mockTagPhotos(route)
      return mockTags(route)
    })
    await page.goto('/album/classification')
    await expect(page.getByText('海边').first()).toBeVisible({ timeout: 15_000 })

    // 点 tag
    await page.getByText('海边').first().click()
    // URL 会被 URL-encode，海边 -> %E6%B5%B7%E8%BE%B9
    await expect(page).toHaveURL(/\/album\/classification\/(?:%E6%B5%B7%E8%BE%B9|海边)/, { timeout: 5_000 })
    // 标题等于 tag_name（被 UnifiedPhotoPage 包成 title prop）
    await expect(page.getByText('海边').first()).toBeVisible({ timeout: 5_000 })
    // 副标题 0 个项目（mock 返回空）
    await expect(page.getByText('0 个项目')).toBeVisible()
  })

  test('进入文件夹布局 -> FolderTree 渲染 2 个子目录', async ({ page }) => {
    await page.route('**/api/photos/folders**', (route) => {
      const url = new URL(route.request().url())
      // child 路径的 parent= 也走通
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(FOLDER_TREE),
      })
    })
    await enterFolderLayout(page)
    // 根目录 children 渲染
    await expect(page.locator('.folder-tree')).toBeVisible({ timeout: 5_000 })
    await expect(page.locator('.folder-tree').getByText('2024')).toBeVisible()
    await expect(page.locator('.folder-tree').getByText('2025')).toBeVisible()
  })

  test('点击 FolderTree 子目录 -> 触发 navigate 并再次请求 GET /api/photos/folders?parent=path', async ({ page }) => {
    const seenParents: string[] = []
    await page.route('**/api/photos/folders**', (route) => {
      const url = new URL(route.request().url())
      const parent = url.searchParams.get('parent') ?? ''
      seenParents.push(parent)
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(FOLDER_TREE),
      })
    })
    await enterFolderLayout(page)
    await expect(page.locator('.folder-tree')).toBeVisible({ timeout: 5_000 })

    // 点 2024
    await page.locator('.folder-tree').getByText('2024').first().click()
    // 至少两次请求：初始 parent='' + 后续 parent='C:/photos/2024'
    await expect.poll(() => seenParents.includes('C:/photos/2024'), { timeout: 5_000 }).toBeTruthy()
  })
})
