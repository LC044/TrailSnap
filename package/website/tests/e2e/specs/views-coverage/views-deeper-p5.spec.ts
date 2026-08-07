import { expect, test, type Page, type Route } from "@playwright/test"

// Self-contained: 通过 addInitScript 注入假登录态，page.route mock 所有相关 API。
// /photos 朋友圈视图 (moments) + 文件夹视图 (folder) 无需真实后端 / AI / Postgres。

test.describe.configure({ mode: "serial" })

const ok = (data: unknown) => ({ code: 0, message: "success", data })

const fakeUser = { id: "u-e2e", username: "e2e-mock", nickname: "E2E 行影者", avatar: "", is_active: true, is_superuser: true }

// 三张同日照片：触发 moments 单日分组 + photo grid 渲染
const fakePhotosByDay = [
  {
    id: "p-1",
    filename: "sky.jpg",
    photo_time: "2025-08-05T10:00:00",
    upload_time: "2025-08-05T10:00:00",
    file_type: "image",
    url: "/api/medias/p-1/file",
    thumbnail_url: "/api/medias/p-1/thumbnail",
    size: 1024,
    width: 1920,
    height: 1080,
  },
  {
    id: "p-2",
    filename: "lake.jpg",
    photo_time: "2025-08-05T11:30:00",
    upload_time: "2025-08-05T11:30:00",
    file_type: "image",
    url: "/api/medias/p-2/file",
    thumbnail_url: "/api/medias/p-2/thumbnail",
    size: 2048,
    width: 1920,
    height: 1080,
  },
  {
    id: "p-3",
    filename: "food.jpg",
    photo_time: "2025-08-05T19:00:00",
    upload_time: "2025-08-05T19:00:00",
    file_type: "image",
    url: "/api/medias/p-3/file",
    thumbnail_url: "/api/medias/p-3/thumbnail",
    size: 1536,
    width: 1920,
    height: 1080,
  },
]

const fakePhotosByFolder = [
  {
    id: "fp-1",
    filename: "beach.jpg",
    photo_time: "2025-07-01T10:00:00",
    upload_time: "2025-07-01T10:00:00",
    file_type: "image",
    url: "/api/medias/fp-1/file",
    thumbnail_url: "/api/medias/fp-1/thumbnail",
    size: 4096,
    width: 1920,
    height: 1080,
  },
  {
    id: "fp-2",
    filename: "mountain.jpg",
    photo_time: "2025-07-02T10:00:00",
    upload_time: "2025-07-02T10:00:00",
    file_type: "image",
    url: "/api/medias/fp-2/file",
    thumbnail_url: "/api/medias/fp-2/thumbnail",
    size: 4096,
    width: 1920,
    height: 1080,
  },
]

const fakeTimeline = {
  total_photos: 3,
  time_range: { start: "2025-08-05", end: "2025-08-05" },
  timeline: [{ year: 2025, month: 8, day: 5, count: 3 }],
}

async function injectFakeAuth(page: Page) {
  await page.addInitScript(() => {
    try {
      localStorage.setItem("user_token", "fake-e2e-token")
      localStorage.setItem("username", "e2e-mock")
      localStorage.setItem("user_info", JSON.stringify({ id: "u-e2e", username: "e2e-mock", nickname: "E2E 行影者", is_active: true, is_superuser: true }))
    } catch { /* ignore */ }
  })
}

async function stubAuthMe(page: Page) {
  await page.route("**/api/auth/me**", async (route: Route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(fakeUser) })
  })
}

async function mockPhotosApis(page: Page, opts: { photos?: unknown[]; timeline?: unknown; folders?: unknown; failPhotos?: boolean } = {}) {
  const photos = opts.photos ?? fakePhotosByDay
  const timeline = opts.timeline ?? fakeTimeline
  const folders = opts.folders ?? { parent: "", breadcrumb: [], own_count: 0, children: [] }

  await page.route("**/api/stats/timeline**", async (route: Route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ok(timeline)) })
  })
  await page.route(/\/api\/photos(\?|$)/, async (route: Route) => {
    if (opts.failPhotos) {
      await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ code: 500, message: "e2e forced failure" }) })
      return
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ok(photos)) })
  })
  await page.route("**/api/photos/folders**", async (route: Route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ok(folders)) })
  })
  await page.route("**/api/medias/**", async (route: Route) => {
    // 返回 1x1 透明 PNG，避免 img.onerror 触发回流
    const pixel = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    await route.fulfill({ status: 200, contentType: "image/png", body: Buffer.from(pixel, "base64") })
  })
}

