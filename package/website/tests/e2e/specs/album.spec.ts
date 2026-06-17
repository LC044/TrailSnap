import { test, expect } from '@playwright/test';

test.describe('相册功能', () => {
  test('相册列表页面正常加载', async ({ page }) => {
    await page.goto('/album');

    // 等待页面加载
    await expect(page.locator('body')).toBeVisible();

    // 验证 URL
    await expect(page).toHaveURL(/\/album/);
  });

  test('智能分类页面正常加载', async ({ page }) => {
    await page.goto('/album/classification');

    await expect(page.locator('body')).toBeVisible();
    await expect(page).toHaveURL(/\/album\/classification/);
  });

  test('位置相册页面正常加载', async ({ page }) => {
    await page.goto('/album/location');

    await expect(page.locator('body')).toBeVisible();
    await expect(page).toHaveURL(/\/album\/location/);
  });

  test('人物相册页面正常加载', async ({ page }) => {
    await page.goto('/album/people');

    await expect(page.locator('body')).toBeVisible();
    await expect(page).toHaveURL(/\/album\/people/);
  });
});