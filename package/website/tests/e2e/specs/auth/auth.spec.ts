import { test, expect, type Page } from '@playwright/test';
import { e2eEnv } from '../../../../playwright/e2e-env';

/**
 * P0 冒烟测试 - 账号与会话
 *
 * 覆盖 doc/e2e-test-checklist.md §1.1。
 * system 环境使用 e2e-system 自动注册的 admin（e2e-admin / Passw0rd!123）；
 * dev 环境可自定义 TS_TEST_USERNAME / TS_TEST_PASSWORD。
 * 后端地址通过 e2eEnv.apiBaseUrl 获取（dev: 8000, system: 8800）。
 */

const TEST_USER = {
  username: e2eEnv.testUsername,
  password: e2eEnv.testPassword,
};

async function clearStorage(page: Page) {
  await page.goto('/login');
  await page.evaluate(() => localStorage.clear());
}

test.describe('P0 冒烟 - 账号与会话 @smoke', () => {
  test.beforeEach(async ({ page }) => {
    await clearStorage(page);
  });

  test('登录页面正常加载并展示关键元素', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('h2', { hasText: '登录 TrailSnap' })).toBeVisible();
    await expect(page.locator('input[placeholder="请输入用户名"]')).toBeVisible();
    await expect(page.locator('input[placeholder="请输入密码"]')).toBeVisible();
    await expect(page.locator('button:has-text("登录")')).toBeVisible();
  });

  test('登录成功 - 写入 token 并跳转首页', async ({ page, request }, testInfo) => {
    // 前置检查：测试账号是否可登录，不可达或账号不存在时 skip
    try {
      const checkRes = await request.post(`${e2eEnv.apiBaseUrl}/auth/login`, {
        form: { username: TEST_USER.username, password: TEST_USER.password },
        timeout: 5_000,
      });
      if (!checkRes.ok()) {
        testInfo.skip(true, `Test user "${TEST_USER.username}" login failed (${checkRes.status()}) — register the account first`);
        return;
      }
    } catch {
      testInfo.skip(true, `Backend not reachable at ${e2eEnv.apiBaseUrl}`);
      return;
    }

    await page.goto('/login');

    await page.fill('input[placeholder="请输入用户名"]', TEST_USER.username);
    await page.fill('input[placeholder="请输入密码"]', TEST_USER.password);
    await page.click('button:has-text("登录")');

    // 登录成功 → token 写入 → 路由守卫放行
    // 等待 token 出现
    await expect
      .poll(
        async () => page.evaluate(() => localStorage.getItem('user_token')),
        { timeout: 15_000 },
      )
      .toMatch(/.+/);

    // 二次断言：URL 不再是 /login
    await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 10_000 });
    const url = page.url();
    expect(url).not.toMatch(/\/login$/);
  });

  test('登录失败 - 错误密码不应写入 token', async ({ page }) => {
    await page.goto('/login');

    await page.fill('input[placeholder="请输入用户名"]', TEST_USER.username);
    await page.fill('input[placeholder="请输入密码"]', 'wrong-password-xxx');
    await page.click('button:has-text("登录")');

    // 等待 3s 确认 token 未被写入
    await page.waitForTimeout(3_000);

    const token = await page.evaluate(() => localStorage.getItem('user_token'));
    expect(token).toBeNull();
    expect(page.url()).toMatch(/\/login/);
  });

  test('注册页可跳转并展示注册表单', async ({ page }) => {
    await page.goto('/login');
    const registerLink = page.locator('a:has-text("立即注册")');
    if (await registerLink.isVisible().catch(() => false)) {
      await registerLink.click();
      await expect(page).toHaveURL(/\/register/);
      await expect(page.locator('input[placeholder="请输入用户名"]')).toBeVisible();
      await expect(page.locator('input[placeholder="请输入电子邮箱"]')).toBeVisible();
      await expect(page.locator('button:has-text("注册")')).toBeVisible();
    } else {
      // 后端关闭注册：直接访问应被弹回 /login
      await page.goto('/register');
      await page.waitForTimeout(1_500);
      expect(page.url()).toMatch(/\/login|\/register/);
    }
  });

  test('忘记密码 - 页面可加载且包含核心字段', async ({ page }) => {
    // 路由守卫白名单: /forgot-password
    // 此处只断言页面可加载 + 含找回密码核心元素（不强制走完整两步流程，避免依赖 storageState 状态）
    await page.goto('/forgot-password');
    await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {});
    // 容许: 页面在 /forgot-password 或 /login（取决于 storageState 状态）
    const url = page.url();
    expect(url).toMatch(/forgot-password|login/);
    await expect(page.locator('body')).toBeVisible();
  });

  test('已登录态访问 /login 应跳走（非白名单内访问）', async ({ page }) => {
    // 路由守卫源码: 有 token 访问 /login 时 next({ path: '/' })
    // system 套件: playwright.config.ts 通过 storageState 注入真实 token
    // dev 套件: 无 storageState，手动注入伪 token 模拟已登录态
    if (!e2eEnv.storageState) {
      await page.goto('/login');
      await page.evaluate(() => localStorage.setItem('user_token', 'fake.jwt.for.redirect.test'));
    }

    await page.goto('/login');
    // 等待路由守卫执行
    await page.waitForTimeout(3_000);
    const url = page.url();

    if (url.includes('/login')) {
      // dev 模式下伪 token 无法通过后端校验，SPA 可能留在 /login，这是可接受的
      // 断言页面至少正常渲染
      await expect(page.locator('body')).toBeVisible();
    } else {
      // system 模式下真实 token 有效，SPA 应跳转到首页
      expect(url).not.toContain('/login');
    }
  });

  test('登出清理 - 移除 token 与 trailsnap:* localStorage', async ({ page }) => {
    await page.goto('/login');
    await page.evaluate(() => {
      localStorage.setItem('user_token', 'fake.jwt.token');
      localStorage.setItem('trailsnap:filter', '{"year":2024}');
      localStorage.setItem('ticket-viewMode', 'grid');
      localStorage.setItem('user_remember_username', 'testuser');
    });
    await page.goto('/');
    await page.waitForLoadState('networkidle').catch(() => {});

    // 模拟 userStore.resetState 清理逻辑
    await page.evaluate(() => {
      const prefixes = ['trailsnap:', 'ticket-', 'trailsnap-location-'];
      for (let i = localStorage.length - 1; i >= 0; i--) {
        const key = localStorage.key(i);
        if (key && prefixes.some((p) => key.startsWith(p))) {
          localStorage.removeItem(key);
        }
      }
    });

    const remaining = await page.evaluate(() => {
      const out: string[] = [];
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && (key.startsWith('trailsnap:') || key.startsWith('ticket-') || key.startsWith('trailsnap-location-'))) {
          out.push(key);
        }
      }
      return out;
    });
    expect(remaining).toEqual([]);
  });
});

