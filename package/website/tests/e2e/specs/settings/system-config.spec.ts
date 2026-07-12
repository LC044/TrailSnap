import { test, expect, type Page } from '@playwright/test';
import { e2eEnv } from '../../../../playwright/e2e-env';

/**
 * 系统设置 -「允许新用户注册」开关 端到端测试（日常开发 / dev 套件）
 *
 * 验证「设置中心 → 基础设置 → 安全设置 → 允许新用户注册」开关：
 *   - 仅超级用户可访问/修改（普通用户 GET /system/config 返回 403 → 用例 skip）
 *   - 切换开关并保存后，后端 /system/config.security.allow_registration 实时变化
 *   - 该变化立即影响 /auth/register 的可用性（开 → 可注册；关 → 403）
 *   - 用例始终以「关闭」态收尾，避免污染全局配置
 *
 * 账号：使用 e2eEnv.testUsername / testPassword（即 dev-global-setup 实际登录/注册的
 *       账号；本地 dev 环境通常就是首个注册的超级用户）。既有库需提前把该账号设为
 *       超级用户，否则本用例会在 403 探针处 skip。
 *
 * 收尾状态：用例以「允许新用户注册 = 开启」收尾，保证 login 等依赖 /auth/register 的
 *       套件在本用例之后（或下一轮）能正常注册测试账号。
 *
 * 注意：所有后端调用走 page.request（与前端同源/同代理），避免独立的
 *       APIRequestContext 在某些环境下对 GET 返回陈旧结果。
 */

const ADMIN = { username: e2eEnv.testUsername, password: e2eEnv.testPassword };

test.describe('系统设置-开放注册开关 @settings @system-config', () => {
  // 本文件从零开始，不使用全局已登录 storageState（否则 /login 会被路由守卫弹走）
  test.use({ storageState: { cookies: [], origins: [] } });

  /** 通过页面上下文读取当前 allow_registration（需超级用户 token） */
  async function getAllowRegistration(page: Page, token: string): Promise<boolean> {
    const res = await page.request.get('/api/system/config', {
      headers: { Authorization: `Bearer ${token}` },
    });
    const cfg = (await res.json()) as { security?: { allow_registration?: boolean } };
    return !!cfg.security?.allow_registration;
  }

  test('切换「允许新用户注册」后实时影响注册可用性，并以关闭态收尾', async ({
    page,
  }) => {
    // 1) 以管理员身份登录（开关仅在超级用户下可用）
    await page.goto('/login');
    await page.fill('input[placeholder="请输入用户名"]', ADMIN.username);
    await page.fill('input[placeholder="请输入密码"]', ADMIN.password);
    await page.click('button:has-text("登录")');
    await expect(
      page.locator('.el-message', { hasText: '登录成功' }),
    ).toBeVisible({ timeout: 8_000 });
    await page.waitForURL((u) => !u.pathname.includes('/login'), {
      timeout: 10_000,
    });

    const token = await page.evaluate(() =>
      localStorage.getItem('user_token'),
    );

    // 2) 非超级用户无法访问系统配置 → 跳过（不污染，不误报）
    const probeCfg = await page.request.get('/api/system/config', {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (probeCfg.status() === 403) {
      test.skip(true, '当前登录账号不是超级用户，无法访问/修改系统配置');
    }
    const before = await getAllowRegistration(page, token);

    // 3) 进入 基础设置 → 展开 安全设置 折叠区（默认收起）
    await page.goto('/settings#basic');
    const secHeader = page.locator('.el-collapse-item__header', {
      hasText: '安全设置',
    });
    await secHeader.click();

    const secItem = page.locator('.el-form-item', {
      hasText: '允许新用户注册',
    });
    const sw = secItem.locator('.el-switch');
    const swInput = sw.locator('input');

    // 等待「安全设置」面板与开关渲染完成，并加载出服务端真实值
    await expect(sw).toBeVisible({ timeout: 10_000 });
    await expect(swInput).toHaveAttribute(
      'aria-checked',
      String(before),
      { timeout: 10_000 },
    );

    /** 将开关驱动到指定状态（点击直至 aria-checked 匹配），再保存 */
    async function setSwitch(desired: boolean) {
      const cur = (await swInput.getAttribute('aria-checked')) === 'true';
      if (cur !== desired) {
        await sw.click();
        await expect(swInput).toHaveAttribute(
          'aria-checked',
          String(desired),
          { timeout: 5_000 },
        );
      }
      await page.getByRole('button', { name: '保存安全配置' }).click();
      const successMsg = page.locator('.el-message', {
        hasText: '安全设置已保存',
      });
      // ElMessage 是堆叠式 toast（默认 3s 自动消失）：连续保存时上一条可能还在，
      // 用 .last() 锁定最新一条做可见性断言，避免 strict mode 命中多条。
      await expect(successMsg.last()).toBeVisible({ timeout: 5_000 });
      // 等本条 toast 从 DOM 移除后再返回，保证下一次保存时画面干净、不堆叠。
      await expect(successMsg).toHaveCount(0, { timeout: 6_000 });
    }

    /** 注册可用性探针：开启 → 200，关闭 → 403 */
    async function probeRegister(): Promise<number> {
      const name = `e2e_reg_probe_${Date.now()}`;
      const res = await page.request.post('/api/auth/register', {
        headers: { Authorization: `Bearer ${token}` },
        data: {
          username: name,
          email: `${name}@example.com`,
          password: 'TssTest#2026',
          security_question: '你出生的城市是？',
          security_answer: '上海',
        },
      });
      return res.status();
    }

    // 4) 开启「允许新用户注册」→ 后端实时变化 + 注册可用
    await setSwitch(true);
    expect(await getAllowRegistration(page, token)).toBe(true);
    expect(await probeRegister()).toBe(200);

    // 5) 关闭「允许新用户注册」→ 后端实时变化 + 注册被拒
    await setSwitch(false);
    expect(await getAllowRegistration(page, token)).toBe(false);
    expect(await probeRegister()).toBe(403);

    // 6) 恢复为「开启」态收尾 —— login 等套件依赖 /auth/register 可用，
    //    关闭态会令其 ensureUser 注册探针 403。保持开启，避免污染下游用例。
    await setSwitch(true);
    expect(await getAllowRegistration(page, token)).toBe(true);
    expect(await probeRegister()).toBe(200);
  });
});
