import { defineConfig, devices } from '@playwright/test'

// P0 smoke configuration:
// - reuses the system bootstrap (registers admin + saves storage state) so login tests can pass
// - uses TS_WEB_BASE_URL/TS_API_BASE_URL injected by e2e-run.ps1 instead of a local dev server
// - runs only the P0 spec files
// - does NOT set storageState: P0 specs handle token state per test
//   (some need logged-in state via API, some need logged-out state for redirect tests)
export default defineConfig({
  testDir: './tests/e2e',
  testMatch: /specs\/(auth|smoke|tasks|redirect)\.spec\.ts$/,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  globalSetup: './e2e-system/helpers/bootstrap.ts',
  reporter: [['list'], ['html', { outputFolder: '.playwright-p0/report' }]],
  outputDir: '.playwright-p0/results',
  use: {
    baseURL: process.env.TS_WEB_BASE_URL || 'http://localhost:8082',
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
