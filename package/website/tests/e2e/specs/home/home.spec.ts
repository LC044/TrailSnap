import { test, expect } from '@playwright/test';
import { ensureAuthSession } from '../../helpers/auth';

test.describe('P0 冒烟 - 首页 @smoke', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo))) return;
  });

  test('首页正常加载', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => {});

    // 验证页面可见
    await expect(page.locator('body')).toBeVisible();
  });

  test('导航栏正常显示', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => {});

    // 检查侧边栏导航链接存在
    const navLinks = page.locator('nav a, .el-menu a, aside a');
    await expect(navLinks.first()).toBeVisible({ timeout: 5_000 });
  });
});
