import { test, expect } from '@playwright/test';
import { ensureAuthSession } from '../../helpers/auth';

/**
 * Smoke 测试 — 设置中心剩余 Tab 切换（src/views/Settings.vue）
 *
 * settings-tabs.spec.ts 已覆盖 profile / user / tokens / about / feedback 五个 tab。
 * 本文件补齐前几轮夜间测试报告标记为「未覆盖」的三项：
 *   - 任务管理（TaskManagement）   data-tab="tasks"
 *   - 外部图库（ExternalGallery）   data-tab="external"
 *   - 性能测试（PerformanceTest）   data-tab="performance"
 *
 * 仅验证 sidebar 锚点点击 → 对应子页面 H2 渲染，遵循既有 settings-tabs 套件风格。
 */

async function clickSettingTab(page, key: string) {
  const anchor = page.locator(`[data-tab="${key}"]`);
  await anchor.first().scrollIntoViewIfNeeded();
  await anchor.first().click();
}

test.describe('Smoke - 设置中心剩余 Tab 切换 @smoke', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return;
  });

  test('切换到「任务管理」- 渲染 TaskManagement 子页 H2', async ({ page }) => {
    await page.goto('/settings');
    await expect(page).toHaveURL(/\/settings/);

    await clickSettingTab(page, 'tasks');
    // TaskManagement.vue 模板硬编码 <h2>任务管理</h2>
    await expect(page.locator('h2', { hasText: '任务管理' }).first()).toBeVisible({ timeout: 10_000 });
  });

  test('切换到「外部图库」- 渲染 ExternalGallery 子页 H2', async ({ page }) => {
    await page.goto('/settings');

    await clickSettingTab(page, 'external');
    // ExternalGallery.vue 模板硬编码 <h2>外部图库管理</h2>
    await expect(page.locator('h2', { hasText: '外部图库管理' }).first()).toBeVisible({ timeout: 10_000 });
  });

  test('切换到「性能测试」- 渲染 PerformanceTest 子页 H2', async ({ page }) => {
    await page.goto('/settings');

    await clickSettingTab(page, 'performance');
    // PerformanceTest.vue 模板硬编码 <h2>性能测试</h2>
    await expect(page.locator('h2', { hasText: '性能测试' }).first()).toBeVisible({ timeout: 10_000 });
  });

  test('连续切换 tasks → external → performance - 内容独立渲染不残留', async ({ page }) => {
    await page.goto('/settings');

    // 任务管理
    await clickSettingTab(page, 'tasks');
    await expect(page.locator('h2', { hasText: '任务管理' }).first()).toBeVisible({ timeout: 10_000 });

    // 切到外部图库 — 任务管理 H2 应消失，外部图库 H2 出现
    await clickSettingTab(page, 'external');
    await expect(page.locator('h2', { hasText: '外部图库管理' }).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('h2', { hasText: '任务管理' })).toHaveCount(0);

    // 再切到性能测试 — 前两个 H2 都应消失
    await clickSettingTab(page, 'performance');
    await expect(page.locator('h2', { hasText: '性能测试' }).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('h2', { hasText: '外部图库管理' })).toHaveCount(0);
    await expect(page.locator('h2', { hasText: '任务管理' })).toHaveCount(0);
  });
});
