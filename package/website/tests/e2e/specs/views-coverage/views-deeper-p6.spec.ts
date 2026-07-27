import { test, expect } from '@playwright/test';
import { ensureAuthSession } from '../../helpers/auth';

/**
 * Smoke / 视图合同 - 第三组补测
 *
 * 命中此前覆盖偏薄的视图：
 *   - /toolbox       工具箱首页（6 张工具卡 + 最近活动占位）
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

  test('Toolbox 首页 - 渲染 6 张工具卡且卡片可点击导航', async ({ page }) => {
    await page.goto('/toolbox');

    // 标题
    await expect(page.getByRole('heading', { name: '工具箱' })).toBeVisible({ timeout: 10_000 });

    // 6 张工具卡
    const toolTitles = [
      '低分清理',
      '相似照片清理',
      '清理重复',
      '图片整理',
      '批量重命名',
      '修改图片元数据',
    ];
    for (const title of toolTitles) {
      await expect(page.getByText(title, { exact: true }).first()).toBeVisible();
    }

    // 最近活动占位
    await expect(page.getByText('暂无最近活动')).toBeVisible();

    // 点击「批量重命名」卡应导航到 /toolbox/rename
    await page.getByText('批量重命名', { exact: true }).first().click();
    await expect(page).toHaveURL(/\/toolbox\/rename$/);
    await expect(page.locator('h1', { hasText: '批量重命名' })).toBeVisible();
  });

  test('Toolbox 首页 - 「低分清理」卡片跳转到清理页', async ({ page }) => {
    await page.goto('/toolbox');
    await expect(page.getByRole('heading', { name: '工具箱' })).toBeVisible({ timeout: 10_000 });

    await page.getByText('低分清理', { exact: true }).first().click();
    await expect(page).toHaveURL(/\/toolbox\/cleanup$/);
    await expect(page.getByRole('heading', { name: '清理相册' })).toBeVisible({ timeout: 10_000 });
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

    // 等网络空闲（容错：无照片时不会进入长轮询）
    await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => {});

    // 三选一：时间提示 / 空态 / 加载 spinner
    const hasTimeHint = await page.getByText(/时间提示[:：]/).count();
    const hasEmpty = await page.getByText('暂无可用的照片').count();
    const hasLoading = await page.locator('.animate-spin').count();
    expect(hasTimeHint + hasEmpty + hasLoading).toBeGreaterThan(0);
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