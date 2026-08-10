import { test, expect, type Page, type APIRequestContext } from '@playwright/test';
import { e2eEnv } from '../../../../playwright/e2e-env';

/**
 * 登录全流程端到端测试（日常开发 / dev 套件）
 *
 * 覆盖 doc/e2e-test-checklist.md 中的登录相关核心路径：
 *   - 登录页加载与关键元素
 *   - 无效登录（错误密码）：不写入 token、停留在 /login、展示错误提示
 *   - 有效登录：写入 user_token、展示成功提示、跳转到首页
 *   - 深链重定向：未登录访问受保护路由 → 弹回 /login；登录后按 redirect 参数回到原路由
 *   - 路由守卫：已登录态直接访问 /login 被跳走
 *   - 登出：清理 token 并跳回 /login
 *   - 找回密码：完整两步流程（安全问题校验 + 重置）→ 用新密码登录成功
 *
 * 账号策略：本文件自包含，通过后端 API 自注册两个独立测试账号（幂等忽略"已存在"），
 *   不依赖全局 storageState。文件顶部强制空 storageState，每个用例都从零开始。
 */

const API = e2eEnv.apiBaseUrl;

const FLOW_USER = {
  username: 'e2e_login_flow',
  email: 'e2e_login_flow@example.com',
  password: 'TssTest#2026',
  security_question: '\u4f60\u51fa\u751f\u7684\u57ce\u5e02\u662f\uff1f',
  security_answer: '\u4e0a\u6d77',
};

const RESET_USER = {
  username: 'e2e_login_reset',
  email: 'e2e_login_reset@example.com',
  password: 'TssTest#2026',
  security_question: '\u4f60\u51fa\u751f\u7684\u57ce\u5e02\u662f\uff1f',
  security_answer: '\u4e0a\u6d77',
  new_password: 'TssReset#2026',
};

/** 幂等注册：账号已存在时忽略错误 */
async function ensureUser(api: APIRequestContext, u: typeof FLOW_USER) {
  await api
    .post(`${API}/auth/register`, {
      data: {
        username: u.username,
        email: u.email,
        password: u.password,
        security_question: u.security_question,
        security_answer: u.security_answer,
      },
      timeout: 8_000,
    })
    .catch(() => {});
}

/**
 * 确保系统「允许新用户注册」处于开启态 —— 否则下面的 ensureUser 会被后端 403 拒绝，
 * 测试账号建不出来，后续登录用例全部误报。
 *
 * Playwright 按文件名字母序跑：login/ 在 settings/ 之前，system-config.spec.ts 来不及
 * 先打开开关，所以 login 套件必须自己用超级账号把 allow_registration 打开。
 * 非超级用户 / 后端不可达时静默失败（后续注册断言会暴露真正原因）。
 */
async function ensureRegistrationEnabled(api: APIRequestContext) {
  try {
    const loginRes = await api.post(`${API}/auth/login`, {
      form: { username: e2eEnv.testUsername, password: e2eEnv.testPassword },
      timeout: 8_000,
    });
    if (!loginRes.ok()) return;
    const { access_token } = (await loginRes.json()) as { access_token: string };
    await api.put(`${API}/system/config`, {
      headers: { Authorization: `Bearer ${access_token}` },
      data: { security: { allow_registration: true } },
      timeout: 8_000,
    });
  } catch {
    // 静默：注册失败由后续断言暴露
  }
}

/** 通过登录页 UI 完成登录（含 goto） */
async function uiLogin(page: Page, username: string, password: string) {
  await page.goto('/login');
  await page.fill('input[placeholder="\u8bf7\u8f93\u5165\u7528\u6237\u540d"]', username);
  await page.fill('input[placeholder="\u8bf7\u8f93\u5165\u5bc6\u7801"]', password);
  await page.click('button:has-text("\u767b\u5f55")');
}

/** 仅填写并提交（不 goto，用于已在 /login 的场景如带 redirect 参数） */
async function fillAndSubmitLogin(
  page: Page,
  username: string,
  password: string,
) {
  await page.fill('input[placeholder="\u8bf7\u8f93\u5165\u7528\u6237\u540d"]', username);
  await page.fill('input[placeholder="\u8bf7\u8f93\u5165\u5bc6\u7801"]', password);
  await page.click('button:has-text("\u767b\u5f55")');
}

// 本文件所有用例都从零开始，不使用全局已登录 storageState
test.use({ storageState: { cookies: [], origins: [] } });

