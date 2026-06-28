import { test, expect } from '@playwright/test';
import { ensureAuthSession } from '../../helpers/auth';

test.describe('Smoke - 照片页 @smoke', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return;
  });

  test('照片页正常加载', async ({ page }) => {
    await page.goto('/photos');
    await expect(page.locator('body')).toBeVisible();
    await expect(page).toHaveURL(/\/photos/);
  });
});

