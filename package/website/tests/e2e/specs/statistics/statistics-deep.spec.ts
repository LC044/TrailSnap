import { test, expect } from '@playwright/test';
import { ensureAuthSession } from '../../helpers/auth';

/**
 * Smoke - 旅行足迹统计页（src/views/ticket/StatisticsPage.vue）。
 *
 * /statistics 此前只有 statistics.spec.ts 的最简 smoke。本文件补齐：
 *   - 标题"旅行足迹报告"渲染
 *   - "返回列表"返回按钮可见
 *   - 时间筛选下拉文案"全部时间"（默认值）
 *   - 页面无明显错误
 *   - URL 锁定 /statistics 路由
 */
test.describe('Smoke - 统计页深度 @smoke', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return;
  });

  test('统计页 - 标题"旅行足迹报告"渲染', async ({ page }) => {
    await page.goto('/statistics');

    // StatisticsPage.vue 模板硬编码 <h1>旅行足迹报告</h1>
    await expect(page.locator('h1', { hasText: '旅行足迹报告' }).first()).toBeVisible({ timeout: 10_000 });
  });

  test('统计页 - 返回列表按钮可见', async ({ page }) => {
    await page.goto('/statistics');

    // 返回按钮带 ArrowLeft 图标 + 文字"返回列表"
    await expect(page.getByRole('button', { name: '返回列表' })).toBeVisible({ timeout: 10_000 });
  });

  test('统计页 - 时间筛选显示默认"全部时间"文案', async ({ page }) => {
    await page.goto('/statistics');

    // 默认 selectedYear === null 时显示"全部时间"
    await expect(page.getByText('全部时间').first()).toBeVisible({ timeout: 10_000 });
  });

  test('统计页 - 点击时间筛选展开下拉含"自定义范围"选项', async ({ page }) => {
    await page.goto('/statistics');

    // 展开年份菜单（"全部时间"右侧按钮）
    const yearMenuButton = page.getByRole('button', { name: '全部时间' });
    await yearMenuButton.click();

    // 下拉菜单含"自定义范围"选项
    await expect(page.getByText('自定义范围')).toBeVisible({ timeout: 5_000 });
  });

  test('统计页 - 路由锁定不被 catch-all 接管', async ({ page }) => {
    await page.goto('/statistics');
    // 不应跳转到 /login 等其他位置
    await expect(page).toHaveURL(/\/statistics$/);
    await expect(page.locator('body')).toBeVisible({ timeout: 10_000 });
  });
});
