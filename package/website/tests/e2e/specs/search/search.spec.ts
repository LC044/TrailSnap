import { test, expect } from '@playwright/test';
import { ensureAuthSession } from '../../helpers/auth';

test.describe('P0 冒烟 - 搜索页 @smoke', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo))) return;
  });

  test('搜索页正常加载', async ({ page }) => {
    await page.goto('/search');
    await expect(page.locator('body')).toBeVisible();
    await expect(page).toHaveURL(/\/search/);
  });
});
