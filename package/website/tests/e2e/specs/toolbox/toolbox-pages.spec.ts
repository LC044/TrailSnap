import { test, expect } from '@playwright/test';
import { ensureAuthSession } from '../../helpers/auth';

/**
 * Smoke 测试 — 工具箱子页面（src/views/toolbox/*）
 *
 * REQ-238 重构后，similar / duplicate / cleanup / organize / rename /
 * time-from-filename / albums 全部由 ToolWorkflowPage 承载，首屏统一是
 * 「选择范围」；各页面的 h1 由 props.kind 决定（清理类统一为「照片清理」）。
 * smoke 只验证页面骨架与工作流入口，不依赖扫描结果或真实数据。
 */

test.describe('Smoke - 工具箱子页面 @smoke', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return;
  });

  test('相似照片清理页面正常加载', async ({ page }) => {
    await page.goto('/toolbox/similar');
    await expect(page).toHaveURL(/\/toolbox\/similar/);
    await expect(page.locator('body')).toBeVisible();
    // 相似/重复/低分清理共用 kind=cleanup 的 ToolWorkflowPage，标题为「照片清理」。
    await expect(page.locator('h1.ts-page-title', { hasText: '相似照片' })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('group', { name: '范围来源' })).toBeVisible();
    await expect(page.getByRole('group', { name: '范围来源' })).toBeVisible();
  });

  test('相似照片工作流从范围选择开始，不直接加载聚类结果', async ({ page }) => {
    await page.goto('/toolbox/similar');
    await expect(page.locator('h1.ts-page-title', { hasText: '相似照片' })).toBeVisible({ timeout: 10_000 });
    // 旧版「对比照片」弹窗 /「标记删除」按钮已由持久化预览计划替代；
    // 首屏不再拉取聚类结果，也不会默认处理整个图库。
    await expect(page.getByRole('group', { name: '范围来源' }).getByRole('button', { name: '相册', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByRole('button', { name: /^(查看效果|查找候选照片)$/ })).toBeDisabled();
    await expect(page.getByRole('button', { name: '对比照片' })).toHaveCount(0);
  });

  test('重复照片清理页面正常加载', async ({ page }) => {
    await page.goto('/toolbox/duplicate');
    await expect(page).toHaveURL(/\/toolbox\/duplicate/);
    await expect(page.locator('body')).toBeVisible();
    await expect(page.locator('h1.ts-page-title', { hasText: '重复照片' })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('group', { name: '范围来源' })).toBeVisible();
    await expect(page.getByRole('group', { name: '范围来源' })).toBeVisible();
  });

  test('批量重命名页面正常加载 - 标题与工作流骨架可见', async ({ page }) => {
    await page.goto('/toolbox/rename');
    await expect(page).toHaveURL(/\/toolbox\/rename/);
    await expect(page.locator('body')).toBeVisible();
    await expect(page.locator('h1.ts-page-title', { hasText: '批量重命名' })).toBeVisible({ timeout: 10_000 });
    // 模板说明（YYYYMMDD_HHMMSS 等）现在属于第二步的 RenameTemplateEditor，首屏只显示范围选择。
    await expect(page.getByRole('group', { name: '范围来源' })).toBeVisible();
    await expect(page.getByRole('group', { name: '范围来源' })).toBeVisible();
    await expect(page.getByRole('button', { name: /^(查看效果|查找候选照片)$/ })).toBeDisabled();
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
