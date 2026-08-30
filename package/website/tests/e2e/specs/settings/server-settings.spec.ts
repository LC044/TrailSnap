import { test, expect, type Page } from '@playwright/test';

/**
 * ServerSettings 页面冒烟测试 — src/views/ServerSettings.vue
 *
 * 该页面是路由 /server-settings 的白名单页面（layout: 'blank'），用于自托管客户端
 * 配置后端地址。本 spec 验证：
 *   - 页面能加载、关键元素可见
 *   - 输入地址 + 点击 "测试并保存" 触发 /api/health-check 调用
 *   - HTTP 200 路径下保存到 localStorage 并跳转
 *   - HTTP 失败路径下显示错误信息并不跳转
 *
 * 已知陷阱（§4.6 / §5.3 测试覆盖原则）：
 *   - App.vue 在 setup 时无条件调用 provideNavItems()，其内部 fetchItems() 立刻打
 *     GET /api/nav/items。空 storageState + 后端在线时，该请求会拿到 401，进入
 *     axios 401 拦截器 -> userStore.resetState() -> router.push('/login')，把
 *     用户踢出 /server-settings。这里提前用 page.route() 拦截 /nav/items 让它
 *     返回空 200，屏蔽该副作用，让 4 个用例都按"未登录场景"路径验证。
 *   - Element Plus 全局 el-message 也会带 role="alert"，但渲染为 <div>；
 *     表单自身 errorMessage 是 <p role="alert" class="text-red-600">，可用
 *     "p[role="alert"].text-red-600" 锁定。绿色成功提示同理用 "p.text-green-600"。
 */
test.use({ storageState: { cookies: [], origins: [] } });

const DEFAULT_API = 'http://127.0.0.1:8082';

async function gotoServerSettings(page: Page) {
  // 拦截认证相关副作用请求，避免 401 拦截器把页面踢到 /login
  await page.route('**/api/nav/items', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) })
  );
  await page.route('**/api/notifications/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  );

  await page.goto('/server-settings', { waitUntil: 'domcontentloaded' });
  await page.getByRole('heading', { name: '连接 TrailSnap', level: 1 }).waitFor({ timeout: 15_000 });
}

test.describe('Smoke - ServerSettings 配置自托管服务 @smoke', () => {
  test('页面打开 - 渲染「连接 TrailSnap」标题与表单骨架', async ({ page }) => {
    await gotoServerSettings(page);

    await expect(page.locator('input[placeholder*="192.168"]')).toBeVisible();
    await expect(page.getByRole('button', { name: /测试并保存|正在测试连接/ })).toBeVisible();
  });

  test('地址为空时提交按钮被禁用', async ({ page }) => {
    await gotoServerSettings(page);

    const input = page.locator('input[placeholder*="192.168"]');
    await input.fill('');
    await expect(page.getByRole('button', { name: /测试并保存/ })).toBeDisabled();
  });

  test('连接链接会填入统一 TrailSnap 地址并生成分享二维码', async ({ page }) => {
    await page.route('**/api/nav/items', route =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) })
    );
    await page.route('**/api/notifications/**', route =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    );

    await page.goto(`/connect?url=${encodeURIComponent('http://192.168.1.20:8082')}`);

    await expect(page.locator('input[placeholder*="192.168"]')).toHaveValue('http://192.168.1.20:8082');
    await expect(page.getByAltText('TrailSnap 连接二维码')).toBeVisible();
  });

  test('HTTP 200 成功路径 - 保存到 localStorage 并跳转 /login', async ({ page }) => {
    await page.route('**/api/health-check', (route) => route.fulfill({ status: 200, body: 'ok' }));

    await gotoServerSettings(page);
    const input = page.locator('input[placeholder*="192.168"]');
    await input.fill(DEFAULT_API);

    await page.getByRole('button', { name: /测试并保存/ }).click();

    await expect(page.locator('p.text-green-600')).toBeVisible({ timeout: 8_000 });
    await expect(page.locator('p.text-green-600')).toContainText(/连接成功/);

    const stored = await page.evaluate(() => localStorage.getItem('trailsnap:server-url'));
    expect(stored).toBe(DEFAULT_API);

    await page.waitForURL(/\/login/, { timeout: 5_000 });
  });

  test('HTTP 500 失败路径 - 显示错误信息并保留在原页面', async ({ page }) => {
    await page.route('**/api/health-check', (route) =>
      route.fulfill({ status: 500, body: 'server error' })
    );

    await gotoServerSettings(page);
    const input = page.locator('input[placeholder*="192.168"]');
    await input.fill(DEFAULT_API);

    await page.getByRole('button', { name: /测试并保存/ }).click();

    const formAlert = page.locator('p[role="alert"].text-red-600');
    await expect(formAlert).toBeVisible({ timeout: 8_000 });
    await expect(formAlert).toContainText(/HTTP 500/);

    await expect(page).toHaveURL(/\/server-settings/);

    const stored = await page.evaluate(() => localStorage.getItem('trailsnap:server-url'));
    expect(stored).toBeFalsy();
  });
});
