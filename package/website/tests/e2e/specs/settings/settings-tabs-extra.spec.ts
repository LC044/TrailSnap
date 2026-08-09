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

  test('切换到「AI 扩展包」- 展示桌面扩展状态和能力', async ({ page }) => {
    await page.route('**/desktop-api/ai/extensions', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        platform: 'win32-x64',
        catalogError: null,
        gateway: { running: false },
        extensions: [{
          id: 'core-ai',
          name: 'TrailSnap AI 基础扩展',
          version: '0.9.2',
          description: '提供 OCR、票据识别和图片分类',
          capabilities: ['ocr', 'tickets', 'classification'],
          requirements: { memoryMB: 2048, diskMB: 500 },
          available: true,
          downloadSize: 200 * 1024 * 1024,
          installed: null,
          job: null,
        }],
      }),
    }));
    await page.goto('/settings');
    await clickSettingTab(page, 'ai-extensions');

    await expect(page.locator('h2', { hasText: 'AI 扩展包' })).toBeVisible();
    await expect(page.getByText('TrailSnap AI 基础扩展')).toBeVisible();
    await expect(page.getByText('文字识别')).toBeVisible();
    await expect(page.getByRole('button', { name: '安装' })).toBeEnabled();
  });

  test('AI 扩展已安装后通过 Server 展示模型管理', async ({ page }) => {
    await page.route('**/desktop-api/ai/extensions', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        platform: 'win32-x64', catalogError: null, gateway: { running: false },
        extensions: [{
          id: 'core-ai', name: 'TrailSnap AI 基础扩展', version: '0.9.2',
          description: '仅包含运行时', capabilities: ['ocr', 'tickets', 'classification'],
          requirements: { memoryMB: 2048, diskMB: 500 }, available: true,
          installed: { version: '0.9.2' }, job: null,
        }],
      }),
    }));
    await page.route('**/api/settings/ai-models', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 0, msg: 'success', data: { models: [{
        id: 'desktop-core-models', name: '桌面 AI 基础模型', status: 'pending',
        description: 'OCR、票据和分类模型', requirements: { diskMB: 600 },
      }] } }),
    }));
    await page.goto('/settings');
    await clickSettingTab(page, 'ai-extensions');

    await expect(page.getByText('AI 模型管理')).toBeVisible();
    await expect(page.getByText('桌面 AI 基础模型')).toBeVisible();
    await expect(page.getByRole('button', { name: '下载模型' })).toBeEnabled();
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
  test('外部图库可切换到图片文件过滤并返回目录管理', async ({ page }) => {
    await page.goto('/settings');
    await clickSettingTab(page, 'external');

    await page.getByRole('tab', { name: '图片文件过滤' }).click();
    await expect(page.getByText('启用过滤', { exact: true })).toBeVisible();

    await page.getByRole('tab', { name: '目录管理' }).click();
    // 新版目录管理 tab：已接入图库列表始终渲染（管理员/普通用户均可见）
    await expect(page.locator('h3', { hasText: '已接入图库' })).toBeVisible({ timeout: 10_000 });
  });

  test('外部图库空路径时手动添加禁用且不发起添加请求', async ({ page }) => {
    // 该用例依赖异步 getUserInfo（isSuperuser gating）+ 折叠展开，CI 偶发 30s 预算吃紧
    test.setTimeout(60000);
    await page.goto('/settings');
    await clickSettingTab(page, 'external');

    let addDirectoryRequests = 0;
    page.on('request', request => {
      if (request.method() === 'POST' && request.url().includes('/api/settings/directories')) {
        addDirectoryRequests += 1;
      }
    });

    // 先等管理员区就绪（isSuperuser 依赖异步 getUserInfo），再展开手动添加折叠；
    // 用子串匹配折叠标题，兼容「手动输入容器内路径 / 手动输入路径」两种文案
    await expect(page.locator('h3', { hasText: '照片目录接入' })).toBeVisible({ timeout: 20_000 });
    await page.getByText('高级：手动输入').click();
    // 空路径时「添加并扫描」禁用；点「校验」提示请输入路径；且不发起 add 请求
    await expect(page.getByRole('button', { name: '添加并扫描' })).toBeVisible();
    await expect(page.getByRole('button', { name: '添加并扫描' })).toBeDisabled();
    await page.getByRole('button', { name: '校验' }).click();
    await expect(page.getByText('请输入路径')).toBeVisible();
    await expect(page.getByRole('tab', { name: '目录管理' })).toHaveAttribute('aria-selected', 'true');
    expect(addDirectoryRequests).toBe(0);
  });

  test('性能测试空路径提交显示校验提示且保持停止状态', async ({ page }) => {
    await page.goto('/settings');
    await clickSettingTab(page, 'performance');

    const startButton = page.getByRole('button', { name: '开始测试' });
    const stopButton = page.getByRole('button', { name: '停止监控' });
    await expect(stopButton).toBeDisabled();

    await startButton.click();
    await expect(page.getByText('请输入测试用的外部文件夹绝对路径', { exact: true })).toBeVisible();
    await expect(startButton).toBeEnabled();
    await expect(stopButton).toBeDisabled();
  });

  test('性能测试填写路径后可取消确认且不会添加目录', async ({ page }) => {
    await page.goto('/settings');
    await clickSettingTab(page, 'performance');

    let addDirectoryRequests = 0;
    page.on('request', request => {
      if (request.method() === 'POST' && request.url().includes('/api/settings/directories')) {
        addDirectoryRequests += 1;
      }
    });

    await page.getByPlaceholder(/输入测试用的外部文件夹绝对路径/).fill('C:\\Photos\\E2E-Cancel');
    await page.getByRole('button', { name: '开始测试' }).click();
    await expect(page.getByRole('dialog', { name: '确认测试' })).toBeVisible();
    await page.getByRole('button', { name: '取消' }).click();

    await expect(page.getByRole('dialog', { name: '确认测试' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: '停止监控' })).toBeDisabled();
    expect(addDirectoryRequests).toBe(0);
  });
});
