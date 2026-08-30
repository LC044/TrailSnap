import { test, expect } from '@playwright/test';
import { ensureAuthSession } from '../../helpers/auth';

/**
 * Smoke 测试 — 工具箱子页面（src/views/toolbox/*）
 *
 * 覆盖以下此前未单独 smoke 的子路由：
 *   /toolbox/similar  - 相似照片清理
 *   /toolbox/duplicate - 重复照片清理
 *   /toolbox/rename   - 批量重命名
 *   /toolbox/organize - 图片文件整理
 *   /toolbox/time-from-filename - 从文件名修改拍摄信息
 *   /toolbox/cleanup  - 清理相册
 *   /toolbox/ticket-edit - 车票编辑
 *
 * 这些页面普遍依赖后台 SCAN_* 任务，smoke 仅验证页面骨架（h1 / 提示文案 /
 * 主要 CTA 按钮）能正常渲染，不验证扫描结果。
 */

test.describe('Smoke - 工具箱子页面 @smoke', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return;
  });

  test('相似照片清理页面正常加载', async ({ page }) => {
    await page.goto('/toolbox/similar');
    await expect(page).toHaveURL(/\/toolbox\/similar/);
    await expect(page.locator('body')).toBeVisible();
    // SimilarPhotoCleanup.vue 通过 CleanupTaskShell 渲染 title="相似照片清理"
    await expect(page.getByText('相似照片清理').first()).toBeVisible({ timeout: 10_000 });
  });

  test('相似照片最多可同时对比四张并标记删除', async ({ page }) => {
    const taskId = '11111111-1111-4111-8111-111111111111';
    const photos = Array.from({ length: 5 }, (_, index) => ({
      id: `22222222-2222-4222-8222-22222222222${index}`,
      filename: `burst-${index + 1}.jpg`,
      photo_time: `2026-08-30T10:00:0${index}`,
      upload_time: `2026-08-30T10:01:0${index}`,
      url: `/api/medias/22222222-2222-4222-8222-22222222222${index}/file`,
      thumbnail_url: `/api/medias/22222222-2222-4222-8222-22222222222${index}/thumbnail`,
      file_type: 'image',
      size: 2_000_000 + index,
      width: 4032,
      height: 3024,
    }));

    await page.route('**/api/toolbox/similar/tasks/latest', route => route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        msg: 'success',
        data: {
          id: taskId,
          type: 'SIMILAR_PHOTO_CLUSTERING',
          status: 'completed',
          created_at: '2026-08-30T10:00:00',
          updated_at: '2026-08-30T10:00:00',
          total_items: 5,
          processed_items: 5,
          result: null,
        },
      }),
    }));
    await page.route(`**/api/toolbox/similar/tasks/${taskId}/result*`, route => route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ code: 0, msg: 'success', data: [photos] }),
    }));
    await page.route('**/api/medias/**', route => route.fulfill({
      contentType: 'image/svg+xml',
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300"><rect width="100%" height="100%" fill="#9ca3af"/></svg>',
    }));

    await page.goto('/toolbox/similar');
    await expect(page.getByText('分组 1 (5 张)')).toBeVisible();
    await page.getByRole('button', { name: '对比照片' }).click();

    const dialog = page.getByRole('dialog');
    await expect(dialog.getByText('照片对比')).toBeVisible();
    await expect(dialog.locator('article')).toHaveCount(4);
    await dialog.getByRole('button', { name: /标记删除/ }).first().click();
    await expect(dialog.getByText('已标记 1 张')).toBeVisible();
  });

  test('重复照片清理页面正常加载', async ({ page }) => {
    await page.goto('/toolbox/duplicate');
    await expect(page).toHaveURL(/\/toolbox\/duplicate/);
    await expect(page.locator('body')).toBeVisible();
    await expect(page.getByText('重复照片清理').first()).toBeVisible({ timeout: 10_000 });
  });

  test('批量重命名页面正常加载 - 标题与说明可见', async ({ page }) => {
    await page.goto('/toolbox/rename');
    await expect(page).toHaveURL(/\/toolbox\/rename/);
    await expect(page.locator('body')).toBeVisible();
    // RenamePage.vue 模板硬编码 <h1>批量重命名</h1>
    await expect(page.locator('h1', { hasText: '批量重命名' })).toBeVisible({ timeout: 10_000 });
    // 操作说明文案（YYYYMMDD_HHMMSS）
    await expect(page.getByText(/YYYYMMDD_HHMMSS/)).toBeVisible();
  });

  test('图片文件整理页面正常加载', async ({ page }) => {
    await page.goto('/toolbox/organize');
    await expect(page).toHaveURL(/\/toolbox\/organize/);
    await expect(page.locator('body')).toBeVisible();
  });

  test('从文件名修改拍摄信息页面正常加载', async ({ page }) => {
    await page.goto('/toolbox/time-from-filename');
    await expect(page).toHaveURL(/\/toolbox\/time-from-filename/);
    await expect(page.locator('body')).toBeVisible();
  });

  test('清理相册页面正常加载', async ({ page }) => {
    await page.goto('/toolbox/cleanup');
    await expect(page).toHaveURL(/\/toolbox\/cleanup/);
    await expect(page.locator('body')).toBeVisible();
  });
});