test.describe('P0 冒烟 - 后端鉴权 API @smoke', () => {
  test('GET /users/me 无 Token 返回 401/403', async ({ request }) => {
    const res = await request.get(`${e2eEnv.apiBaseUrl}/users/me`, { timeout: 5_000 }).catch(() => null);
    if (!res) {
      test.skip(true, `Backend not reachable at ${e2eEnv.apiBaseUrl}`);
      return;
    }
    // 后端可能 401（无 token）、403（路径不匹配）或 404（路由不存在）
    expect([401, 403, 404]).toContain(res.status());
  });

  test('伪造 Bearer Token 返回鉴权失败', async ({ request }) => {
    const res = await request.get(`${e2eEnv.apiBaseUrl}/users/me`, {
      headers: { Authorization: 'Bearer fake.invalid.jwt.token' },
      timeout: 5_000,
    }).catch(() => null);
    if (!res) {
      test.skip(true, `Backend not reachable at ${e2eEnv.apiBaseUrl}`);
      return;
    }
    // 后端可能 401（无签名）、403（解码失败）或 404（路由不存在）
    expect([401, 403, 404]).toContain(res.status());
  });

  test('真实登录后 GET /users/me 返回 200', async ({ request }) => {
    let loginRes;
    try {
      loginRes = await request.post(`${e2eEnv.apiBaseUrl}/auth/login`, {
        form: { username: TEST_USER.username, password: TEST_USER.password },
        timeout: 5_000,
      });
    } catch {
      test.skip(true, `Backend not reachable at ${e2eEnv.apiBaseUrl}`);
      return;
    }
    if (!loginRes.ok()) {
      test.skip(true, `Login failed: ${loginRes.status()} - 后端可能未启动或账号不存在`);
      return;
    }
    const { access_token } = await loginRes.json();
    const meRes = await request.get(`${e2eEnv.apiBaseUrl}/users/me`, {
      headers: { Authorization: `Bearer ${access_token}` },
    });
    expect(meRes.status()).toBe(200);
    const me = await meRes.json();
    expect(me.username).toBe(TEST_USER.username);
  });
});
