import { test, expect } from '@playwright/test';
import { ensureAuthSession } from '../../helpers/auth';

test.describe('Smoke - 车票页 @smoke', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo))) return;
  });

  test('车票页正常加载', async ({ page }) => {
    await page.goto('/ticket');
    await expect(page.locator('body')).toBeVisible();
    await expect(page).toHaveURL(/\/ticket/);
  });
});
