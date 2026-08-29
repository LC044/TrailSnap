import { expect, test } from '@playwright/test'

test.use({ storageState: { cookies: [], origins: [] } })

test.describe('手机 App 登录服务器选择 @p0', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      ;(window as typeof window & { CapacitorCustomPlatform?: { name: string } }).CapacitorCustomPlatform = {
        name: 'android',
      }
      localStorage.setItem('trailsnap:server-url', 'http://192.168.1.10:8800')
      localStorage.setItem('trailsnap_server_history', JSON.stringify([
        'http://192.168.1.10:8800',
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
    await expect(serverSelect).toHaveValue('http://192.168.1.10:8800')

    const formItems = page.locator('.el-form-item')
    await expect(formItems.nth(0)).toContainText('服务器地址')
    await expect(formItems.nth(1)).toContainText('用户名')
    await expect(formItems.nth(2)).toContainText('密码')

    await serverSelect.click()
    await expect(page.getByRole('option', { name: 'https://photos.example.com' })).toBeVisible()
    await page.getByRole('option', { name: 'https://photos.example.com' }).click()
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
    await serverInput.fill('http://10.0.0.8:8800')
    await page.locator('input[placeholder="请输入用户名"]').fill('test-user')
    await page.locator('input[placeholder="请输入密码"]').fill('password123')
    await page.getByRole('button', { name: '登录' }).click()

    await expect.poll(() => page.evaluate(() => localStorage.getItem('trailsnap:server-url')))
      .toBe('http://10.0.0.8:8800')
    const history = await page.evaluate(() => JSON.parse(localStorage.getItem('trailsnap_server_history') || '[]'))
    expect(history).toEqual([
      'http://10.0.0.8:8800',
      'http://192.168.1.10:8800',
      'https://photos.example.com',
    ])
  })
})

test.describe('手机 App 首次启动 @p0', () => {
  test('未配置服务器时直接进入可填写地址的登录页', async ({ page }) => {
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

    await expect(page).toHaveURL(url => url.pathname === '/login' && url.searchParams.get('redirect') === '/')
    await expect(page.getByTestId('server-address')).toBeVisible()
    await expect(page.getByTestId('server-address')).toHaveValue('')
  })
})

test.describe('手机 App 服务器断连 @p0', () => {
  test('已登录时连接失败会保留服务器地址并返回登录页', async ({ page }) => {
    await page.addInitScript(() => {
      ;(window as typeof window & { CapacitorCustomPlatform?: { name: string } }).CapacitorCustomPlatform = {
        name: 'android',
      }
      localStorage.setItem('trailsnap:server-url', 'http://192.168.1.10:8800')
      localStorage.setItem('user_token', 'expired-offline-session')
    })
    await page.route('http://192.168.1.10:8800/**', route => route.abort('connectionrefused'))

    await page.goto('/photos', { waitUntil: 'domcontentloaded' })

    await expect(page).toHaveURL(url =>
      url.pathname === '/login' &&
      url.searchParams.get('reason') === 'server-unreachable' &&
      url.searchParams.get('redirect') === '/photos',
    )
    await expect(page.getByTestId('server-address')).toHaveValue('http://192.168.1.10:8800')
    await expect.poll(() => page.evaluate(() => localStorage.getItem('user_token'))).toBeNull()
  })
})
