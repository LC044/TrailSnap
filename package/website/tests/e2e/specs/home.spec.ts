import { test, expect } from '@playwright/test';

test.describe('首页功能', () => {
  test('首页正常加载', async ({ page }) => {
    // 先登录获取 token
    await page.goto('/login');
    await page.fill('input[type="text"], input[name="username"]', 'testuser');
    await page.fill('input[type="password"]', 'testpassword');
    await page.click('button[type="submit"]');

    // 跳转到首页
    await page.goto('/');

    // 等待页面加载
    await expect(page.locator('body')).toBeVisible();

    // 验证页面 title
    await expect(page).toHaveTitle(/.*行影集.*|.*TrailSnap.*|.*首页.*/);
  });

  test('导航栏正常显示', async ({ page }) => {
    await page.goto('/');

    // 检查导航链接存在
    const navLinks = page.locator('nav a, .el-menu a, header a');
    await expect(navLinks.first()).toBeVisible();
  });
});