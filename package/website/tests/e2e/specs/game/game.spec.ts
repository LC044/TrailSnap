import { test, expect } from '@playwright/test';
import { ensureAuthSession } from '../../helpers/auth';

/**
 * Smoke 测试 — 猜城市游戏页（src/views/game/GuessCity.vue）
 *
 * 验证：
 *  - 路由 /game 能正常打开（页面 + 主交互骨架存在）。
 *  - 标题「猜城市」渲染。
 *  - 输入框 / 时间提示区块可见。
 *
 * 该游戏依赖带位置信息的照片（GET /game/startPhoto），无数据时组件会渲染
 * "暂无可用的照片" 兜底页（仍然有可点击的"重新加载"按钮）。Smoke 阶段不
 * 验证游戏逻辑，只验证页面骨架能渲染——数据缺失的兜底页也视为页面存活。
 */

test.describe('Smoke - 猜城市游戏页 @smoke', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return;
  });

  test('猜城市页面正常加载 - 标题与提示文案可见', async ({ page }) => {
    await page.goto('/game');

    // 路由保护：未登录会跳 /login，套件已注入 token 因此不会跳走
    await expect(page).toHaveURL(/\/game/);
    await expect(page.locator('body')).toBeVisible();

    // 标题：GuessCity.vue 模板里硬编码 <h1>猜城市</h1>
    await expect(page.locator('h1', { hasText: '猜城市' }).first()).toBeVisible({ timeout: 10_000 });
  });

  test('猜城市页面渲染出时间提示区块或空态文案', async ({ page }) => {
    await page.goto('/game');

    // 等待懒加载组件 mount；网络空闲容错避免空数据时 5xx 长尾
    await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => {});

    // 至少命中以下其中一项：
    //   - 有数据时：「时间提示：xxxxx」
    //   - 无数据时：「暂无可用的照片」
    const hasTimeHint = await page.getByText(/时间提示[:：]/).count();
    const hasEmpty = await page.getByText('暂无可用的照片').count();
    expect(hasTimeHint + hasEmpty).toBeGreaterThan(0);
  });
});

