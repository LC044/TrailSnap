import { test, expect } from '@playwright/test';
import { ensureAuthSession } from '../../helpers/auth';

/**
 * Smoke / 视图合同 - 第三组补测
 *
 * 命中此前覆盖偏薄的视图：
 *   - /toolbox       工具箱首页（整理与命名 / 清理与修复两组卡片 + 操作记录）
 *   - /annual-report 年度报告（白名单，无 token 也可访问）
 *   - /game          猜城市游戏（空数据 / 加载 / 交互骨架）
 *
 * 目标：每个视图 1-2 个稳定的 smoke + 1 个针对关键交互的 contract 检查，
 * 不会触发 SCAN_* 任务或依赖真实数据，纯渲染层验证。
 */

test.describe('P1 - 视图合同补测 @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return;
  });

  test('Toolbox 首页 - 渲染分组工具卡且卡片可点击导航', async ({ page }) => {
    await page.goto('/toolbox');

    await expect(page.locator('h1.ts-page-title', { hasText: '工具箱' })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('region', { name: '整理与命名' })).toBeVisible();
    await expect(page.getByRole('region', { name: '清理与修复' })).toBeVisible();

    // 重构后首页按用途分组：整理与命名 3 张 + 清理与修复 4 张，共 7 个入口。
    const tools: Array<[string, string]> = [
      ['影像整理', '/toolbox/organize'],
      ['批量重命名', '/toolbox/rename'],
      ['按规则创建相册', '/toolbox/albums'],
      ['重复照片', '/toolbox/duplicate'],
      ['相似照片', '/toolbox/similar'],
      ['低质量照片', '/toolbox/cleanup'],
      ['修正拍摄信息', '/toolbox/time-from-filename'],
    ];
    for (const [title, href] of tools) {
      await expect(page.getByRole('link', { name: new RegExp(title) }).first()).toHaveAttribute('href', href);
    }

    // 旧「暂无最近活动」占位改为「操作记录」分区，记录来自持久化预览计划。
    await expect(page.getByRole('region', { name: '操作记录' })).toBeVisible();

    await page.getByRole('link', { name: /批量重命名/ }).first().click();
    await expect(page).toHaveURL(/\/toolbox\/rename$/);
    await expect(page.locator('h1.ts-page-title', { hasText: '批量重命名' })).toBeVisible({ timeout: 10_000 });
  });

  test('Toolbox 首页 - 「低质量照片」卡片跳转到清理页', async ({ page }) => {
    await page.goto('/toolbox');
    await expect(page.locator('h1.ts-page-title', { hasText: '工具箱' })).toBeVisible({ timeout: 10_000 });

    await page.getByRole('link', { name: /低质量照片/ }).first().click();
    await expect(page).toHaveURL(/\/toolbox\/cleanup$/);
    await expect(page.locator('h1.ts-page-title', { hasText: '照片清理' })).toBeVisible({ timeout: 10_000 });
  });

  test('年度报告页 - 白名单路由不会踢去 /login', async ({ page }) => {
    // /annual-report 在 router.beforeEach 守卫白名单里，不需要 token。
    // smoke 允许停在 /annual-report 或降级 /login；这里因 ensureAuthSession 提供了 token，
    // 页面不会跳 /login，URL 应当保持在 /annual-report。
    await page.goto('/annual-report');
    await expect(page).toHaveURL(/\/annual-report/);
    await expect(page.locator('body')).toBeVisible({ timeout: 10_000 });
  });

  test('猜城市页 - 路由存活且至少出现空态或时间提示', async ({ page }) => {
    await page.goto('/game');
    await expect(page).toHaveURL(/\/game/);
    await expect(page.locator('h1', { hasText: '猜城市' }).first()).toBeVisible({ timeout: 10_000 });

    await expect(page.getByText(/时间提示[:：]/).or(page.getByText('暂无可用的照片')).or(page.locator('.animate-spin')).first()).toBeVisible({ timeout: 10_000 });
  });

  test('猜城市页 - 拦截 random 接口返 code=404 后渲染空态与「重新加载」按钮', async ({ page }) => {
    // 后端无符合条件的照片时返回 {code:404, ...}。
    // 组件 catch 块识别 err.code===404 -> noPhoto=true，渲染「暂无可用的照片」+「重新加载」。
    // 注意：HTTP 状态码保持 200，因为后端在业务码里表达 404；axios 拦截器读 res.code 后 reject。
    const fakeNoPhoto = {
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 404, message: 'no photo available', data: null }),
    };
    const fakeCities = {
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 0, message: 'success', data: [] }),
    };

    await page.route('**/api/guess-city/random*', async (route) => {
      await route.fulfill(fakeNoPhoto);
    });
    await page.route('**/api/guess-city/cities*', async (route) => {
      await route.fulfill(fakeCities);
    });

    await page.goto('/game');
    await expect(page.locator('h1', { hasText: '猜城市' }).first()).toBeVisible({ timeout: 10_000 });

    // 空态文案 + 重新加载按钮
    await expect(page.getByText('暂无可用的照片')).toBeVisible({ timeout: 10_000 });
    const reloadBtn = page.getByRole('button', { name: /重新加载/ });
    await expect(reloadBtn).toBeVisible();

    // 重新挂一个会记录调用的 route，验证「重新加载」会再次触发 random
    let calledAgain = false;
    await page.unroute('**/api/guess-city/random*');
    await page.route('**/api/guess-city/random*', async (route) => {
      calledAgain = true;
      await route.fulfill(fakeNoPhoto);
    });
    await reloadBtn.click();
    await expect.poll(() => calledAgain).toBe(true);
  });
});