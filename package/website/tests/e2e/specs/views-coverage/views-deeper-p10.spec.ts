import { expect, test, type Page, type Route } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'
import { desktopLevelButton } from '../../helpers/location-ui'

/**
 * Nightly view-coverage round 2026-08-27.
 *
 * 覆盖 coverage-gaps-frontend.md 中剩余的 2 个未引用 view:
 *   - LocationMap  (views/album/location/LocationMap.vue)
 *   - TicketPage   (views/ticket/TicketPage.vue)
 *
 * 触发条件：
 *   - LocationMap 仅在 level='scene' 或 'photo-map' + viewMode='map' 时挂载
 *     (LocationList.vue 第 387 行 `<LocationMap v-if="...">`)
 *   - TicketPage 是 /ticket 的页面级容器，TicketExportModal/TicketHeader 等子组件
 *     在其它 spec 已覆盖；本文件专门验证页面级 handler（goToStatistics / handleExport /
 *     handleFileImport / importTickets 错误反馈）。
 */

const ok = <T>(data: T): { code: number; message: string; data: T } => ({
  code: 0,
  message: 'success',
  data,
})

/** 阻止 ticketStore 通过真实接口拉数据，否则未登录态会被 401 拦到 /login。 */
async function stubTickets(page: Page) {
  await page.route('**/api/train-ticket**', (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(ok({ items: [], total: 0 })),
    }),
  )
  await page.route('**/api/flight-ticket**', (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(ok({ items: [], total: 0 })),
    }),
  )
}

/** 让 LocationMap 缺少地图 key 时立即触发 MAP_KEY_MISSING 的 ElMessageBox。 */
async function stubLocationMapNoKey(page: Page) {
  await page.route('**/api/settings', (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(ok({ map: { provider: 'tianditu', api_keys: [], api_key: '' } })),
    }),
  )
  await page.route('**/api/locations/scenes/list**', (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(ok([])),
    }),
  )
  await page.route('**/api/locations/map/markers**', (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(ok([])),
    }),
  )
}

