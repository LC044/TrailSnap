import { test, expect } from '@playwright/test';
import { e2eEnv } from '../../../playwright/e2e-env';

test.describe('首页功能', () => {
  test('首页正常加载', async ({ page, request }, testInfo) => {
    // 需要真实登录态，dev 环境无测试账号时 skip
    if (!e2eEnv.storageState) {
      try {
        const loginRes = await request.post(`${e2eEnv.apiBaseUrl}/auth/login`, {
          form: { username: e2eEnv.testUsername, password: e2eEnv.testPassword },
          timeout: 5_000,
        });
        if (!loginRes.ok()) {
          testInfo.skip(true, `Test user login failed (${loginRes.status()}) — register e2e-admin first`);
          return;
        }
        const { access_token } = await loginRes.json();
        await page.goto('/login');
        await page.evaluate((token) => localStorage.setItem('user_token', token), access_token);
      } catch {
        testInfo.skip(true, `Backend not reachable at ${e2eEnv.apiBaseUrl}`);
        return;
      }
    }

    // 跳转到首页
    await page.goto('/');
    await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => {});

    // 验证页面可见
    await expect(page.locator('body')).toBeVisible();
  });

  test('导航栏正常显示', async ({ page, request }, testInfo) => {
    // 需要真实登录态，dev 环境无测试账号时 skip
    if (!e2eEnv.storageState) {
      try {
        const loginRes = await request.post(`${e2eEnv.apiBaseUrl}/auth/login`, {
          form: { username: e2eEnv.testUsername, password: e2eEnv.testPassword },
          timeout: 5_000,
        });
        if (!loginRes.ok()) {
          testInfo.skip(true, `Test user login failed (${loginRes.status()}) — register e2e-admin first`);
          return;
        }
        const { access_token } = await loginRes.json();
        await page.goto('/login');
        await page.evaluate((token) => localStorage.setItem('user_token', token), access_token);
      } catch {
        testInfo.skip(true, `Backend not reachable at ${e2eEnv.apiBaseUrl}`);
        return;
      }
    }

    await page.goto('/');
    await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => {});

    // 检查侧边栏导航链接存在
    const navLinks = page.locator('nav a, .el-menu a, aside a');
    await expect(navLinks.first()).toBeVisible({ timeout: 5_000 });
  });
});
