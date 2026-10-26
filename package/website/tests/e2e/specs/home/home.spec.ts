import { test, expect } from '@playwright/test';
import { ensureAuthSession } from '../../helpers/auth';

test.describe('Smoke - 首页 @smoke', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return;
  });

  test('首页正常加载', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByRole('heading', { name: '首页', exact: true }).first()).toBeVisible();
  });

  test('导航栏正常显示', async ({ page }) => {
    await page.goto('/');

    // 检查侧边栏导航链接存在
    const navLinks = page.locator('nav a, .el-menu a, aside a');
    await expect(navLinks.first()).toBeVisible({ timeout: 5_000 });
  });
});

