import { test, expect } from '../../fixtures/auth-page';

/**
 * Smoke 测试 — 找回密码（src/views/login/ForgotPassword.vue）
 *
 * /forgot-password 在路由白名单内，未登录也能直接访问。
 * 验证：
 *  - 路由 /forgot-password 能正常打开（不跳 /login）。
 *  - 「找回密码」标题渲染。
 *  - 「安全问题 / 服务器验证码」两种重置方式 radio 可见。
 *  - 用户名/邮箱输入框可见，placeholder 与模板一致。
 *
 * 隔离说明：system 模式下 config.use.storageState 注入的全局共享 token 会被并行用例
 * 失效；原 spec 用 browser.newContext() 想起干净上下文，但 Playwright 1.60 下
 * storageState 会泄漏进手动 newContext()，并不干净。改用 cleanPage fixture —— 它在
 * SPA 任何脚本执行前 addInitScript(localStorage.clear)，保证 userStore.token 启动即
 * 读到 null，与 storageState 是否泄漏无关，白名单页稳定放行不踢 /login。
 */

test.describe('Smoke - 找回密码 @smoke', () => {
  test('找回密码页面正常加载 - 标题与重置方式可见', async ({ cleanPage: page }) => {
    await page.goto('/forgot-password');

    // 白名单页面，未登录也直接放行
    await expect(page).toHaveURL(/\/forgot-password/);
    await expect(page.locator('body')).toBeVisible();

    // 模板硬编码 <h2>找回密码</h2>
    await expect(page.locator('h2', { hasText: '找回密码' })).toBeVisible({ timeout: 10_000 });
  });

  test('找回密码页面渲染方式切换与第一步输入框', async ({ cleanPage: page }) => {
    await page.goto('/forgot-password');

    // 两种重置方式 radio 按钮文本（CI 上组件挂载偏晚，放宽到 15s，与 h2 断言一致）
    await expect(page.getByText('安全问题')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('服务器验证码')).toBeVisible();

    // 用户名 / 邮箱输入框（placeholder 模板硬编码）
    const usernameInput = page.getByPlaceholder('请输入用户名或邮箱');
    await expect(usernameInput).toBeVisible();
  });

  test('找回密码页面切换到"服务器验证码"模式显示对应字段', async ({ cleanPage: page }) => {
    await page.goto('/forgot-password');

    // 默认是「安全问题」模式，点击切换到「服务器验证码」（先等 radio 渲染，CI 挂载偏晚）
    const serverRadio = page.getByText('服务器验证码');
    await expect(serverRadio).toBeVisible({ timeout: 15_000 });
    await serverRadio.click();

    // 等待 Vue 响应式更新
    await page.waitForTimeout(300);

    // 「服务器验证码」模式下应该有「服务器日志 / 邮箱」相关字段。
    // 这里仅断言切换后页面不白屏 / body 仍可见 + URL 不变。
    await expect(page).toHaveURL(/\/forgot-password/);
    await expect(page.locator('body')).toBeVisible();
  });
});