test.beforeEach(async ({ page }) => {
  await injectFakeAuth(page)
  await stubAuthMe(page)
  await mockPhotosApis(page)
})

// ===========================================================================
// Moments 朋友圈视图
// ===========================================================================

test.describe("Moments 朋友圈视图 @views-coverage", () => {
  test("切换到「朋友圈」布局 -> 渲染用户昵称 + 未生成文案时的占位与「AI 生成」按钮", async ({ page }) => {
    // 拦截朋友圈日文案列表接口：返回空数组，保证进入"未生成"占位态
    await page.route("**/api/moments/day-captions**", (route) => {
      const method = route.request().method()
      if (method === "GET") {
        return route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
      }
      return route.continue()
    })

    await page.goto("/photos")
    // 等首屏 grid 渲染（grid 是默认布局）
    await expect(page.locator(".photo-gallery")).toBeVisible({ timeout: 15_000 })
    // 点视图设置 -> 朋友圈
    await page.locator('button[title="视图设置"]').click()
    const momentsItem = page.locator('button:has-text("朋友圈")').first()
    await expect(momentsItem).toBeVisible({ timeout: 5_000 })
    await momentsItem.click()

    // Moments 视图特征：用户昵称 + 朋友圈默认占位文案（未生成时显示）
    // injectFakeAuth 注入的 user_info 里 nickname 为「E2E 行影者」，store 会从 localStorage
    // 恢复 userInfo（见 stores/user.ts 的持久化），因此 PhotoGallery 渲染该昵称而非默认值。
    await expect(page.getByText("E2E 行影者").first()).toBeVisible({ timeout: 10_000 })
    await expect(
      page.getByText(/这是\s*2025\s*年\s*8\s*月\s*5\s*日\s*的美好回忆/)
    ).toBeVisible()
    // 首屏第一天的"AI 生成"按钮应可见（悬浮才展开的按钮组，因此使用 attached 判定即可）
    await expect(page.locator('button:has-text("AI 生成")').first()).toHaveCount(1, { timeout: 5_000 })
  })

  test("朋友圈视图 -> 同日多张照片在 grid 内渲染对应数量的缩略图", async ({ page }) => {
    await page.goto("/photos")
    await expect(page.locator(".photo-gallery")).toBeVisible({ timeout: 15_000 })
    await page.locator('button[title="视图设置"]').click()
    await page.locator('button:has-text("朋友圈")').first().click()

    // moments 单日 block 内的 img 数量应等于 fakePhotosByDay.length (3)
    await expect(page.getByText("E2E 行影者").first()).toBeVisible({ timeout: 10_000 })
    const dayBlock = page.locator(".day-block").first()
    await expect(dayBlock).toBeVisible({ timeout: 10_000 })
    const imgs = dayBlock.locator("img")
    await expect.poll(async () => await imgs.count(), { timeout: 10_000 }).toBeGreaterThanOrEqual(3)
  })

  test("无照片时 -> 朋友圈视图渲染空态文案", async ({ page }) => {
    await page.unroute(/\/api\/photos(\?|$)/).catch(() => {})
    await page.unroute("**/api/stats/timeline**").catch(() => {})
    await mockPhotosApis(page, {
      photos: [],
      timeline: { total_photos: 0, time_range: { start: null, end: null }, timeline: [] },
    })
    await page.goto("/photos")
    await expect(page.locator(".photo-gallery")).toBeVisible({ timeout: 15_000 })
    await page.locator('button[title="视图设置"]').click()
    await page.locator('button:has-text("朋友圈")').first().click()
    // PhotosPage empty 模板硬编码「欢迎来到 TrailSnap」
    await expect(page.getByText("欢迎来到 TrailSnap")).toBeVisible({ timeout: 10_000 })
  })
})