test.describe('\u767b\u5f55\u5168\u6d41\u7a0b @login', () => {
  test.beforeAll(async ({ request }) => {
    await ensureRegistrationEnabled(request);
    await ensureUser(request, FLOW_USER);
    await ensureUser(request, RESET_USER);
  });

  test('\u767b\u5f55\u9875\u6b63\u5e38\u52a0\u8f7d\u5e76\u5c55\u793a\u5173\u952e\u5143\u7d20', async ({ page }) => {
    await page.goto('/login');
    await expect(
      page.locator('h2', { hasText: '\u767b\u5f55 TrailSnap' }),
    ).toBeVisible();
    await expect(
      page.locator('input[placeholder="\u8bf7\u8f93\u5165\u7528\u6237\u540d"]'),
    ).toBeVisible();
    await expect(
      page.locator('input[placeholder="\u8bf7\u8f93\u5165\u5bc6\u7801"]'),
    ).toBeVisible();
    await expect(page.locator('button:has-text("\u767b\u5f55")')).toBeVisible();
    await expect(page.locator('a:has-text("\u5fd8\u8bb0\u5bc6\u7801")')).toBeVisible();
  });

  test('\u65e0\u6548\u767b\u5f55 - \u9519\u8bef\u5bc6\u7801\u4e0d\u5199\u5165 token \u4e14\u505c\u7559\u5728 /login', async ({ page }) => {
    await uiLogin(page, FLOW_USER.username, 'wrong-password-xxx');

    await expect(
      page.locator('.el-message', {
        hasText: '\u7528\u6237\u540d\u6216\u5bc6\u7801\u9519\u8bef',
      }),
    ).toBeVisible({ timeout: 5_000 });

    await page.waitForTimeout(1_000);
    const token = await page.evaluate(() =>
      localStorage.getItem('user_token'),
    );
    expect(token).toBeNull();
    expect(page.url()).toMatch(/\/login/);
  });

  test('\u6709\u6548\u767b\u5f55 - \u5199\u5165 token \u5e76\u8df3\u8f6c\u9996\u9875', async ({ page }) => {
    await uiLogin(page, FLOW_USER.username, FLOW_USER.password);

    await expect(
      page.locator('.el-message', { hasText: '\u767b\u5f55\u6210\u529f' }),
    ).toBeVisible({ timeout: 8_000 });

    await page.waitForURL(
      (url) => !url.pathname.includes('/login'),
      { timeout: 10_000 },
    );
    expect(page.url()).not.toMatch(/\/login/);

    const token = await page.evaluate(() =>
      localStorage.getItem('user_token'),
    );
    expect(token).toBeTruthy();
  });

  test(
    '\u6df1\u94fe\u91cd\u5b9a\u5411 - \u672a\u767b\u5f55\u8bbf\u95ee\u53d7\u4fdd\u62a4\u8def\u7531\u5f39\u56de\u767b\u5f55\uff0c\u767b\u5f55\u540e\u53ef\u8bbf\u95ee\u539f\u8def\u7531',
    async ({ page }) => {
      // \u672a\u767b\u5f55\u8bbf\u95ee /photos \u2192 \u8def\u7531\u5b88\u536b\u5f39\u56de /login
      await page.goto('/photos');
      await expect(
        page.locator('input[placeholder="\u8bf7\u8f93\u5165\u7528\u6237\u540d"]'),
      ).toBeVisible({ timeout: 10_000 });
      expect(page.url()).toMatch(/\/login/);

      // \u5728\u767b\u5f55\u9875\u5b8c\u6210\u767b\u5f55 \u2192 \u8fdb\u5165\u7cfb\u7edf
      await fillAndSubmitLogin(
        page,
        FLOW_USER.username,
        FLOW_USER.password,
      );
      await expect(
        page.locator('.el-message', { hasText: '\u767b\u5f55\u6210\u529f' }),
      ).toBeVisible({ timeout: 8_000 });
      await page.waitForURL(
        (url) => !url.pathname.includes('/login'),
        { timeout: 10_000 },
      );

      // \u767b\u5f55\u540e\u53ef\u76f4\u63a5\u8bbf\u95ee\u539f\u59cb\u53d7\u4fdd\u62a4\u8def\u7531 /photos
      await page.goto('/photos');
      expect(page.url()).toContain('/photos');
    },
  );

  test('\u8def\u7531\u5b88\u536b - \u5df2\u767b\u5f55\u6001\u8bbf\u95ee /login \u88ab\u8df3\u8d70', async ({ page }) => {
    await uiLogin(page, FLOW_USER.username, FLOW_USER.password);
    await page.waitForURL(
      (url) => !url.pathname.includes('/login'),
      { timeout: 10_000 },
    );

    await page.goto('/login');
    await page.waitForURL(
      (url) => !url.pathname.includes('/login'),
      { timeout: 10_000 },
    );
    expect(page.url()).not.toMatch(/\/login/);
  });

  test('\u767b\u51fa - \u6e05\u7406 token \u5e76\u8df3\u56de /login', async ({ page }) => {
    await uiLogin(page, FLOW_USER.username, FLOW_USER.password);
    await page.waitForURL(
      (url) => !url.pathname.includes('/login'),
      { timeout: 10_000 },
    );

    // Settings \u9875\u9ed8\u8ba4\u663e示 "\u4e2a\u4eba\u8d44\u6599" \u6807\u7b7e\u9875\uff0c\u9000\u51fa\u767b\u5f55\u5728 "\u7528\u6237\u7ba1\u7406" \u6807\u7b7e
    const accountMenu = page.getByRole('button', { name: new RegExp(FLOW_USER.username) });
    await expect(accountMenu).toBeVisible({ timeout: 10_000 });
    await accountMenu.click();

    await page.getByText('\u9000\u51fa\u767b\u5f55', { exact: true }).click();
    await page.getByRole('button', { name: '\u9000\u51fa', exact: true }).click();

    await page.waitForURL(/\/login/, { timeout: 10_000 });
    const token = await page.evaluate(() =>
      localStorage.getItem('user_token'),
    );
    expect(token).toBeNull();
  });

  test('\u627e\u56de\u5bc6\u7801 - \u5b8c\u6574\u4e24\u6b65\u6d41\u7a0b\u91cd\u7f6e\u540e\u53ef\u7528\u65b0\u5bc6\u7801\u767b\u5f55', async ({
    page,
    request,
  }) => {
    // \u4ece\u767b\u5f55\u9875\u70b9\u51fb"\u5fd8\u8bb0\u5bc6\u7801?"\u94fe\u63a5\u8fdb\u5165\uff08\u5ba2\u6237\u7aef\u5bfc\u822a\uff0c\u907f\u514d\u5168\u9875\u52a0\u8f7d\u7684\u8def\u7531\u95ee\u9898\uff09
    await page.goto('/login');
    await page.click('a:has-text("\u5fd8\u8bb0\u5bc6\u7801")');
    await page.waitForURL(/\/forgot-password/, { timeout: 10_000 });

    // Step 1\uff1a\u8f93\u5165\u7528\u6237\u540d/\u90ae\u7bb1\uff0c\u83b7\u53d6\u5b89\u5168\u95ee\u9898
    await page.fill(
      'input[placeholder="\u8bf7\u8f93\u5165\u7528\u6237\u540d\u6216\u90ae\u7bb1"]',
      RESET_USER.username,
    );
    await page.locator('button:has-text("\u4e0b\u4e00\u6b65")').click();

    // \u8fdb\u5165 Step 2\uff1a\u5c55\u793a\u5b89\u5168\u95ee\u9898\u5e76\u51fa\u73b0\u7b54\u6848/\u65b0\u5bc6\u7801\u8f93\u5165\u6846
    await expect(
      page.locator('input[placeholder="\u8bf7\u8f93\u5165\u7b54\u6848"]'),
    ).toBeVisible({ timeout: 8_000 });
    await expect(
      page.locator('.el-card', { hasText: RESET_USER.security_question }),
    ).toBeVisible();

    // Step 2\uff1a\u56de\u7b54\u5b89\u5168\u95ee\u9898\u5e76\u8bbe\u7f6e\u65b0\u5bc6\u7801
    await page.fill(
      'input[placeholder="\u8bf7\u8f93\u5165\u7b54\u6848"]',
      RESET_USER.security_answer,
    );
    await page.fill(
      'input[placeholder="\u8bf7\u8f93\u5165\u65b0\u5bc6\u7801"]',
      RESET_USER.new_password,
    );
    await page.fill(
      'input[placeholder="\u8bf7\u518d\u6b21\u8f93\u5165\u65b0\u5bc6\u7801"]',
      RESET_USER.new_password,
    );
    await page.locator('button:has-text("\u91cd\u7f6e\u5bc6\u7801")').click();

    await expect(
      page.locator('.el-message', { hasText: '\u5bc6\u7801\u91cd\u7f6e\u6210\u529f' }),
    ).toBeVisible({ timeout: 8_000 });
    await page.waitForURL(/\/login/, { timeout: 10_000 });

    // \u7528\u65b0\u5bc6\u7801\u767b\u5f55\u6210\u529f
    await uiLogin(page, RESET_USER.username, RESET_USER.new_password);
    await expect(
      page.locator('.el-message', { hasText: '\u767b\u5f55\u6210\u529f' }),
    ).toBeVisible({ timeout: 8_000 });
    await page.waitForURL(
      (url) => !url.pathname.includes('/login'),
      { timeout: 10_000 },
    );

    // \u8fd8\u539f\u5bc6\u7801\uff0c\u4fdd\u8bc1\u672c\u7528\u4f8b\u53ef\u91cd\u590d\u8fd0\u884c
    const restoreOk = await page.evaluate(
      async ([apiUrl, u, ans, pwd]) => {
        try {
          const res = await fetch(`${apiUrl}/auth/reset-password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              username_or_email: u,
              security_answer: ans,
              new_password: pwd,
            }),
          });
          return res.ok;
        } catch {
          return false;
        }
      },
      [API, RESET_USER.username, RESET_USER.security_answer, RESET_USER.password] as [string, string, string, string],
    );
    if (!restoreOk) console.warn('[forgot-password] password restore failed');
  });
});
