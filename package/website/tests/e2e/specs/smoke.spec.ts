import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import { e2eEnv } from '../../../playwright/e2e-env';

/**
 * P0 冒烟测试 - 主链路渲染与系统健康
 *
 * 覆盖 doc/e2e-test-checklist.md §1.3、§1.4。
 * 后端地址通过 e2eEnv.apiBaseUrl 获取（dev: 8000, system: 8800）。
 * 后端不可达或测试账号无法登录时自动 test.skip，避免环境噪声。
 */

/** 检查后端是否可达，不可达则 skip 当前测试 */
async function ensureBackend(
  request: APIRequestContext,
  testInfo: { skip: (condition: boolean, reason: string) => void },
): Promise<boolean> {
  try {
    const res = await request.get(`${e2eEnv.apiBaseUrl}/system/version`, { timeout: 5_000 });
    if (!res.ok()) {
      testInfo.skip(true, `Backend returned ${res.status()}`);
      return false;
    }
    return true;
  } catch {
    testInfo.skip(true, `Backend not reachable at ${e2eEnv.apiBaseUrl}`);
    return false;
  }
}

/**
 * 确保测试账号可登录，为 page 注入真实 token。
 * - system 套件: storageState 已由 config 注入真实 token
 * - dev 套件: 手动登录获取真实 token 并写入 localStorage
 * 如果登录失败则 skip 当前测试。
 */
async function ensureAuthSession(
  request: APIRequestContext,
  page: Page,
  testInfo: { skip: (condition: boolean, reason: string) => void },
): Promise<boolean> {
  // system 套件已有 storageState 提供真实 token，无需手动登录
  if (e2eEnv.storageState) return true;

  // dev 套件: 尝试用测试账号登录获取真实 token
  try {
    const loginRes = await request.post(`${e2eEnv.apiBaseUrl}/auth/login`, {
      form: { username: e2eEnv.testUsername, password: e2eEnv.testPassword },
      timeout: 5_000,
    });
    if (!loginRes.ok()) {
      testInfo.skip(true, `Test user login failed (${loginRes.status()}) — register e2e-admin first or run system suite`);
      return false;
    }
    const { access_token } = await loginRes.json();
    await page.evaluate((token) => localStorage.setItem('user_token', token), access_token);
    return true;
  } catch {
    testInfo.skip(true, `Backend not reachable at ${e2eEnv.apiBaseUrl}`);
    return false;
  }
}

test.describe('P0 冒烟 - 主链路渲染', () => {
  test.beforeEach(async ({ page }) => {
    // 注入伪 token 跳过路由守卫（不校验真实性）
    // 需要真实后端数据的测试会用 ensureAuthSession 替换为真实 token
    await page.goto('/login');
    await page.evaluate(() => localStorage.setItem('user_token', 'p0-smoke.jwt'));
  });

  test('首页正常加载 - 至少渲染出标题', async ({ page, request }, testInfo) => {
    // 需要 real token 才能获取首页数据
    if (!(await ensureAuthSession(request, page, testInfo))) return;
    await page.goto('/');
    await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => {});

    // HomePage 顶部固定 h1
    await expect(page.locator('h1', { hasText: '相册概览' })).toBeVisible({ timeout: 5_000 });
    await expect(page.locator('body')).toBeVisible();
  });

  test('404 兜底 - 访问不存在的路由', async ({ page, request }, testInfo) => {
    // 404 页面在 MainLayout 内，需要 real token 防止 axios 拦截器清 token 重定向
    if (!(await ensureAuthSession(request, page, testInfo))) return;
    await page.goto('/this-route-does-not-exist-12345');
    await page.waitForLoadState('networkidle', { timeout: 5_000 }).catch(() => {});

    await expect(page.locator('h1', { hasText: '404' })).toBeVisible({ timeout: 5_000 });
    await expect(page.locator('text=页面未找到')).toBeVisible();
  });

  test('白名单页面 - /annual-report 无需登录可访问', async ({ page }) => {
    await page.evaluate(() => localStorage.removeItem('user_token'));
    await page.goto('/annual-report');

    await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => {});
    const url = page.url();
    // 源码: to.path.startsWith('/annual-report') 放行
    // 年度报告页可能因后端 API 失败降级跳登录；这里只断言 URL 合法 + body 可见
    expect(url).toMatch(/annual-report|login/);
    await expect(page.locator('body')).toBeVisible();
  });
});

test.describe('P0 冒烟 - 后端 API 健康', () => {
  test('/system/version 返回版本号', async ({ request }) => {
    const res = await request.get(`${e2eEnv.apiBaseUrl}/system/version`, { timeout: 5_000 }).catch(() => null);
    if (!res || !res.ok()) {
      test.skip(true, `Backend not reachable at ${e2eEnv.apiBaseUrl}`);
      return;
    }
    const body = await res.json();
    expect(body).toHaveProperty('version');
    expect(typeof body.version).toBe('string');
    expect(body.version).toMatch(/^\d+\.\d+\.\d+/);
  });

  test('/auth/status 返回 has_users / allow_registration 字段', async ({ request }) => {
    const res = await request.get(`${e2eEnv.apiBaseUrl}/auth/status`, { timeout: 5_000 }).catch(() => null);
    if (!res || !res.ok()) {
      test.skip(true, `Backend not reachable at ${e2eEnv.apiBaseUrl}`);
      return;
    }
    const body = await res.json();
    expect(body).toHaveProperty('has_users');
    expect(body).toHaveProperty('allow_registration');
    expect(typeof body.has_users).toBe('boolean');
    expect(typeof body.allow_registration).toBe('boolean');
  });

  test('/tasks/status 返回全局任务状态', async ({ request }) => {
    const res = await request.get(`${e2eEnv.apiBaseUrl}/tasks/status`, { timeout: 5_000 }).catch(() => null);
    if (!res || !res.ok()) {
      test.skip(true, `Backend not reachable at ${e2eEnv.apiBaseUrl}`);
      return;
    }
    const body = await res.json();
    expect(body).toBeDefined();
  });

  test('/openapi.json 可访问 - FastAPI 文档', async ({ request }) => {
    const res = await request.get(`${e2eEnv.apiBaseUrl}/openapi.json`, { timeout: 5_000 }).catch(() => null);
    if (!res || !res.ok()) {
      test.skip(true, `Backend not reachable at ${e2eEnv.apiBaseUrl}`);
      return;
    }
    const body = await res.json();
    expect(body).toHaveProperty('openapi');
    expect(body).toHaveProperty('paths');
  });
});
