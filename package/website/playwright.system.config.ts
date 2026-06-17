import { defineConfig, devices } from '@playwright/test'

import { authStatePath } from './e2e-system/helpers/env'

export default defineConfig({
  testDir: './e2e-system',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  globalSetup: './e2e-system/helpers/bootstrap.ts',
  reporter: [['html', { outputFolder: '.playwright-system/report' }], ['list']],
  outputDir: '.playwright-system/results',
  use: {
    baseURL: process.env.TS_WEB_BASE_URL || 'http://localhost:8082',
    storageState: authStatePath,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
