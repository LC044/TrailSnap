import { test, expect } from '@playwright/test';
import { e2eEnv } from '../../../playwright/e2e-env';
import { preparePhotoFixturesForSuite } from '../helpers/photo-fixtures';
import fs from 'node:fs';
import path from 'node:path';

// 与 dev-global-setup 对齐：用 testUsername/testPassword（本地 dev 环境即实际存在的
// 超级用户账号），而不是 adminUser（默认 e2e-admin，既有库里通常不存在 → 登录 401）。
const ADMIN = {
  username: e2eEnv.testUsername,
  password: e2eEnv.testPassword,
  email: `${e2eEnv.testUsername}@example.com`,
  securityQuestion: e2eEnv.adminUser.securityQuestion,
  securityAnswer: e2eEnv.adminUser.securityAnswer,
};

test.describe('Test Environment Setup @setup', () => {
  // full/light 套件 globalSetup=undefined，storage-state.json 在本 spec 运行前尚不存在
  // （本 spec 才是创建者）。若沿用 config 的 use.storageState，Playwright 创建 context
  // 时会去读这个不存在的文件 → "Error reading storage state" 直接失败。本 spec 自带
  // 注册/登录逻辑，不依赖预存登录态，故显式置空。
  test.use({ storageState: undefined });

  test('Create test account and scan folder', async ({ page, request }) => {
    // 1. Check if user exists, if not create admin user
    // request fixture 的 baseURL 是前端地址，必须带 /api 前缀走 Vite 代理到后端，
    // 否则 Vite 回吐 index.html → res.json() 解析失败。
    const statusResponse = await request.get('/api/auth/status');
    expect(statusResponse.ok()).toBeTruthy();
    const status = await statusResponse.json();

    if (!status.has_users) {
      const registerResponse = await request.post('/api/auth/register', {
        data: {
          username: ADMIN.username,
          email: ADMIN.email,
          password: ADMIN.password,
          security_question: ADMIN.securityQuestion,
          security_answer: ADMIN.securityAnswer,
        },
      });
      expect(registerResponse.ok()).toBeTruthy();
    }

    // 2. Login to get token
    const loginResponse = await request.post('/api/auth/login', {
      form: {
        username: ADMIN.username,
        password: ADMIN.password,
      },
    });
    expect(loginResponse.ok()).toBeTruthy();
    const { access_token } = await loginResponse.json();

    // 3. Scan folder (import test data)
    // preparePhotoFixturesForSuite already handles the scanning and waiting for tasks
    test.setTimeout(180_000); // Allow up to 3 minutes for scanning tasks to complete
    
    // Set up a listener or polling mechanism if you want progress output
    // Note: The preparePhotoFixturesForSuite already does quiet polling internally via waitForTasksToSettle
    const fixtureReady = await preparePhotoFixturesForSuite(request, access_token, e2eEnv.suite, {
      onUnavailable: 'throw',
    });
    expect(fixtureReady).toBeTruthy();

    // 4. Save frontend session (storageState)
    // 不用 networkidle：本 spec 继承 globalSetup 的已登录态，/login 会被守卫重定向到 /，
    // 首页有 SSE/轮询等持续网络活动，networkidle 永不满足 → 超时。SPA 用 domcontentloaded
    // 即可；evaluate 写 localStorage 是 origin 级别，与最终落在哪个路由无关。
    await page.goto('/login', { waitUntil: 'domcontentloaded' });
    await page.evaluate(
      ({ token, username }) => {
        localStorage.setItem('user_token', token);
        localStorage.setItem('remember_username', username);
      },
      { token: access_token, username: ADMIN.username }
    );
    
    // Ensure directory exists
    const statePath = e2eEnv.storageState;
    if (statePath) {
      fs.mkdirSync(path.dirname(statePath), { recursive: true });
      await page.context().storageState({ path: statePath });
    }
  });
});
