/**
 * P1 - 回收站清理优化（src/views/RecycleBinPage.vue）
 *
 * 覆盖本次新增的交互，这些路径原先完全没有 e2e：
 *  - 「全选」跨页语义：stats 报告 500 项但列表只返回 1 页时，标题应显示总量
 *    而非已加载数量，并出现「包含尚未加载的 N 项」提示。
 *  - 「清空回收站」：不带任何 id 调用 POST /purge（photo_ids = null），
 *    这是不下拉加载也能清空的关键契约。
 *  - 大批量转异步：purge 返回 mode=async 时出现进度条，并轮询 job 接口，
 *    完成后刷新列表 —— 前端不再阻塞在一个会超时的请求上。
 *  - 「加载更多」按钮：无限滚动在嵌套滚动容器下不可靠，显式按钮是兜底。
 *
 * 全部用 page.route mock 后端，因此不依赖真实照片数据。注意 mock 顺序：
 * 更具体的 /stats、/purge 必须在宽泛的列表路由之前注册，否则会被前者吞掉。
 */

import { test, expect } from '@playwright/test';
import { ensureAuthSession } from '../../helpers/auth';

/** 造 n 条回收站照片，字段与 mapPhotoToImage 期望的形状一致 */
function makePhotos(n: number, offset = 0) {
  return Array.from({ length: n }, (_, i) => ({
    id: `photo-${offset + i}`,
    filename: `p${offset + i}.jpg`,
    file_type: 'image',
    takenAt: new Date(Date.now() - 2 * 86400_000).toISOString(),
    size: 1234,
    width: 100,
    height: 100,
    deleted_at: new Date(Date.now() - 86400_000).toISOString(),
  }));
}

test.describe('P1 - 回收站清理优化 @recycle-bin', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return;
  });

  test('stats 提供总量 - 标题显示「共 N 项」而非已加载数', async ({ page }) => {
    await page.route('**/api/photos/recycle-bin/stats**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, msg: 'success', data: { total: 500, retention_days: 7 } }),
      }),
    );
    // 列表只回 3 条，与 total=500 故意不一致，用于证明总量来自 stats
    await page.route('**/api/photos/recycle-bin?**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, msg: 'success', data: makePhotos(3) }),
      }),
    );

    await page.goto('/recycle-bin');
    await expect(page.getByText('共 500 项')).toBeVisible({ timeout: 10_000 });
  });

  test('清空回收站 - 请求体 photo_ids 为 null（无需枚举 id）', async ({ page }) => {
    await page.route('**/api/photos/recycle-bin/stats**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, msg: 'success', data: { total: 42, retention_days: 7 } }),
      }),
    );

    let purgeBody: any = null;
    await page.route('**/api/photos/recycle-bin/purge', async (route) => {
      purgeBody = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          msg: 'success',
          data: { mode: 'sync', total: 42, deleted: 42, message: 'ok' },
        }),
      });
    });

    await page.route('**/api/photos/recycle-bin?**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, msg: 'success', data: makePhotos(2) }),
      }),
    );

    await page.goto('/recycle-bin');
    await expect(page.getByText('共 42 项')).toBeVisible({ timeout: 10_000 });

    // 桌面端「更多操作」下拉里的「清空回收站」
    await page.locator('button[title="更多操作"]').click();
    await page.getByText('清空回收站').click();

    // 确认对话框
    const confirmBtn = page.getByRole('button', { name: '确定' }).last();
    await expect(confirmBtn).toBeVisible({ timeout: 5_000 });
    await confirmBtn.click();

    await expect.poll(() => purgeBody, { timeout: 8_000 }).not.toBeNull();
    // 关键契约：清空不枚举 id
    expect(purgeBody).toHaveProperty('photo_ids', null);
  });

  test('大批量转异步 - 出现进度条并轮询 job 状态', async ({ page }) => {
    await page.route('**/api/photos/recycle-bin/stats**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, msg: 'success', data: { total: 5000, retention_days: 7 } }),
      }),
    );

    await page.route('**/api/photos/recycle-bin/purge', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          msg: 'success',
          data: { mode: 'async', job_id: 'job-e2e', status: 'running', total: 5000, processed: 0, progress: 0 },
        }),
      }),
    );

    let polls = 0;
    await page.route('**/api/photos/recycle-bin/purge/job-e2e', (route) => {
      polls += 1;
      // 前两次仍在跑，第三次完成 —— 验证轮询真的在循环
      const done = polls >= 3;
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          msg: 'success',
          data: {
            job_id: 'job-e2e',
            status: done ? 'completed' : 'running',
            total: 5000,
            processed: done ? 5000 : 2000,
            deleted: done ? 5000 : 0,
            progress: done ? 100 : 40,
          },
        }),
      });
    });

    await page.route('**/api/photos/recycle-bin?**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, msg: 'success', data: makePhotos(2) }),
      }),
    );

    await page.goto('/recycle-bin');
    await expect(page.getByText('共 5000 项')).toBeVisible({ timeout: 10_000 });

    await page.locator('button[title="更多操作"]').click();
    await page.getByText('清空回收站').click();
    await page.getByRole('button', { name: '确定' }).last().click();

    // 进度条出现，说明没有阻塞在同步请求上
    await expect(page.getByText('正在清理回收站…')).toBeVisible({ timeout: 8_000 });
    // 轮询确实发生了多次
    await expect.poll(() => polls, { timeout: 15_000 }).toBeGreaterThanOrEqual(3);
    // 完成后进度条消失
    await expect(page.getByText('正在清理回收站…')).toBeHidden({ timeout: 10_000 });
  });

  test('「加载更多」按钮存在并追加下一页', async ({ page }) => {
    await page.route('**/api/photos/recycle-bin/stats**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, msg: 'success', data: { total: 400, retention_days: 7 } }),
      }),
    );

    // 第一页满 200 条 => hasMore=true => 按钮可见
    let call = 0;
    await page.route('**/api/photos/recycle-bin?**', (route) => {
      const page1 = call === 0;
      call += 1;
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          msg: 'success',
          data: page1 ? makePhotos(200) : makePhotos(5, 200),
        }),
      });
    });

    await page.goto('/recycle-bin');
    const moreBtn = page.getByRole('button', { name: /加载更多/ });
    await expect(moreBtn).toBeVisible({ timeout: 10_000 });

    // Virtualized list re-renders can detach this button between pointer actionability checks.
    await moreBtn.dispatchEvent('click');
    // 第二页返回 5 条(<200) => hasMore=false => 按钮消失
    await expect(moreBtn).toBeHidden({ timeout: 10_000 });
    await expect(page.getByText(/已加载 205/)).toBeVisible();
  });

  test('stats 接口异常时页面仍可用（降级不崩）', async ({ page }) => {
    await page.route('**/api/photos/recycle-bin/stats**', (route) =>
      route.fulfill({ status: 500, contentType: 'application/json', body: '{}' }),
    );
    await page.route('**/api/photos/recycle-bin?**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, msg: 'success', data: makePhotos(3) }),
      }),
    );

    await page.goto('/recycle-bin');

    // 列表照常渲染，标题仍在，说明 stats 失败只是降级
    await expect(page.locator('h1', { hasText: '最近删除' })).toBeVisible({ timeout: 10_000 });
    await expect(page).toHaveURL(/\/recycle-bin/);
  });
});
