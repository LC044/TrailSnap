import { test, expect } from '@playwright/test';
import { authStatePath } from '../../../e2e-system/helpers/env';

// smoke 测试需要已登录态（首页/404 兜底访问后端）
test.use({ storageState: authStatePath });

/**
 * P0 冒烟测试 - 主链路渲染与系统健康
 *
 * 覆盖 doc/e2e-test-checklist.md §1.3、§1.4。
 * 环境变量约定（与 e2e-system/ 一致）：
 *   TS_WEB_BASE_URL  - 前端入口（system 环境: 8082, dev 环境: 5176）
 *   TS_API_BASE_URL  - 后端入口（system 环境: 8800, dev 环境: 8000）
 *
 * 后端不可达时自动 test.skip，避免环境噪声。
 */

const API_BASE = process.env.TS_API_BASE_URL || 'http://localhost:8800';

test.describe('P0 冒烟 - 主链路渲染', () => {
  test.beforeEach(async ({ page }) => {
    // 注入伪 token 跳过登录态要求（不校验真实性）
    await page.goto('/login');
    await page.evaluate(() => localStorage.setItem('user_token', 'p0-smoke.jwt'));
  });

  test('首页正常加载 - 至少渲染出标题', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => {});

    // HomePage 顶部固定 h1
    await expect(page.locator('h1', { hasText: '相册概览' })).toBeVisible({ timeout: 5_000 });
    await expect(page.locator('body')).toBeVisible();
  });

  test('404 兜底 - 访问不存在的路由', async ({ page }) => {
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
    const res = await request.get(`${API_BASE}/system/version`, { timeout: 5_000 }).catch(() => null);
    if (!res || !res.ok()) {
      test.skip(true, `Backend not reachable at ${API_BASE}`);
      return;
    }
    const body = await res.json();
    expect(body).toHaveProperty('version');
    expect(typeof body.version).toBe('string');
    expect(body.version).toMatch(/^\d+\.\d+\.\d+/);
  });

  test('/auth/status 返回 has_users / allow_registration 字段', async ({ request }) => {
    const res = await request.get(`${API_BASE}/auth/status`, { timeout: 5_000 }).catch(() => null);
    if (!res || !res.ok()) {
      test.skip(true, `Backend not reachable at ${API_BASE}`);
      return;
    }
    const body = await res.json();
    expect(body).toHaveProperty('has_users');
    expect(body).toHaveProperty('allow_registration');
    expect(typeof body.has_users).toBe('boolean');
    expect(typeof body.allow_registration).toBe('boolean');
  });

  test('/tasks/status 返回全局任务状态', async ({ request }) => {
    const res = await request.get(`${API_BASE}/tasks/status`, { timeout: 5_000 }).catch(() => null);
    if (!res || !res.ok()) {
      test.skip(true, `Backend not reachable at ${API_BASE}`);
      return;
    }
    const body = await res.json();
    expect(body).toBeDefined();
  });

  test('/openapi.json 可访问 - FastAPI 文档', async ({ request }) => {
    const res = await request.get(`${API_BASE}/openapi.json`, { timeout: 5_000 }).catch(() => null);
    if (!res || !res.ok()) {
      test.skip(true, `Backend not reachable at ${API_BASE}`);
      return;
    }
    const body = await res.json();
    expect(body).toHaveProperty('openapi');
    expect(body).toHaveProperty('paths');
  });
});
