import { test, expect } from '@playwright/test';
import { ensureAuthSession } from '../../helpers/auth';

/**
 * E2E 测试 — 移动端搜索全屏面板（src/views/search/MobileSearch.vue）
 *
 * /mobile-search 是 mobile 端的全屏搜索入口（layout: 'blank'），不走
 * 桌面 /search 路由；这一页一直缺少 smoke / p0 覆盖，所以这里集中补齐：
 *
 *  - smoke : 路由可达、模板骨架（搜索输入框、占位符、空态文案）可见
 *  - p0    : 输入文字后渲染 AI 语义搜索 CTA / 清除按钮；清除后回到空态
 *  - p1    : Enter 键直接跳到 /search?q=...，与桌面端行为一致
 *
 * 与 e2e /search 不同：mobile-search 是「输入 → 选择 → 跳转」三段式，这里
 * 只验证每个交互段的 UI 反馈，而不是验证 /search 结果列表本身（那是 p0
 * search 套件的事）。
 */
test.describe('E2E - 移动端搜索面板', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return;
  });

  test('smoke - 移动搜索面板可打开 - 搜索输入与空态可见', async ({ page }) => {
    await page.goto('/mobile-search');
    await expect(page).toHaveURL(/\/mobile-search/);
    await expect(page.locator('body')).toBeVisible();

    // 模板硬编码：input placeholder="搜索照片、地点、人物..."
    const searchInput = page.locator('input[placeholder*="搜索照片"]');
    await expect(searchInput).toBeVisible({ timeout: 10_000 });

    // 空态：搜索图标 + 「开始搜索您的精彩瞬间」提示
    await expect(page.getByText('开始搜索您的精彩瞬间')).toBeVisible({ timeout: 10_000 });
  });

  test('smoke - 顶部返回按钮可见', async ({ page }) => {
    await page.goto('/mobile-search');
    // 模板里返回按钮带 ArrowLeft 图标，无文字 label；用 svg 父按钮定位
    const backButton = page.locator('button').filter({ has: page.locator('svg').first() }).first();
    await expect(backButton).toBeVisible({ timeout: 5_000 });
  });

  test('p0 - 输入文字后渲染 AI 语义搜索 CTA 与清除按钮', async ({ page }) => {
    await page.goto('/mobile-search');

    const searchInput = page.locator('input[placeholder*="搜索照片"]');
    await expect(searchInput).toBeVisible({ timeout: 10_000 });
    await searchInput.fill('日落');

    // AI 语义搜索 CTA：「画面识别: "日落"」+ 「使用AI进行语义搜索: "日落"」之一可见
    const aiCta = page.getByText(/使用AI进行语义搜索|画面识别/).first();
    await expect(aiCta).toBeVisible({ timeout: 10_000 });

    // 清除按钮 (X) 在 searchText 非空时才渲染
    const clearButton = page.locator('button').filter({ has: page.locator('svg').nth(3) }).last();
    // 用更精确的选择：v-if="searchText" 包裹的按钮里仅有 X 图标
    const xButton = page.locator('button:has(svg)').filter({ hasText: '' }).filter({ has: page.locator('.lucide-x') });
    await expect(xButton.first()).toBeVisible();
  });

  test('p0 - 点击清除按钮后回到空态', async ({ page }) => {
    await page.goto('/mobile-search');

    const searchInput = page.locator('input[placeholder*="搜索照片"]');
    await expect(searchInput).toBeVisible({ timeout: 10_000 });
    await searchInput.fill('北京');

    // 出现清除按钮
    const xButton = page.locator('button:has(.lucide-x)');
    await expect(xButton.first()).toBeVisible({ timeout: 5_000 });
    await xButton.first().click();

    // 文本清空，空态恢复
    await expect(searchInput).toHaveValue('');
    await expect(page.getByText('开始搜索您的精彩瞬间')).toBeVisible({ timeout: 5_000 });
  });

  test('p1 - 输入文字后按 Enter 跳转到 /search?q=', async ({ page }) => {
    await page.goto('/mobile-search');

    const searchInput = page.locator('input[placeholder*="搜索照片"]');
    await expect(searchInput).toBeVisible({ timeout: 10_000 });
    await searchInput.fill('西湖');
    await searchInput.press('Enter');

    // handleSearch() 走 router.push({ path: '/search', query: { q: '西湖' } })
    await page.waitForURL(/\/search\?.*q=/, { timeout: 10_000 });
    const url = new URL(page.url());
    expect(url.pathname).toBe('/search');
    expect(url.searchParams.get('q')).toBe('西湖');
  });
});