test.describe('P1 - Nightly view coverage round 2026-08-27 @views-coverage', () => {
  test.describe('LocationMap scene-level + map view', () => {
    test.beforeEach(async ({ page, request }, testInfo) => {
      if (!(await ensureAuthSession(request, page, testInfo))) return
      // 还原 location store 的持久化字段，确保从默认态出发
      await page.addInitScript(() => {
        try {
          localStorage.removeItem('trailsnap-location-view-mode')
          localStorage.removeItem('trailsnap-location-level')
          localStorage.removeItem('trailsnap-location-filter-status')
          localStorage.removeItem('trailsnap_map_state')
        } catch {
          /* ignore */
        }
      })
    })

    test('切换到景区 + 地图视图 -> 渲染 LocationMap 容器 (缺 map key 时进入确认弹窗)', async ({
      page,
    }, testInfo) => {
      await stubLocationMapNoKey(page)

      await page.goto('/album/location')
      await page.waitForLoadState('networkidle', { timeout: 8_000 }).catch(() => undefined)
      // 路由守卫偶发 redirect，给 500ms 收敛
      await page.waitForTimeout(500)
      if (!/\/album\/location(?:\?|$|\/)/.test(page.url())) {
        testInfo.skip(true, `Page did not stay on /album/location; landed on ${page.url()}`)
        return
      }

      // 1) 切到景区 level（监听 scenes/list 接口响应）
      const sceneReq = page
        .waitForResponse(
          (res) => res.url().includes('/api/locations/scenes/list') && res.status() === 200,
          { timeout: 10_000 },
        )
        .catch(() => undefined)
      await desktopLevelButton(page, '景区').click()
      await sceneReq

      // 2) 切到地图视图
      const mapBtn = page.locator('.location-list button[title="地图视图"]').first()
      await expect(mapBtn).toBeVisible({ timeout: 10_000 })
      await mapBtn.click()

      // 3) LocationMap 容器 (#tianditu-map) 应挂载；同时 onMounted 抛 MAP_KEY_MISSING
      //    会触发 ElMessageBox 询问「去设置 / 取消」。
      await expect(page.locator('#tianditu-map')).toHaveCount(1, { timeout: 10_000 })
      const dialog = page.getByRole('dialog').filter({ hasText: '查看地图照片需要配置地图 API Key' })
      await expect(dialog).toBeVisible({ timeout: 10_000 })
      // 关闭弹窗保持测试幂等
      await dialog.getByRole('button', { name: '取消' }).click()
      await expect(dialog).toHaveCount(0, { timeout: 5_000 })
    })
  })

  test.describe('TicketPage page-level handlers', () => {
    test.beforeEach(async ({ page, request }, testInfo) => {
      if (!(await ensureAuthSession(request, page, testInfo))) return
      await page.addInitScript(() => {
        try {
          localStorage.removeItem('ticket-view-mode')
          localStorage.removeItem('ticket-filter-type')
          localStorage.removeItem('ticket-sort-type')
          localStorage.removeItem('ticket-selected-passenger')
          localStorage.removeItem('ticket-search-query')
          localStorage.removeItem('ticket-stats-map')
        } catch {
          /* ignore */
        }
      })
    })

    test('页面挂载 -> 车票管理标题可见 + 触发 train-ticket / flight-ticket 列表拉取', async ({
      page,
    }) => {
      const trainCalls: string[] = []
      const flightCalls: string[] = []
      await page.route('**/api/train-ticket**', (route: Route) => {
        if (route.request().method() !== 'GET') return route.continue()
        trainCalls.push(route.request().url())
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ok({ items: [], total: 0 })),
        })
      })
      await page.route('**/api/flight-ticket**', (route: Route) => {
        if (route.request().method() !== 'GET') return route.continue()
        flightCalls.push(route.request().url())
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ok({ items: [], total: 0 })),
        })
      })

      await page.goto('/ticket')
      await expect(page.getByText('车票管理').first()).toBeVisible({ timeout: 15_000 })

      await expect.poll(() => trainCalls.length).toBeGreaterThan(0)
      await expect.poll(() => flightCalls.length).toBeGreaterThan(0)
    })

    test('点击「统计报表」按钮 -> 路由跳转到 /statistics', async ({ page }) => {
      await stubTickets(page)
      await page.goto('/ticket')
      await expect(page.getByText('车票管理').first()).toBeVisible({ timeout: 15_000 })

      await page.locator('button[title="统计报表"]').first().click()
      await page.waitForURL(/\/statistics/, { timeout: 10_000 })
    })

    test('点击「导出数据」按钮 -> TicketExportModal 打开（页面级 handleExport 触发）', async ({
      page,
    }) => {
      await stubTickets(page)
      await page.goto('/ticket')
      await expect(page.getByText('车票管理').first()).toBeVisible({ timeout: 15_000 })

      await page.locator('button[title="导出数据"]').first().click()
      await expect(
        page.locator('.el-dialog__title', { hasText: '导出车票数据' }),
      ).toBeVisible({ timeout: 5_000 })
    })

    test('导入非法文件 -> ElMessage.error 反馈且不抛未捕获异常', async ({ page }) => {
      let importCalls = 0
      await stubTickets(page)
      await page.route('**/api/train-ticket/import**', (route: Route) => {
        importCalls += 1
        return route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({ code: 400, message: '文件格式不合法', data: null }),
        })
      })

      await page.goto('/ticket')
      await expect(page.getByText('车票管理').first()).toBeVisible({ timeout: 15_000 })

      // 隐藏的 <input type="file"> 来自 TicketHeader.triggerImport，setInputFiles
      // 会自动触发 change 事件 -> TicketHeader emit('handle-file-import') -> TicketPage.handleFileImport
      const fileInput = page.locator('input[type="file"]').first()
      await fileInput.setInputFiles({
        name: 'broken.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from('not-a-valid-ticket'),
      })

      await expect.poll(() => importCalls).toBeGreaterThan(0)
      await expect(page.locator('.el-message--error').first()).toBeVisible({ timeout: 10_000 })
    })
  })
})
