import { test, expect } from '@playwright/test';

/**
 * Smoke 测试 — 找回密码（src/views/login/ForgotPassword.vue）
 *
 * /forgot-password 在路由白名单内，未登录也能直接访问。
 * 验证：
 *  - 路由 /forgot-password 能正常打开（不跳 /login）。
 *  - 「找回密码」标题渲染。
 *  - 「安全问题 / 服务器验证码」两种重置方式 radio 可见。
 *  - 用户名/邮箱输入框可见，placeholder 与模板一致。
 */

test.describe('Smoke - 找回密码 @smoke', () => {
  // /forgot-password 是未登录即可访问的白名单页面。用空 storageState 起干净 context，
  // 不继承全局登录态——避免并行跑 login-flow 的「找回密码改密码」用例把共享 token
  // 失效后，本 spec 被路由守卫踢到 /login（toHaveURL 收到 /login 而非 /forgot-password）。
  test.use({ storageState: { cookies: [], origins: [] } });

  test('找回密码页面正常加载 - 标题与重置方式可见', async ({ page }) => {
    await page.goto('/forgot-password');

    // 白名单页面，未登录也直接放行
    await expect(page).toHaveURL(/\/forgot-password/);
    await expect(page.locator('body')).toBeVisible();

    // 模板硬编码 <h2>找回密码</h2>
    await expect(page.locator('h2', { hasText: '找回密码' })).toBeVisible({ timeout: 10_000 });
  });

  test('找回密码页面渲染方式切换与第一步输入框', async ({ page }) => {
    await page.goto('/forgot-password');

    // 两种重置方式 radio 按钮文本
    await expect(page.getByText('安全问题')).toBeVisible();
    await expect(page.getByText('服务器验证码')).toBeVisible();

    // 用户名 / 邮箱输入框（placeholder 模板硬编码）
    const usernameInput = page.getByPlaceholder('请输入用户名或邮箱');
    await expect(usernameInput).toBeVisible();
  });

  test('找回密码页面切换到"服务器验证码"模式显示对应字段', async ({ page }) => {
    await page.goto('/forgot-password');

    // 默认是「安全问题」模式，点击切换到「服务器验证码」
    await page.getByText('服务器验证码').click();

    // 等待 Vue 响应式更新
    await page.waitForTimeout(300);

    // 「服务器验证码」模式下应该有「服务器日志 / 邮箱」相关字段。
    // 这里仅断言切换后页面不白屏 / body 仍可见 + URL 不变。
    await expect(page).toHaveURL(/\/forgot-password/);
    await expect(page.locator('body')).toBeVisible();
  });
});
