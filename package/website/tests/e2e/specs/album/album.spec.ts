import { test, expect } from '@playwright/test';
import { ensureAuthSession } from '../../helpers/auth';

test.describe('Smoke - 相册路由 @smoke', () => {
  // 受保护路由：未登录会被守卫重定向到 /login，统一在 beforeEach 建立会话
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return;
  });

  test('相册列表页面正常加载', async ({ page }) => {
    await page.goto('/album');

    await expect(page.locator('body')).toBeVisible();
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

