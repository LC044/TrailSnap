import { test, expect } from '@playwright/test';
import { ensureAuthSession } from '../helpers/auth';

/**
 * Smoke 测试 — 仅验证「页面能否正常打开」
 *
 * 职责边界（与 p0 分离）：
 *   - smoke (@smoke)：页面能打开、关键静态骨架元素可见。不校验数据正确性、不校验交互。
 *   - p0   (@p0)   ：功能是否可用、API 是否返回正确数据。
 *
 * 受保护页面需要真实 token —— 否则 axios 401 拦截器（src/utils/request.ts）
 * 会清空 token 并重定向到 /login，页面根本停不住。token 通过 ensureAuthSession
 * 注入（system 套件走 storageState，dev 套件走登录）；后端不可达 / 账号无法登录时
 * 自动 test.skip，避免环境噪声。
 * 白名单页面（/annual-report 等）无需登录，路由守卫直接放行。
 *
 * 注意：不再在 beforeEach 注入伪 token —— 那会覆盖 system 套件 storageState
 * 里的真实 token，导致受保护页面被 401 拦截器踢去 /login。
 */

test.describe('页面打开冒烟 @smoke', () => {
  test('首页能打开 - 渲染出标题', async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return;
    await page.goto('/');

    // HomePage 顶部固定 h1（模板静态写死，与 API 数据无关）
    await expect(page.locator('h1', { hasText: '相册概览' })).toBeVisible({ timeout: 10_000 });
  });

  test('404 兜底页能打开', async ({ page, request }, testInfo) => {
    // 404 页在 MainLayout 内，需要真实 token 防止 axios 拦截器清 token 重定向
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return;
    await page.goto('/this-route-does-not-exist-12345');

    await expect(page.locator('h1', { hasText: '404' })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('页面未找到')).toBeVisible();
  });

  test('白名单页 /annual-report 无需登录可打开', async ({ page }) => {
    await page.goto('/annual-report');

    // 源码: to.path.startsWith('/annual-report') 放行，无需 token。
    // 年度报告页可能因后端 API 失败降级跳登录；smoke 只验证「没白屏」：
    // 停在 annual-report 或降级到 login 均算页面存活。
    await expect(page.locator('body')).toBeVisible({ timeout: 10_000 });
    await expect(page).toHaveURL(/\/(annual-report|login)/);
  });
});

