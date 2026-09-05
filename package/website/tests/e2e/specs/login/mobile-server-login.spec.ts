import { expect, test } from '@playwright/test'

test.use({ storageState: { cookies: [], origins: [] } })

test.describe('手机 App 登录服务器选择 @p0', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      ;(window as typeof window & { CapacitorCustomPlatform?: { name: string } }).CapacitorCustomPlatform = {
        name: 'android',
      }
      localStorage.setItem('trailsnap:server-url', 'http://192.168.1.10:8082')
      localStorage.setItem('trailsnap_server_history', JSON.stringify([
        'http://192.168.1.10:8082',
        'https://photos.example.com',
      ]))
    })

    await page.route('**/auth/status', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ has_users: true, allow_registration: false, demo_mode: false }),
    }))
    await page.route('**/api/nav/items', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [] }),
    }))
    await page.route('**/api/notifications/**', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    }))
  })

  test('按服务器、用户名、密码顺序显示，并可选择历史地址', async ({ page }) => {
    await page.goto('/login', { waitUntil: 'domcontentloaded' })

    const serverSelect = page.getByTestId('server-address')
    await expect(serverSelect).toBeVisible()
    await expect(serverSelect).toHaveValue('http://192.168.1.10:8082')

    const formItems = page.locator('.el-form-item')
    await expect(formItems.nth(0)).toContainText('TrailSnap 地址')
    await expect(formItems.nth(1)).toContainText('用户名')
    await expect(formItems.nth(2)).toContainText('密码')

    await serverSelect.click()
    const historyOption = page.locator('[role="option"]:visible', { hasText: 'https://photos.example.com' })
    await expect(historyOption).toBeVisible()
    await historyOption.click()
    await expect(serverSelect).toHaveValue('https://photos.example.com')
  })

  test('登录前保存新地址并加入历史记录', async ({ page }) => {
    await page.route('**/auth/login', route => route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ detail: '用户名或密码错误' }),
    }))
    await page.goto('/login', { waitUntil: 'domcontentloaded' })

    const serverInput = page.getByTestId('server-address')
    await serverInput.fill('http://10.0.0.8:8082')
    await page.locator('input[placeholder="请输入用户名"]').fill('test-user')
    await page.locator('input[placeholder="请输入密码"]').fill('password123')
    await page.getByRole('button', { name: '登录' }).click()

    await expect.poll(() => page.evaluate(() => localStorage.getItem('trailsnap:server-url')))
      .toBe('http://10.0.0.8:8082')
    const history = await page.evaluate(() => JSON.parse(localStorage.getItem('trailsnap_server_history') || '[]'))
    expect(history).toEqual([
      'http://10.0.0.8:8082',
      'http://192.168.1.10:8082',
      'https://photos.example.com',
    ])
  })
})

test.describe('手机 App 首次启动 @p0', () => {
  test('未配置服务器时直接进入支持扫码和发现的连接页', async ({ page }) => {
    await page.addInitScript(() => {
      ;(window as typeof window & { CapacitorCustomPlatform?: { name: string } }).CapacitorCustomPlatform = {
        name: 'android',
      }
      localStorage.clear()
    })
    await page.route('**/api/nav/items', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [] }),
    }))

    await page.goto('/', { waitUntil: 'domcontentloaded' })

    await expect(page).toHaveURL(url => url.pathname === '/server-settings' && url.searchParams.get('redirect') === '/')
    await expect(page.getByRole('button', { name: '扫描二维码' })).toBeVisible()
    await expect(page.getByRole('button', { name: '自动查找 TrailSnap' })).toBeVisible()
  })
})

test.describe('手机 App 天地图瓦片 @p0', () => {
  test('瓦片请求使用已选 TrailSnap 服务器的 nginx 代理', async ({ page }) => {
    await page.addInitScript(() => {
      ;(window as typeof window & { CapacitorCustomPlatform?: { name: string } }).CapacitorCustomPlatform = {
        name: 'android',
      }
      localStorage.setItem('trailsnap:server-url', 'http://192.168.1.10:8082')
      localStorage.setItem('user_token', 'mobile-map-session')
      localStorage.setItem('trailsnap-location-view-mode', 'map')
      localStorage.setItem('trailsnap-location-level', 'scene')

      const tileTemplates: string[] = []
      class MockMap {
        constructor(_element: string, _options?: unknown) {}
        centerAndZoom() {}
        enableScrollWheelZoom() {}
        addEventListener() {}
        removeEventListener() {}
        addOverLay() {}
        clearOverLays() {}
      }
      class MockTileLayer {
        constructor(url: string) {
          tileTemplates.push(url)
        }
      }
      class MockLngLat {
        constructor(_lng: number, _lat: number) {}
      }

      Object.assign(window, {
        __tiandituTileTemplates: tileTemplates,
        T: { Map: MockMap, TileLayer: MockTileLayer, LngLat: MockLngLat },
      })
    })

    await page.route('http://192.168.1.10:8082/**', route => {
      const path = new URL(route.request().url()).pathname
      const data = path === '/api/settings/'
        ? { map: { provider: 'tianditu', api_keys: ['mobile-map-key'] } }
        : path === '/api/nav/items'
          ? { items: [] }
          : []
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, message: 'success', data }),
      })
    })

    await page.goto('/album/location', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('#tianditu-map')).toBeVisible({ timeout: 10_000 })
    await expect.poll(() => page.evaluate(() => (
      (window as typeof window & { __tiandituTileTemplates?: string[] }).__tiandituTileTemplates || []
    ))).toEqual([
      'http://192.168.1.10:8082/api/system/map-proxy/t0.tianditu.gov.cn/DataServer?T=vec_w&x={x}&y={y}&l={z}&tk=mobile-map-key',
      'http://192.168.1.10:8082/api/system/map-proxy/t0.tianditu.gov.cn/DataServer?T=cva_w&x={x}&y={y}&l={z}&tk=mobile-map-key',
    ])
  })
})

test.describe('手机 App 服务器断连 @p0', () => {
  test('已登录时瞬时连接失败会保留会话和当前页面', async ({ page }) => {
    await page.addInitScript(() => {
      ;(window as typeof window & { CapacitorCustomPlatform?: { name: string } }).CapacitorCustomPlatform = {
        name: 'android',
      }
      localStorage.setItem('trailsnap:server-url', 'http://192.168.1.10:8082')
      localStorage.setItem('user_token', 'expired-offline-session')
    })
    await page.route('http://192.168.1.10:8082/**', route => route.abort('connectionrefused'))

    await page.goto('/photos', { waitUntil: 'domcontentloaded' })

    await expect(page).toHaveURL(url => url.pathname === '/photos')
    await expect.poll(() => page.evaluate(() => localStorage.getItem('trailsnap:server-url')))
      .toBe('http://192.168.1.10:8082')
    await expect.poll(() => page.evaluate(() => localStorage.getItem('user_token')))
      .toBe('expired-offline-session')
  })
})
