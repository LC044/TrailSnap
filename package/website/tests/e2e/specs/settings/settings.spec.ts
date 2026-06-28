import { test, expect } from '@playwright/test';
import { ensureAuthSession } from '../../helpers/auth';

test.describe('Smoke - 设置页 @smoke', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return;
  });

  test('设置页正常加载', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.locator('body')).toBeVisible();
    await expect(page).toHaveURL(/\/settings/);
  });
});

