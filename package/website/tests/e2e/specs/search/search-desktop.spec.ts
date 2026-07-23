import { test, expect } from '@playwright/test';
import { ensureAuthSession } from '../../helpers/auth';

/**
 * Smoke - 桌面端搜索结果页（src/views/search/SearchResult.vue）。
 *
 * /search 此前只有 search.spec.ts 一条简单 smoke，缺少对 query 参数路由 /
 * 标题渲染 / 空态文案 / 顶部 header 的深度验证。本文件补齐：
 *   - 默认无 query 时显示"搜索结果"标题
 *   - 带 ?q= 参数时标题渲染"搜索: xxx"
 *   - 顶部返回按钮可见
 *   - 空 query 时显示 empty state 文案（验证与有数据分支同样能渲染）
 *   - 头部副标题文案随加载/数据状态切换
 */
test.describe('Smoke - 桌面端搜索结果页 @smoke', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return;
  });

  test('默认无 query - 标题显示"搜索结果"', async ({ page }) => {
    await page.goto('/search');
    await expect(page).toHaveURL(/\/search/);
    await expect(page.locator('h1', { hasText: '搜索结果' }).first()).toBeVisible({ timeout: 10_000 });
  });

  test('带 ?q=test - 标题渲染"搜索: test"且 URL 保留参数', async ({ page }) => {
    await page.goto('/search?q=test');
    await expect(page).toHaveURL(/\/search\?q=test/);
    await expect(page.locator('h1', { hasText: '搜索: test' }).first()).toBeVisible({ timeout: 10_000 });
  });

  test('顶部返回按钮可见 - main 区域首个 sticky 按钮', async ({ page }) => {
    await page.goto('/search?q=smoke');
    // 返回按钮在 main > .sticky header 内，锚定 main 区域避免与侧边栏的 sticky 搜索按钮混淆
    const backButton = page.locator('main .sticky button').first();
    await expect(backButton).toBeVisible({ timeout: 10_000 });
  });

  test('空 query 时进入 empty 状态 - 文案"未找到相关照片"可见', async ({ page }) => {
    // 当 query 为空时，结果列表为空，进入 empty 状态（不受样本数量影响）
    await page.goto('/search');
    await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => {});

    await expect(page.getByText('未找到相关照片')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('尝试更换搜索关键词')).toBeVisible();
  });

  test('头部副标题元素可见 - 渲染计数或加载文案', async ({ page }) => {
    await page.goto('/search');
    await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => {});

    // subtitle 计算属性：loading 时 "搜索中..."，否则 "N 个结果" 或 "N+ 个结果"
    // 直接定位 main .sticky p 段落元素并断言文本匹配三种合法文案
    const subtitleEl = page.locator('main .sticky p').first();
    await expect(subtitleEl).toBeVisible({ timeout: 10_000 });
    const text = (await subtitleEl.textContent()) || '';
    expect(text).toMatch(/(搜索中|个结果)/);
  });
});
