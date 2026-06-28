import { test, expect } from '@playwright/test';
import { e2eEnv } from '../../../playwright/e2e-env';
import { cleanupPreparedPhotoFixtures } from '../helpers/photo-fixtures';
import fs from 'node:fs';

test.describe('Test Environment Teardown @teardown', () => {
  test('Clean up test data and delete account', async ({ request }) => {
    // 1. Get token
    const loginResponse = await request.post('/auth/login', {
      form: {
        username: e2eEnv.adminUser.username,
        password: e2eEnv.adminUser.password,
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
    const meResponse = await request.get('/users/me', {
      headers: { Authorization: `Bearer ${access_token}` }
    });
    if (meResponse.ok()) {
      const me = await meResponse.json();
      const deleteUserResponse = await request.delete(`/users/${me.id}`, {
        headers: { Authorization: `Bearer ${access_token}` }
      });
      expect(deleteUserResponse.ok()).toBeTruthy();
    }
    
    // Clean up storage state
    if (e2eEnv.storageState && fs.existsSync(e2eEnv.storageState)) {
      fs.unlinkSync(e2eEnv.storageState);
    }
  });
});
