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

// /api/tags/clip/categories mock：一组人物 CLIP 类别 + 一个空分组，验证列表只显示大组
const CLIP_CATEGORIES_RESPONSE = {
  code: 0,
  message: 'success',
  data: {
    groups: ['人物', '自然风景'],
    categories: [
      { id: 'cat-1', tag_id: 'tag-clip-1', name: '自拍', groups: ['人物'], enabled: false, revision: 1, descriptions: ['自拍照'], strictness: 'standard', thresholds: {}, builtin: true, count: 5, calibration: { status: 'reviewed' } },
      { id: 'cat-2', tag_id: 'tag-clip-2', name: '多人合照', groups: ['人物'], enabled: false, revision: 1, descriptions: ['合影'], strictness: 'standard', thresholds: {}, builtin: true, count: 0, calibration: { status: 'limited' } },
    ],
  },
}

const TAG_PHOTOS_RESPONSE: any[] = []

function mockTags(route: Route) {
  return route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ code: 0, message: 'success', data: TAGS_RESPONSE }),
  })
}

function mockClipCategories(route: Route) {
  return route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(CLIP_CATEGORIES_RESPONSE),
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
  // 首个页面等待 Vite 冷编译；避免默认 30s 把启动页误判为失败。
  test.setTimeout(120_000)

  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return
  })

  test('进入 /album/classification -> 渲染大组卡片 + 返回按钮不可见', async ({ page }) => {
    await page.route('**/api/tags**', (route) => {
      const u = new URL(route.request().url())
      // /api/tags/:name/photos 也命中；空 photos 也走 mock
      if (/\/photos$/.test(u.pathname)) return mockTagPhotos(route)
      return mockTags(route)
    })
    await page.route('**/api/tags/clip/categories', mockClipCategories)
    await page.goto('/album/classification', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('body')).toBeVisible()
    // 标题"智能分类"
    await expect(page.getByRole('heading', { name: '智能分类' })).toBeVisible({ timeout: 15_000 })
    // 列表只显示大组卡片：人物（CLIP 有计数类别）+ YOLO / 自定义分类（mock 的两个标签）
    // 自然风景组的两个类别计数都为 0，不应出现
    const groupGrid = page.locator('[data-testid="classification-group-grid"]')
    await expect(groupGrid).toBeVisible({ timeout: 15_000 })
    await expect(groupGrid.getByTestId('classification-group-人物')).toBeVisible()
    await expect(groupGrid.getByTestId('classification-group-YOLO / 自定义分类')).toBeVisible()
    await expect(groupGrid.getByTestId('classification-group-自然风景')).toHaveCount(0)
    // 智能分类是一级页面，不显示返回相册按钮。
    const backBtn = page.getByRole('button', { name: '返回相册', exact: true })
    await expect(backBtn).toHaveCount(0)
  })

  test('点击大组 -> 跳 /album/classification/group/:group + 类别网格与标题正确', async ({ page }) => {
    await page.route('**/api/tags**', (route) => {
      const u = new URL(route.request().url())
      if (/\/photos$/.test(u.pathname)) return mockTagPhotos(route)
      return mockTags(route)
    })
    await page.route('**/api/tags/clip/categories', mockClipCategories)
    await page.goto('/album/classification', { waitUntil: 'domcontentloaded' })
    await expect(page.getByTestId('classification-group-人物')).toBeVisible({ timeout: 15_000 })

    // 点大组卡片
    await page.getByTestId('classification-group-人物').click()
    await expect(page).toHaveURL(/\/album\/classification\/group\//, { timeout: 5_000 })
    // 分组详情页：标题等于分组名，类别网格显示该组的类别
    await expect(page.getByText('人物').first()).toBeVisible({ timeout: 5_000 })
    const strip = page.getByTestId('classification-category-strip')
    await expect(strip).toBeVisible()
    // 计数为 0 的「多人合照」不显示
    await expect(strip.getByTestId('classification-category-自拍')).toBeVisible()
    await expect(strip.getByTestId('classification-category-多人合照')).toHaveCount(0)
    // 类别少（1 个，一行内），不出现折叠/展开按钮
    await expect(page.getByTestId('classification-category-toggle')).toHaveCount(0)
    // 副标题 0 个项目（mock 返回空照片）
    await expect(page.getByText('0 个项目')).toBeVisible()
  })

  test('类别超过一行 -> 折叠为一行 + 展开按钮控制', async ({ page }) => {
    // 40 个类别（桌面 1280 宽、tile 68+8 ≈ 每行 14 个 → 3 行），必然超过折叠的一行
    const manyCategories = Array.from({ length: 40 }, (_, i) => ({
      id: `cat-${i + 1}`, tag_id: `tag-clip-${i + 1}`, name: `类别${String(i + 1).padStart(2, '0')}`,
      groups: ['人物'], enabled: false, revision: 1, descriptions: ['x'], strictness: 'standard',
      thresholds: {}, builtin: true, count: i + 1, calibration: { status: 'reviewed' },
    }))
    await page.route('**/api/tags**', (route) => {
      const u = new URL(route.request().url())
      if (/\/photos$/.test(u.pathname)) return mockTagPhotos(route)
      return mockTags(route)
    })
    await page.route('**/api/tags/clip/categories', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, message: 'success', data: { groups: ['人物'], categories: manyCategories } }),
      }),
    )
    await page.goto('/album/classification/group/人物', { waitUntil: 'domcontentloaded' })
    const strip = page.getByTestId('classification-category-strip')
    await expect(strip).toBeVisible({ timeout: 15_000 })
    await expect(strip.locator('.category-tile')).toHaveCount(40, { timeout: 15_000 })

    // 第二行首个 tile（1280 宽下每行约 16 个）是否被折叠高度裁剪（超出网格底边）
    const isTileClipped = () => page.evaluate(() => {
      const grid = document.querySelector('[data-testid="classification-category-strip"]')
      const tile = document.querySelector('[data-testid="classification-category-类别20"]')
      if (!grid || !tile) return false
      return tile.getBoundingClientRect().top >= grid.getBoundingClientRect().bottom - 1
    })

    // 默认折叠：网格限高一行（overflow hidden + max-height 一行），第二行被裁剪
    await expect(strip).toHaveClass(/is-collapsed/)
    await expect(isTileClipped()).resolves.toBeTruthy()
    // 展开按钮出现且显示总数
    const toggle = page.getByTestId('classification-category-toggle')
    await expect(toggle).toBeVisible()
    await expect(toggle).toContainText('40 个类别')

    // 点击展开：限高移除，最后一个 tile 可见
    await toggle.click()
    await expect(strip).not.toHaveClass(/is-collapsed/)
    await expect(strip.getByTestId('classification-category-类别40')).toBeVisible()

    // 再点收起：恢复折叠并重新裁剪
    await toggle.click()
    await expect(strip).toHaveClass(/is-collapsed/)
    await expect(isTileClipped()).resolves.toBeTruthy()
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