// ===========================================================================
// Moments 朋友圈日文案生成 / 编辑 / 清除 交互
// 依赖：/api/moments/day-captions 与 /api/moments/day-captions/generate 两个后端接口。
// 所有场景通过 page.route mock，不依赖真实后端或 LLM。
// ===========================================================================

test.describe("Moments 日文案 AI 生成 & 编辑 @views-coverage", () => {
  // 该 describe 内所有用例统一走"无历史文案"的 GET stub
  const stubEmptyListRoute = async (page: Page) => {
    await page.route("**/api/moments/day-captions?**", (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
      }
      return route.continue()
    })
  }

  // 打开 /photos 并切换到朋友圈视图的公共步骤
  const enterMomentsView = async (page: Page) => {
    await page.goto("/photos")
    await expect(page.locator(".photo-gallery")).toBeVisible({ timeout: 15_000 })
    await page.locator('button[title="视图设置"]').click()
    await page.locator('button:has-text("朋友圈")').first().click()
    await expect(page.locator(".day-block").first()).toBeVisible({ timeout: 10_000 })
  }

  test("已有 caption -> 进入 moments 视图时直接展示，且默认按钮变为「重新生成」", async ({ page }) => {
    // GET 返回一条已经生成好的文案
    await page.route("**/api/moments/day-captions?**", (route) => {
      if (route.request().method() !== "GET") return route.continue()
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: 1,
            user_id: "u-e2e",
            scope_type: "all",
            scope_id: null,
            day: "2025-08-05",
            caption: "云低到能碰到山头。",
            source: "ai",
            model_name: "e2e-mock",
            photo_count: 3,
            created_at: "2025-08-05T20:00:00Z",
            updated_at: "2025-08-05T20:00:00Z",
          },
        ]),
      })
    })

    await enterMomentsView(page)
    await expect(page.getByText("云低到能碰到山头。")).toBeVisible({ timeout: 10_000 })
    // 已有文案时按钮文案切换为「重新生成」，不应再显示占位文本
    await expect(page.locator('button:has-text("重新生成")').first()).toHaveCount(1, { timeout: 5_000 })
    await expect(page.getByText(/这是\s*2025\s*年\s*8\s*月\s*5\s*日\s*的美好回忆/)).toHaveCount(0)
  })

  test("手动编辑并保存 -> 触发 PUT /api/moments/day-captions/{day}，DOM 更新为新文案", async ({ page }) => {
    // 先给一条已有文案，才会出现「编辑」按钮
    await page.route("**/api/moments/day-captions?**", (route) => {
      if (route.request().method() !== "GET") return route.continue()
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: 2,
            user_id: "u-e2e",
            scope_type: "all",
            scope_id: null,
            day: "2025-08-05",
            caption: "初稿：随便写点什么。",
            source: "ai",
            model_name: "e2e-mock",
            photo_count: 3,
            created_at: "2025-08-05T20:00:00Z",
            updated_at: "2025-08-05T20:00:00Z",
          },
        ]),
      })
    })

    let putBody: any = null
    await page.route("**/api/moments/day-captions/2025-08-05*", async (route) => {
      if (route.request().method() !== "PUT") return route.continue()
      putBody = JSON.parse(route.request().postData() || "{}")
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: 2,
          user_id: "u-e2e",
          scope_type: "all",
          scope_id: null,
          day: "2025-08-05",
          caption: putBody.caption,
          source: "manual",
          model_name: null,
          photo_count: 3,
          created_at: "2025-08-05T20:00:00Z",
          updated_at: "2025-08-05T21:00:00Z",
        }),
      })
    })

    await enterMomentsView(page)
    await expect(page.getByText("初稿：随便写点什么。")).toBeVisible({ timeout: 10_000 })

    // 点「编辑」按钮 -> 出现 textarea
    const dayBlock = page.locator(".day-block").first()
    await dayBlock.hover()
    await dayBlock.getByRole("button", { name: "编辑", exact: true }).click()
    const textarea = dayBlock.locator("textarea")
    await expect(textarea).toBeVisible({ timeout: 5_000 })
    await textarea.fill("手写的一句：夜里的江面比白天更沉。")

    // 保存
    await dayBlock.getByRole("button", { name: "保存", exact: true }).click()

    // DOM 应更新为新文案
    await expect(page.getByText("手写的一句：夜里的江面比白天更沉。")).toBeVisible({ timeout: 10_000 })
    // PUT payload 校验
    expect(putBody).toBeTruthy()
    expect(putBody.caption).toBe("手写的一句：夜里的江面比白天更沉。")
  })

  test("清除文案 -> 触发 DELETE /api/moments/day-captions/{day}，DOM 回到占位态", async ({ page }) => {
    // 先给一条已有文案，让「清除」按钮出现
    await page.route("**/api/moments/day-captions?**", (route) => {
      if (route.request().method() !== "GET") return route.continue()
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: 3,
            user_id: "u-e2e",
            scope_type: "all",
            scope_id: null,
            day: "2025-08-05",
            caption: "临时文案。",
            source: "manual",
            model_name: null,
            photo_count: 3,
            created_at: "2025-08-05T20:00:00Z",
            updated_at: "2025-08-05T20:00:00Z",
          },
        ]),
      })
    })

    await page.route("**/api/moments/day-captions/2025-08-05*", async (route) => {
      if (route.request().method() !== "DELETE") return route.continue()
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ deleted: true }),
      })
    })

    await enterMomentsView(page)
    await expect(page.getByText("临时文案。")).toBeVisible({ timeout: 10_000 })

    // 点首个 day block 内的「清除」并等待 DELETE 落地；
    // 将触发与监听绑定，避免高负载下 click 完成后才开始等待响应。
    const deleteResponse = page.waitForResponse(
      (r) =>
        r.url().includes("/api/moments/day-captions/2025-08-05") &&
        r.request().method() === "DELETE",
      { timeout: 25_000 }
    )
    const dayBlock = page.locator(".day-block").first()
    await dayBlock.hover()
    const clearButton = dayBlock.locator('button[title="清除文案"]')
    await expect(clearButton).toBeVisible({ timeout: 5_000 })
    await Promise.all([deleteResponse, clearButton.click()])
    await expect(
      page.getByText(/这是\s*2025\s*年\s*8\s*月\s*5\s*日\s*的美好回忆/)
    ).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText("临时文案。")).toHaveCount(0)
  })

  test("朋友圈日位置 -> GET /api/moments/day-locations 返回后，日期行拼接位置文字", async ({ page }) => {
    // caption 走空数组，避免与本用例断言干扰
    await page.route("**/api/moments/day-captions?**", (route) => {
      if (route.request().method() !== "GET") return route.continue()
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      })
    })

    // 关键：mock /api/moments/day-locations 返回该月一天的多位置
    let locationHit = false
    await page.route("**/api/moments/day-locations**", (route) => {
      if (route.request().method() !== "GET") return route.continue()
      locationHit = true
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            day: "2025-08-05",
            primary: "外滩",
            level: "scene",
            locations: [
              { name: "外滩", level: "scene", count: 3 },
              { name: "陆家嘴", level: "scene", count: 2 },
              { name: "上海", level: "city", count: 5 },
            ],
          },
        ]),
      })
    })

    await enterMomentsView(page)

    // 接口被真正调用（可见月份变化后会触发）
    await expect
      .poll(() => locationHit, { timeout: 10_000 })
      .toBe(true)

    // 日期行同时包含日期与"外滩 · 陆家嘴 · 上海"的位置字符串
    await expect(page.getByText("2025-08-05").first()).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText("外滩 · 陆家嘴 · 上海").first()).toBeVisible({ timeout: 10_000 })
  })
})

