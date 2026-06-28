import { test, expect } from '@playwright/test';
import { e2eEnv } from '../../../playwright/e2e-env';
import { preparePhotoFixturesForSuite } from '../helpers/photo-fixtures';
import fs from 'node:fs';

test.describe('Test Environment Setup @setup', () => {
  test('Create test account and scan folder', async ({ page, request }) => {
    // 1. Check if user exists, if not create admin user
    const statusResponse = await request.get('/auth/status');
    expect(statusResponse.ok()).toBeTruthy();
    const status = await statusResponse.json();

    if (!status.has_users) {
      const registerResponse = await request.post('/auth/register', {
        data: {
          username: e2eEnv.adminUser.username,
          email: e2eEnv.adminUser.email,
          password: e2eEnv.adminUser.password,
          security_question: e2eEnv.adminUser.securityQuestion,
          security_answer: e2eEnv.adminUser.securityAnswer,
        },
      });
      expect(registerResponse.ok()).toBeTruthy();
    }

    // 2. Login to get token
    const loginResponse = await request.post('/auth/login', {
      form: {
        username: e2eEnv.adminUser.username,
        password: e2eEnv.adminUser.password,
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
    await page.goto('/login', { waitUntil: 'networkidle' });
    await page.evaluate(
      ({ token, username }) => {
        localStorage.setItem('user_token', token);
        localStorage.setItem('remember_username', username);
      },
      { token: access_token, username: e2eEnv.adminUser.username }
    );
    
    // Ensure directory exists
    const statePath = e2eEnv.storageState;
    if (statePath) {
      fs.mkdirSync(require('path').dirname(statePath), { recursive: true });
      await page.context().storageState({ path: statePath });
    }
  });
});
