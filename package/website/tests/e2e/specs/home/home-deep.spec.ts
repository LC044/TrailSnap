import { test, expect } from '@playwright/test';
import { ensureAuthSession } from '../../helpers/auth';

/**
 * Smoke - 首页（src/views/HomePage.vue）深度验证。
 *
 * 首页此前只有 home.spec.ts 的两条极简 smoke（仅 body 可见 + nav links）。
 * 本文件补齐：
 *   - Navbar h1"相册概览"渲染
 *   - 顶部 navbar 含"回收站""存储中心"两个 icon 按钮（通过 title 锚定）
 *   - 主体主区域渲染
 *   - 年度回忆录 banner 可见
 *   - 路由不被 catch-all 接管为 NotFound
 *
 * 注意：
 *   - HomePage main 区需要等 dashboard 数据回来后才挂载，因此先等 "相册概览"
 *     h1 出现，再断言其内部 icon 按钮
 *   - icon-only 按钮 hover state 偶发 Playwright 可见性 false，所以用 count()
 */
test.describe('Smoke - 首页深度 @smoke', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return;
  });

  test('首页 - Navbar 标题"相册概览"渲染', async ({ page }) => {
    await page.goto('/');
    // HomePage.vue 模板硬编码 <h1>相册概览</h1>
    await expect(page.locator('h1', { hasText: '相册概览' }).first()).toBeVisible({ timeout: 10_000 });
  });

  test('首页 - 顶部 navbar 含回收站 / 存储中心 icon 按钮', async ({ page }) => {
    await page.goto('/');
    // 先等主区域挂载（Dashboard 数据回来后 Navbar 才渲染 main 部分）
    await expect(page.locator('h1', { hasText: '相册概览' }).first()).toBeVisible({ timeout: 15_000 });

    // 通过 title 属性锚定 icon button；用 count() 而非 toBeVisible()，
    // 因为 hover-state / 尺寸极小时 Playwright 可见性判断偶发 false
    const recycleCount = await page.getByTitle('回收站').count();
    const storageCount = await page.getByTitle('存储中心').count();
    expect(recycleCount).toBeGreaterThan(0);
    expect(storageCount).toBeGreaterThan(0);
  });

  test('首页 - 主体主区域渲染', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h1', { hasText: '相册概览' }).first()).toBeVisible({ timeout: 15_000 });
    await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => {});

    // main 元素可见（HomePage.vue 顶层包了 main）
    await expect(page.locator('main').first()).toBeVisible({ timeout: 10_000 });
  });

  test('首页 - 年度回忆录 banner 可见', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h1', { hasText: '相册概览' }).first()).toBeVisible({ timeout: 15_000 });
    await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => {});

    // 年度回忆录 h3 显示 "[year] 年度回忆录"，断言 banner 存在
    const banner = page.getByText(/年度回忆录/).first();
    await expect(banner).toBeVisible({ timeout: 10_000 });
  });

  test('首页 - 路由不被 catch-all 接管为 NotFound', async ({ page }) => {
    await page.goto('/');
    // 不被重定向（已登录态）也不到 catch-all 触发 NotFound
    await expect(page).toHaveURL(/\/$/);
    const notFoundCount = await page.getByText(/页面不存在|404|Not Found|未找到页面/).count();
    expect(notFoundCount).toBe(0);
  });

  test('首页 - 那年今日操作菜单可查看详情或退出回忆', async ({ page }) => {
    await page.route('**/api/photos/on-this-day**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          msg: 'success',
          data: [{
            id: '00000000-0000-0000-0000-000000000112',
            filename: 'on-this-day.jpg',
            photo_time: '2020-08-08T12:00:00',
            upload_time: '2020-08-08T12:00:00',
            url: '',
            thumbnail_url: '',
            file_type: 'image',
            size: 1024,
            width: 800,
            height: 600,
          }],
        }),
      });
    });

    await page.goto('/');
    const memoryCard = page.getByRole('button', { name: /打开 2020-08-08 的回忆卡片/ });
    await expect(memoryCard).toBeVisible({ timeout: 15_000 });
    await memoryCard.click();

    const actionsButton = page.getByRole('button', { name: '回忆操作' });
    await expect(actionsButton).toBeVisible({ timeout: 5_000 });
    await actionsButton.click();

    const memoryMenu = page.getByRole('menu', { name: '回忆操作菜单' });
    await expect(memoryMenu).toBeVisible();
    await expect(memoryMenu.getByRole('menuitem', { name: '退出回忆' })).toBeVisible();
    const detailsButton = memoryMenu.getByRole('menuitem', { name: '查看详情' });
    await expect(detailsButton).toBeVisible({ timeout: 5_000 });
    await detailsButton.click();

    await expect(page.getByTitle('查看元数据 (I)')).toBeVisible({ timeout: 10_000 });
  });
});