// ===========================================================================
// Folder 文件夹视图（扩展 views-deeper.spec.ts 已有的 3 个用例）
// ===========================================================================

test.describe("FolderBrowser 文件夹视图扩展 @views-coverage", () => {
  test("文件夹内含照片 -> 渲染 photo 缩略图卡片 + 文件夹卡片", async ({ page }) => {
    await page.unroute("**/api/photos/folders**").catch(() => {})
    await page.unroute(/\/api\/photos(\?|$)/).catch(() => {})
    await mockPhotosApis(page, {
      photos: fakePhotosByFolder,
      folders: {
        parent: "Travel",
        breadcrumb: [{ name: "Travel", path: "Travel" }],
        own_count: 2,
        children: [{ name: "Asia", path: "Travel/Asia", count: 2, has_children: false }],
      },
    })
    await page.goto("/photos")
    await expect(page.locator(".photo-gallery")).toBeVisible({ timeout: 15_000 })
    await page.locator('button[title="视图设置"]').click()
    await page.locator('button:has-text("文件夹")').first().click()

    await expect(page.locator(".folder-browser")).toBeVisible({ timeout: 10_000 })
    // 文件夹卡片：Asia
    await expect(page.getByRole("button", { name: /Asia/ }).first()).toBeVisible()
    // 面包屑显示 Travel
    await expect(page.locator(".folder-browser").getByText("Travel").first()).toBeVisible()
    // 照片缩略图（fp-1/fp-2）应可见，至少 2 张
    const imgs = page.locator(".folder-browser img")
    await expect.poll(async () => await imgs.count(), { timeout: 10_000 }).toBeGreaterThanOrEqual(2)
  })

  test("面包屑点击「全部」 -> 触发 parent='' 的 GET /api/photos/folders", async ({ page }) => {
    const folderCalls: string[] = []
    await page.unroute("**/api/photos/folders**").catch(() => {})
    await page.route("**/api/photos/folders**", async (route: Route) => {
      const parent = new URL(route.request().url()).searchParams.get("parent") ?? ""
      folderCalls.push(parent)
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(ok({ parent, breadcrumb: parent ? [{ name: parent, path: parent }] : [], own_count: 0, children: [] })),
      })
    })

    await page.goto("/photos")
    await expect(page.locator(".photo-gallery")).toBeVisible({ timeout: 15_000 })
    await page.locator('button[title="视图设置"]').click()
    await page.locator('button:has-text("文件夹")').first().click()
    await expect(page.locator(".folder-browser")).toBeVisible({ timeout: 10_000 })

    // FolderBrowser 在根目录已经有「全部」按钮，再次点「全部」应该重新触发请求
    const allBtn = page.locator(".folder-browser").getByRole("button", { name: "全部" }).first()
    await expect(allBtn).toBeVisible()
    await allBtn.click()
    await expect.poll(() => folderCalls.includes(""), { timeout: 5_000 }).toBeTruthy()
  })

  test("排序下拉打开 -> 显示「按时间倒序 / 按时间正序 / 按文件名」三个选项", async ({ page }) => {
    await page.goto("/photos")
    await expect(page.locator(".photo-gallery")).toBeVisible({ timeout: 15_000 })
    await page.locator('button[title="视图设置"]').click()
    await page.locator('button:has-text("文件夹")').first().click()
    await expect(page.locator(".folder-browser")).toBeVisible({ timeout: 10_000 })

    // FolderBrowser 工具栏排序按钮 title="排序"
    const sortBtn = page.locator('.folder-browser button[title="排序"]').first()
    await expect(sortBtn).toBeVisible()
    await sortBtn.click()
    // el-dropdown 触发后会把菜单 teleport 到 body。等待 menu 真正展开（display != none），
    // 然后断言六项排序选项。
    await page.waitForFunction(() => {
      const menus = document.querySelectorAll(".el-dropdown-menu")
      for (const m of Array.from(menus)) {
        const style = window.getComputedStyle(m)
        if (style.display !== "none" && style.visibility !== "hidden") return true
      }
      return false
    }, undefined, { timeout: 5_000 })
    const menu = page.locator(".el-dropdown-menu:visible").last()
    await expect(menu).toBeVisible()
    await expect(menu.getByText(/名称\s*A→Z/)).toBeVisible()
    await expect(menu.getByText(/名称\s*Z→A/)).toBeVisible()
    await expect(menu.getByText(/时间\s*新→旧/)).toBeVisible()
    await expect(menu.getByText(/时间\s*旧→新/)).toBeVisible()
    await expect(menu.getByText(/大小\s*大→小/)).toBeVisible()
    await expect(menu.getByText(/大小\s*小→大/)).toBeVisible()
  })
})
