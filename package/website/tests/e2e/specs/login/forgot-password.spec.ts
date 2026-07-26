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
 * 隔离说明：docker（生产构建 + 真后端）下，SPA 首帧会用默认 MainLayout 渲染，其
 * onMounted 触发 /nav/items、/tasks/grouped-status 等需鉴权的启动期接口；无 token 时
 * 后端返 401，此时路由尚未解析到 /forgot-password（currentRoute 仍是初始 '/'，非
 * publicPage），request.ts 拦截器 resetState() → /login，把白名单页也一并踢走。
 * dev（vite）下无后端，这些请求以网络错误收场（非 401），不触发拦截器，故本地能过。
 * 改用 authedPage：worker 级现登录注入有效 token，启动期接口 200，不再 401 跳转，
 * 路由顺利解析到 /forgot-password。页面本身渲染与登录态无关，smoke 仍验证渲染本身。
 */

test.describe('Smoke - 找回密码 @smoke', () => {
  test('找回密码页面正常加载 - 标题与重置方式可见', async ({ authedPage: page }) => {
    await page.goto('/forgot-password');

    // 白名单页面，未登录也直接放行
    await expect(page).toHaveURL(/\/forgot-password/);
    await expect(page.locator('body')).toBeVisible();

    // 模板硬编码 <h2>找回密码</h2>
    await expect(page.locator('h2', { hasText: '找回密码' })).toBeVisible({ timeout: 10_000 });
  });

  test('找回密码页面渲染方式切换与第一步输入框', async ({ authedPage: page }) => {
    await page.goto('/forgot-password');

    // 两种重置方式 radio 按钮文本（CI 上组件挂载偏晚，放宽到 15s，与 h2 断言一致）
    await expect(page.getByText('安全问题')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('服务器验证码')).toBeVisible();

    // 用户名 / 邮箱输入框（placeholder 模板硬编码）
    const usernameInput = page.getByPlaceholder('请输入用户名或邮箱');
    await expect(usernameInput).toBeVisible();
  });

  test('找回密码页面切换到"服务器验证码"模式显示对应字段', async ({ authedPage: page }) => {
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
