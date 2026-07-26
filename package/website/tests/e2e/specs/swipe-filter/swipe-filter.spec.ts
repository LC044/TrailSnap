import { test, expect } from '../../fixtures/auth-page';

/**
 * Smoke 测试 — 断舍离筛选（src/views/toolbox/SwipeFilter.vue）
 *
 * /swipe-filter 是「blank layout」独立路由，但组件 onMounted 会调 photoApi/albumService
 * 拉数据，属于需要登录的工具页（不在路由白名单、也不在 401 拦截器的 publicPages 里）。
 * 验证：
 *  - 登录后路由 /swipe-filter 能正常打开（不跳 /login）。
 *  - 标题「照片筛选」渲染（模板硬编码 h1）。
 *  - 顶部 "处理中 / 撤销" 控件可见（撤销按钮初始是 disabled 状态）。
 *
 * 隔离说明：原 spec 用 browser.newContext() 想起干净上下文测「免登录」，但 SwipeFilter
 * 本就需要 token；且 Playwright 1.60 下 storageState 会泄漏进手动 newContext()，干净上下文
 * 并不干净——骑的失效 token 让 photoApi 返回 401，request.ts 拦截器 resetState() 跳 /login。
 * 改用 authedPage：worker 级现登录拿保证有效的 token 注入，不共享、不被别的用例失效。
 */
test.describe('Smoke - 断舍离筛选 @smoke', () => {

  test('断舍离页面正常加载 - 登录后可打开', async ({ authedPage: page }) => {
    await page.goto('/swipe-filter');

    // 已登录态下守卫放行；容许 1) 正常加载 2) 数据为空时停留在 /swipe-filter。
    await expect(page).toHaveURL(/\/swipe-filter/);
    await expect(page.locator('body')).toBeVisible();
  });

  test('断舍离页面渲染顶部工具栏 - 标题 / 进度 / 撤销按钮可见', async ({ authedPage: page }) => {
    await page.goto('/swipe-filter');

    // 模板硬编码 h1「照片筛选」；CI 上 SPA bundle 较大、JS 执行慢，组件挂载可能略晚，放宽到 20s
    await expect(page.locator('h1', { hasText: '照片筛选' })).toBeVisible({ timeout: 20_000 });
    // 进度计数 N / M 必然渲染（0 / 0 也算）
    await expect(page.getByText(/^\s*\d+\s*\/\s*\d+\s*$/)).toBeVisible();
    // 撤销按钮：title="撤销 (Ctrl+Z)"
    const undoBtn = page.getByTitle(/撤销/);
    await expect(undoBtn).toBeVisible();
    // 初始没有操作历史时按钮 disabled
    await expect(undoBtn).toBeDisabled();
  });
});
