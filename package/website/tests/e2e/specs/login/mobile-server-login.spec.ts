import { expect, test } from '@playwright/test'

test.use({ storageState: { cookies: [], origins: [] } })

test.describe('手机 App 登录服务器选择 @p0', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      ;(window as typeof window & { CapacitorCustomPlatform?: { name: string } }).CapacitorCustomPlatform = {
        name: 'android',
      }
      localStorage.setItem('trailsnap:server-url', 'http://192.168.1.10:3180')
      localStorage.setItem('trailsnap_server_history', JSON.stringify([
        'http://192.168.1.10:3180',
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
    await expect(serverSelect).toHaveValue('http://192.168.1.10:3180')

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
    await serverInput.fill('http://10.0.0.8:3180')
    await page.locator('input[placeholder="请输入用户名"]').fill('test-user')
    await page.locator('input[placeholder="请输入密码"]').fill('password123')
    await page.getByRole('button', { name: '登录' }).click()

    await expect.poll(() => page.evaluate(() => localStorage.getItem('trailsnap:server-url')))
      .toBe('http://10.0.0.8:3180')
    const history = await page.evaluate(() => JSON.parse(localStorage.getItem('trailsnap_server_history') || '[]'))
    expect(history).toEqual([
      'http://10.0.0.8:3180',
      'http://192.168.1.10:3180',
      'https://photos.example.com',
    ])
  })

  test('已配置旧 Server 时可测试并保存扫码得到的新 Server', async ({ page }) => {
    const newServer = 'http://192.168.1.20:3180'
    await page.route(`${newServer}/api/health-check`, route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 0, message: 'success', data: {} }),
    }))

    await page.goto(`/server-settings?url=${encodeURIComponent(newServer)}`, { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: '测试并保存' }).click()

    await expect(page.locator('p.text-green-600')).toContainText('连接成功')
    await expect.poll(() => page.evaluate(() => localStorage.getItem('trailsnap:server-url')))
      .toBe(newServer)
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
  test('瓦片请求使用已选 TrailSnap 服务器的服务端 Key 代理', async ({ page }) => {
    await page.addInitScript(() => {
      ;(window as typeof window & { CapacitorCustomPlatform?: { name: string } }).CapacitorCustomPlatform = {
        name: 'android',
      }
      localStorage.setItem('trailsnap:server-url', 'http://192.168.1.10:3180')
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

    await page.route('http://192.168.1.10:3180/**', route => {
      const path = new URL(route.request().url()).pathname
      const data = path === '/api/settings/map/runtime'
        ? { provider: 'tianditu', access_token: 'scoped-map-token' }
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
      'http://192.168.1.10:3180/api/system/map-proxy/scoped-map-token/t0.tianditu.gov.cn/DataServer?T=vec_w&x={x}&y={y}&l={z}',
      'http://192.168.1.10:3180/api/system/map-proxy/scoped-map-token/t0.tianditu.gov.cn/DataServer?T=cva_w&x={x}&y={y}&l={z}',
    ])
  })
})

test.describe('手机 App 服务器断连 @p0', () => {
  test('已登录时瞬时连接失败会保留会话和当前页面', async ({ page }) => {
    await page.addInitScript(() => {
      ;(window as typeof window & { CapacitorCustomPlatform?: { name: string } }).CapacitorCustomPlatform = {
        name: 'android',
      }
      localStorage.setItem('trailsnap:server-url', 'http://192.168.1.10:3180')
      localStorage.setItem('user_token', 'expired-offline-session')
    })
    await page.route('http://192.168.1.10:3180/**', route => route.abort('connectionrefused'))

    await page.goto('/photos', { waitUntil: 'domcontentloaded' })

    await expect(page).toHaveURL(url => url.pathname === '/photos')
    await expect.poll(() => page.evaluate(() => localStorage.getItem('trailsnap:server-url')))
      .toBe('http://192.168.1.10:3180')
    await expect.poll(() => page.evaluate(() => localStorage.getItem('user_token')))
      .toBe('expired-offline-session')
  })

  test('连接页收到 401 时静默清除过期登录态，不踢回登录页', async ({ page }) => {
    await page.addInitScript(() => {
      ;(window as typeof window & { CapacitorCustomPlatform?: { name: string } }).CapacitorCustomPlatform = {
        name: 'android',
      }
      localStorage.setItem('trailsnap:server-url', 'http://192.168.1.10:3180')
      localStorage.setItem('user_token', 'expired-token-before-server-switch')
    })
    // 后台请求（nav items 等）带过期 token 吃到 401，但连接页必须可用——
    // 用户正是为了登录才来切换服务器，踢回 /login 会形成死循环。
    await page.route('http://192.168.1.10:3180/**', route => route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Not authenticated' }),
    }))

    await page.goto('/server-settings', { waitUntil: 'domcontentloaded' })

    await expect(page).toHaveURL(url => url.pathname === '/server-settings')
    await expect(page.getByRole('button', { name: '测试并保存' })).toBeVisible()
    // 过期 token 已被静默清除，而不是触发"登录已过期"跳转。
    await expect.poll(() => page.evaluate(() => localStorage.getItem('user_token'))).toBeNull()
  })

  test('受保护页面收到 401 仍会退出并跳转登录页', async ({ page }) => {
    await page.addInitScript(() => {
      ;(window as typeof window & { CapacitorCustomPlatform?: { name: string } }).CapacitorCustomPlatform = {
        name: 'android',
      }
      localStorage.setItem('trailsnap:server-url', 'http://192.168.1.10:3180')
      localStorage.setItem('user_token', 'expired-token-on-protected-page')
      localStorage.setItem('user_info', JSON.stringify({ id: 1, username: 'e2e-admin' }))
    })
    await page.route('http://192.168.1.10:3180/**', route => route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Not authenticated' }),
    }))

    await page.goto('/photos', { waitUntil: 'domcontentloaded' })

    // 正常的过期处理：清 token 并回到登录页。
    await expect(page).toHaveURL(url => url.pathname === '/login', { timeout: 10_000 })
    await expect.poll(() => page.evaluate(() => localStorage.getItem('user_token'))).toBeNull()
  })
})
