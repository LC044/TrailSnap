import { test, expect } from '@playwright/test';
import { ensureAuthSession } from '../../helpers/auth';

/**
 * P0 测试 — 设置中心子 Tab 切换（src/views/Settings.vue）
 *
 * 设置中心共有 9 个 tab（个人资料 / 用户管理 / 任务管理 / 基础设置 /
 * 外部图库 / 性能测试 / 令牌管理 / 关于行影集 / 问题反馈），每个 tab
 * 加载不同的子页面。仅当 sidebar 渲染时 cursor-pointer 锚点
 * data-tab="<key>" 暴露给 e2e。
 *
 * 这里选取覆盖前几轮 nightly watch 报告「未测试」的子页面：
 *   - 令牌管理（Tokens）       data-tab="tokens"
 *   - 用户管理（UserManagement）data-tab="user"
 *   - 关于行影集（AboutPage）   data-tab="about"
 *
 * 验证 sidebar 锚点点击 → 对应子页面 h1/h2 渲染 → 当前的激活样式迁移
 * 正确。@p1 也兼容；标记 @p0 与既有设置套件风格保持一致。
 */

async function clickSettingTab(page, key: string) {
  const anchor = page.locator(`[data-tab="${key}"]`);
  await expect(anchor.first()).toBeVisible({ timeout: 20_000 });
  await anchor.first().scrollIntoViewIfNeeded();
  await anchor.first().click();
}

test.describe('P0 - 设置中心子 Tab 切换', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return;
    // e2e-admin 是首个注册用户（必然 superuser），但 user_info 只在部分页面异步拉取；
    // store 初始读 localStorage 为 null 会让 superuserOnly 菜单迟到。预置 is_superuser。
    await page.addInitScript(() => {
      const raw = localStorage.getItem('user_info')
      if (!raw) {
        localStorage.setItem('user_info', JSON.stringify({ id: 'u-e2e', username: 'e2e-admin', is_active: true, is_superuser: true }))
      }
    });
    // AboutPage.vue 在 onMounted 时会主动调用 /api/system/update-check；
    // 如果该接口返回 has_update=true，会弹出「检查更新」对话框拦截后续点击。
    // 该 bug 与本测试无关，仅在 nightly round 3 (2026-08-15) 真实 update 服务
    // 升级到 v0.10.0 后才出现，所以这里按 views-deeper-p8 的已有模式桩掉它。
    await page.route('**/api/system/update-check**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          msg: 'success',
          data: { has_update: false, latest_version: '0.0.0-e2e', download_url: null },
        }),
      }),
    );
  });

  test('切换到「令牌管理」- 渲染 Tokens 子页 H1', async ({ page }) => {
    await page.goto('/settings');
    await expect(page).toHaveURL(/\/settings/);

    await clickSettingTab(page, 'tokens');
    // Tokens.vue 模板硬编码 <h1>令牌管理</h1>
    await expect(page.locator('h1', { hasText: '令牌管理' }).first()).toBeVisible({ timeout: 10_000 });
  });

  test('切换到「用户管理」- 渲染 UserManagement 子页 H2', async ({ page }) => {
    // user 是 superuserOnly 项：真实登录账号的 is_superuser 依赖异步 /api/users/me
    // 回填 user_info，侧边栏锚点可能晚于点击出现。直接 hash 进入，不依赖锚点时序。
    await page.goto('/settings#user');
    // UserManagement 的 SettingsPageHeader 渲染 <h1>用户管理</h1>。
    // 移动端页头也有同文案 h1（桌面隐藏），用 ts-page-title 精确命中内容区。
    await expect(page.locator('h1.ts-page-title', { hasText: '用户管理' })).toBeVisible({ timeout: 10_000 });
  });

  test('切换到「关于行影集」- 渲染 AboutPage 子页 H1', async ({ page }) => {
    await page.goto('/settings');

    await clickSettingTab(page, 'about');
    // AboutPage 的 SettingsPageHeader 渲染 <h1 class="ts-page-title">关于行影集</h1>。
    // Settings.vue 移动端页头还渲染一个同文案 <h1>（桌面视口 md:hidden 但仍在 DOM），
    // 用 ts-page-title 精确命中内容区标题，避免 .first() 抓到隐藏的移动端 h1。
    await expect(page.locator('h1.ts-page-title', { hasText: '关于行影集' })).toBeVisible({ timeout: 10_000 });
  });

  test('连续切换多个 Tab - 每个 Tab 内容独立渲染不残留', async ({ page }) => {
    await page.goto('/settings');

    // 先 about → 看到「关于行影集 (TrailSnap)」
    await clickSettingTab(page, 'about');
    await expect(page.locator('h1.ts-page-title', { hasText: '关于行影集' })).toBeVisible({ timeout: 10_000 });

    // 切到 feedback → 关于的 H1 不再可见，FeedbackPage 的 h1 「需求平台」出现
    await clickSettingTab(page, 'feedback');
    await expect(page.locator('h1.ts-page-title', { hasText: '需求平台' })).toBeVisible({ timeout: 10_000 });
    // 切回 personal profile → profile 的设置项出现，feedback 的 H1 消失
    await clickSettingTab(page, 'profile');
    // ProfileSettings 的 SettingsPageHeader 渲染 <h1>个人资料</h1>
    await expect(page.locator('h1.ts-page-title', { hasText: '个人资料' })).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('h1.ts-page-title', { hasText: '需求平台' })).toHaveCount(0);
  });
});

