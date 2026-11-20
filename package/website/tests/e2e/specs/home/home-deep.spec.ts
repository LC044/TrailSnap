import { test, expect } from '@playwright/test';
import { ensureAuthSession } from '../../helpers/auth';

test.describe('Smoke - 首页深度 @smoke', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return;
  });

  test('首页展示影像手记和主要操作', async ({ page }) => {
    await page.goto('/');
    const main = page.getByRole('main');
    await expect(main.getByRole('heading', { name: '影像手记' })).toBeVisible();
    await expect(main.getByRole('button', { name: '导入照片' })).toBeVisible();
    await expect(main.getByRole('region', { name: '精选影像' })).toBeVisible();
    await expect(main.getByRole('link', { name: '全部照片' })).toBeVisible();
  });

  test('图库概览展开后可进入存储中心', async ({ page }) => {
    await page.goto('/');
    await page.getByText('图库概览', { exact: true }).click();
    await page.getByRole('button', { name: '存储空间管理', exact: true }).click();
    await expect(page.getByRole('dialog', { name: '存储空间管理' })).toBeVisible();
  });

  test('首页年度回忆录入口可见', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('link', { name: '年度回忆录' })).toBeVisible();
  });

  test('首页路由未跳转到 NotFound', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/$/);
    await expect(page.locator('.not-found')).toHaveCount(0);
  });

  test('足迹统计展示城市、省份和记录天数并可跳转', async ({ page }) => {
    await page.route('**/api/location-stats/overview**', route => route.fulfill({
      json: { code: 0, data: { city_count: 8, province_count: 3, travel_days: 42 } },
    }));
    await page.goto('/');
    await expect(page.getByRole('link', { name: /足迹地图.*走过 8 座城市/ })).toHaveAttribute('href', '/footprint');
    await page.getByText('图库概览', { exact: true }).click();
    const footprint = page.getByRole('region', { name: '我的足迹' });
    await expect(footprint.getByRole('button', { name: '记录城市 8 座，查看足迹统计' })).toBeVisible();
    await expect(footprint.getByRole('button', { name: '记录省份 3 个，查看足迹统计' })).toBeVisible();
    await expect(footprint.getByRole('button', { name: '记录天数 42 天，查看足迹统计' })).toBeVisible();
    await footprint.getByRole('button', { name: '查看足迹', exact: true }).click();
    await expect(page).toHaveURL(/\/album\/location$/);
  });

  test('今日新增携带当天导入时间范围进入照片页', async ({ page }) => {
    await page.goto('/');
    await page.getByText('图库概览', { exact: true }).click();
    await page.getByRole('button', { name: /今日新增/ }).click();
    await expect(page).toHaveURL(/\/photos\?.*uploaded_after=.*uploaded_before=/);
    const url = new URL(page.url());
    expect(url.searchParams.get('uploaded_after')).toMatch(/^\d{4}-\d{2}-\d{2}T00:00:00$/);
    expect(url.searchParams.get('uploaded_before')).toMatch(/^\d{4}-\d{2}-\d{2}T00:00:00$/);
  });

  test('精选照片可查看详情并用 Escape 返回手记', async ({ page }) => {
    await page.route('**/api/photos/on-this-day**', route => route.fulfill({
      json: [{
        id: '00000000-0000-0000-0000-000000000112',
        filename: 'on-this-day.jpg',
        photo_time: '2020-08-08T12:00:00',
        file_type: 'image',
        size: 1024,
        width: 800,
        height: 600,
      }],
    }));
    await page.goto('/');
    const open = page.getByRole('region', { name: '精选影像' }).getByRole('button', { name: '打开影像' });
    await open.click();
    await expect(page.getByTitle('查看元数据 (I)')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByTitle('查看元数据 (I)')).toBeHidden();
    await expect(open).toBeFocused();
  });
});
