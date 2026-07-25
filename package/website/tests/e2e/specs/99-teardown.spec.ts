import { test, expect } from '@playwright/test';
import { e2eEnv } from '../../../playwright/e2e-env';
import { cleanupPreparedPhotoFixtures } from '../helpers/photo-fixtures';
import fs from 'node:fs';

// 与 00-setup 对齐：用 testUsername/testPassword（本地 dev 环境即实际存在的账号）。
const ADMIN = {
  username: e2eEnv.testUsername,
  password: e2eEnv.testPassword,
};

test.describe('Test Environment Teardown @teardown', () => {
  // 与 00-setup 对齐：teardown 自带登录（Bearer token），不依赖预存 storageState；
  // 且 setup 若失败，storage-state.json 可能不存在，置空避免 teardown 再因读不到文件而报错。
  test.use({ storageState: undefined });

  test('Clean up test data and delete account', async ({ request }) => {
    // TS_TEST_KEEP_SERVICES=true 时跳过清理，保留服务与数据以便查看测试完成后的现场状态。
    test.skip(
      e2eEnv.keepServices,
      'TS_TEST_KEEP_SERVICES=true，保留服务与数据以便查看最终状态，跳过清理',
    );

    // 1. Get token
    // request fixture 的 baseURL 是前端地址，必须带 /api 前缀走 Vite 代理到后端。
    const loginResponse = await request.post('/api/auth/login', {
      form: {
        username: ADMIN.username,
        password: ADMIN.password,
      },
    });

    if (!loginResponse.ok()) {
      console.log('User already deleted or not found, skipping teardown.');
      return;
    }

    const { access_token } = await loginResponse.json();

    // 2. Delete test data (directories)
    await cleanupPreparedPhotoFixtures(request, access_token);

    // 3. Delete user account
    // ⚠️ 注意：当 testUsername 指向真实账号（如本地 dev 的 zhousk）时，这一步会删掉该账号。
    //    仅在用一次性测试账号（CI 的 e2e-admin）时才安全；真实账号环境请保持
    //    TS_TEST_KEEP_SERVICES=true，或把这段删除逻辑去掉。
    const meResponse = await request.get('/api/users/me', {
      headers: { Authorization: `Bearer ${access_token}` },
    });
    if (meResponse.ok()) {
      const me = await meResponse.json();
      const deleteUserResponse = await request.delete(`/api/users/${me.id}`, {
        headers: { Authorization: `Bearer ${access_token}` },
      });
      expect(deleteUserResponse.ok()).toBeTruthy();
    }

    // Clean up storage state
    if (e2eEnv.storageState && fs.existsSync(e2eEnv.storageState)) {
      fs.unlinkSync(e2eEnv.storageState);
    }
  });
});
