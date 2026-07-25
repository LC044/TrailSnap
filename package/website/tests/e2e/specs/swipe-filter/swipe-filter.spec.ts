import { test, expect } from '@playwright/test';

/**
 * Smoke 测试 — 断舍离筛选（src/views/toolbox/SwipeFilter.vue）
 *
 * /swipe-filter 是「blank layout」独立路由，无需登录即可访问。
 * 验证：
 *  - 路由 /swipe-filter 能正常打开（不跳 /login）。
 *  - 标题「照片筛选」渲染（模板硬编码 h1）。
 *  - 顶部 "处理中 / 撤销" 控件可见（撤销按钮初始是 disabled 状态）。
 */

test.describe('Smoke - 断舍离筛选 @smoke', () => {
  // /swipe-filter 是 blank layout 独立路由，无需登录。用空 storageState 起干净 context，
  // 不继承全局登录态——避免共享 token 被并行用例失效后页面被守卫干扰、h1 不渲染。
  test.use({ storageState: { cookies: [], origins: [] } });

  test('断舍离页面正常加载 - 无需登录即可打开', async ({ page }) => {
    await page.goto('/swipe-filter');

    // 路由守卫白名单外的页面会被踢到 /login；swipe-filter 不在白名单，
    // 但它是 blank layout 独立页面，需要在 spec 里验证不被守卫拦截。
    // 容许 1) 正常加载 2) 数据为空时停留在 /swipe-filter。
    await expect(page).toHaveURL(/\/swipe-filter/);
    await expect(page.locator('body')).toBeVisible();
  });

  test('断舍离页面渲染顶部工具栏 - 标题 / 进度 / 撤销按钮可见', async ({ page }) => {
    await page.goto('/swipe-filter');

    // 模板硬编码 h1「照片筛选」
    await expect(page.locator('h1', { hasText: '照片筛选' })).toBeVisible({ timeout: 10_000 });
    // 进度计数 N / M 必然渲染（0 / 0 也算）
    await expect(page.getByText(/^\s*\d+\s*\/\s*\d+\s*$/)).toBeVisible();
    // 撤销按钮：title="撤销 (Ctrl+Z)"
    const undoBtn = page.getByTitle(/撤销/);
    await expect(undoBtn).toBeVisible();
    // 初始没有操作历史时按钮 disabled
    await expect(undoBtn).toBeDisabled();
  });
});
