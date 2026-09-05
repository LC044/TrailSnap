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

  test('电脑网页的「连接手机 App」生成可扫描二维码', async ({ page }) => {
    await page.goto('/settings#mobile-app');

    await expect(page.getByRole('heading', { name: '连接手机 App', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: '下载 Android App' })).toBeVisible();
    await expect(page.getByText(/当前版本：TrailSnap v\d+\.\d+\.\d+/)).toBeVisible();
    await expect(page.getByRole('link', { name: '下载 Android APK' })).toHaveAttribute(
      'href',
      /\/api\/system\/app-update-download\/\d+\.\d+\.\d+$/,
    );
    await expect(page.getByAltText('TrailSnap Android App 下载二维码')).toBeVisible();
    await expect(page.getByRole('heading', { name: '连接到这台 TrailSnap' })).toBeVisible();

    const addressInput = page.getByLabel('手机可访问的 TrailSnap 地址');
    // dev / system 模式由 Vite config 决定 host；playwright config 会以 localhost 或 127.0.0.1 拉起。
    // 两者都是 loopback, MobileAppConnection 的 isLoopbackAddress 会正确触发「手机无法访问」警告,
    // 此处只校验 addressInput 已被自动填入当前 origin, 不锁具体 hostname.
    await expect(addressInput).toHaveValue(/localhost|127\.0\.0\.1/);
    await expect(page.getByText(/手机无法访问/)).toBeVisible();

    await addressInput.fill('http://192.168.1.20:8082');
    await expect(page.getByAltText('TrailSnap 手机 App 连接二维码')).toBeVisible();
    await expect(page.getByRole('button', { name: '复制连接链接' })).toBeVisible();
  });

  test('切换到「外部图库」- 渲染 ExternalGallery 子页 H2', async ({ page }) => {
    await page.goto('/settings');

    await clickSettingTab(page, 'external');
    await expect(page.getByRole('heading', { name: '外部图库', exact: true })).toBeVisible({ timeout: 10_000 });
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
          version: '0.10.0',
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
    await page.goto('/settings?tab=ai-extensions');
    await clickSettingTab(page, 'ai-extensions');

    await expect(page.locator('h2', { hasText: 'AI 扩展包' })).toBeVisible();
    await expect(page.getByText('TrailSnap AI 基础扩展')).toBeVisible();
    // SidebarTaskManager 也会渲染运行中的 OCR 任务名 '文字识别'，因此把断言限定在主内容区。
    await expect(page.locator('#main-content-wrapper').getByText('文字识别')).toBeVisible();
    // 'exact: true'：llama.cpp 区在 web 模式下也渲染「一键安装」按钮，子串匹配会同时命中两者。
    await expect(page.getByRole('button', { name: '安装', exact: true })).toBeEnabled();
  });

  test('AI 扩展已安装后通过 Server 展示模型管理', async ({ page }) => {
    await page.route('**/desktop-api/ai/extensions', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        platform: 'win32-x64', catalogError: null, gateway: { running: false },
        extensions: [{
          id: 'core-ai', name: 'TrailSnap AI 基础扩展', version: '0.10.0',
          description: '仅包含运行时', capabilities: ['ocr', 'tickets', 'classification'],
          requirements: { memoryMB: 2048, diskMB: 500 }, available: true,
          installed: { version: '0.10.0' }, job: null,
        }],
      }),
    }));
    await page.route('**/api/settings/ai-models', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 0, msg: 'success', data: {
        models: [{
          id: 'yolo_photo_cls_general', name: '图片分类与票据识别模型', status: 'pending',
          description: '用于识别照片和票据', requirements: { memoryMB: 500 },
        }],
        tasks: {
          classification: {
            name: '图片智能分类', selected: 'yolo_photo_cls_general', available: ['yolo_photo_cls_general'],
          },
        },
      } }),
    }));
    await page.goto('/settings?tab=ai-extensions');
    await clickSettingTab(page, 'ai-extensions');
    await clickSettingTab(page, 'ai-models');

    // 'heading' 角色：侧边栏菜单项「AI 模型管理」是 <a> 锚点而非标题，用 heading 精确命中内容区 <h2>。
    await expect(page.getByRole('heading', { name: 'AI 模型管理' })).toBeVisible();
    // 合并模型卡片后（c0605b5），模型名只在 <select> 的 <option> 中出现，Playwright 视 <option> 不可见；
    // 改为断言任务卡片标题「图片智能分类」可见——taskCards 会过滤掉 model 缺失的卡片，
    // 故该 <h3> 可见即说明 yolo_photo_cls_general 已加载并渲染。
    await expect(page.getByRole('heading', { name: '图片智能分类' })).toBeVisible();
    await expect(page.getByRole('button', { name: '下载', exact: true })).toBeEnabled();
  });

  test('连续切换 tasks → external → performance - 内容独立渲染不残留', async ({ page }) => {
    await page.goto('/settings');

    // 任务管理
    await clickSettingTab(page, 'tasks');
    await expect(page.locator('h2', { hasText: '任务管理' }).first()).toBeVisible({ timeout: 10_000 });

    // 切到外部图库 — 任务管理 H2 应消失，外部图库 H2 出现
    await clickSettingTab(page, 'external');
    await expect(page.getByRole('heading', { name: '外部图库', exact: true })).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('h2', { hasText: '任务管理' })).toHaveCount(0);

    // 再切到性能测试 — 前两个 H2 都应消失
    await clickSettingTab(page, 'performance');
    await expect(page.locator('h2', { hasText: '性能测试' }).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('heading', { name: '外部图库', exact: true })).toHaveCount(0);
    await expect(page.locator('h2', { hasText: '任务管理' })).toHaveCount(0);
  });
  test('外部图库可切换到图片文件过滤并返回目录管理', async ({ page }) => {
    await page.goto('/settings');
    await clickSettingTab(page, 'external');

    await page.getByRole('tab', { name: '图片文件过滤' }).click();
    await expect(page.getByText('启用过滤', { exact: true })).toBeVisible();

    await page.getByRole('tab', { name: '目录管理' }).click();
    // 新版目录管理 tab：文件夹列表始终渲染（管理员/普通用户均可见）
    await expect(page.getByRole('heading', { name: '已添加的文件夹', exact: true })).toBeVisible({ timeout: 10_000 });
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
    await expect(page.getByRole('heading', { name: '添加照片目录', exact: true })).toBeVisible({ timeout: 20_000 });
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
