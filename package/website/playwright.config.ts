/**
 * TrailSnap Playwright E2E 配置（单一入口）
 *
 * 通过 TS_E2E_SUITE 环境变量切换测试套件：
 *   dev    - 默认。pnpm test:e2e 走 vite dev server (5176)，跑 tests/e2e 下所有 spec
 *   p0     - P0 核心路径（@p0，PR 阶段），需 system 环境（pnpm test:e2e:up）
 *   p1     - P1 核心业务功能（'P1 - '，Nightly），需 system 环境
 *   smoke  - 页面打开 + 系统级冒烟（@smoke，可 Nightly / Release）
 *   all    - p0 → p1 → smoke 串行
 *
 * 套件对应的 testDir / testMatch / 后端前端地址 / 标签 grep 全部集中在
 * ./playwright/e2e-env.ts 与 ./playwright/run-e2e.mjs。
 *
 * 所有环境变量默认值 / 套件映射集中在 ./playwright/e2e-env.ts
 */

import { defineConfig, devices } from '@playwright/test'

import { e2eEnv } from './playwright/e2e-env'

process.env.TS_E2E_PREP_RUN_ID ??= `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`

const suite = e2eEnv.suite
const isSystemSuite = suite !== 'dev'

export default defineConfig({
  testDir: e2eEnv.testDir,
  testMatch: e2eEnv.testMatch,

  // dev 套件下用本地 vite dev server 自动拉起；system 套件用 docker compose
  // 见 playwright/e2e-up.mjs（pnpm test:e2e:up）/ package.json scripts
  fullyParallel: suite !== 'smoke',
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  // CI: smoke=1, others=2. 本地非 CI 默认 4 worker（可由 TS_E2E_WORKERS 覆盖），
  // 避免 Playwright auto-detect（≈CPU 数，本机常达 8~16）压满后端/AI 时出现 load-induced flake。
  workers: process.env.CI
    ? (suite === 'smoke' ? 1 : 2)
    : process.env.TS_E2E_WORKERS
    ? Number(process.env.TS_E2E_WORKERS)
    : 4,

  globalSetup: e2eEnv.globalSetup,
  globalTeardown: e2eEnv.globalTeardown,

  reporter: [
    ['list'],
    ['html', { outputFolder: e2eEnv.reportDir }],
  ],
  outputDir: e2eEnv.outputDir,

  use: {
    baseURL: e2eEnv.webBaseUrl,
    storageState: e2eEnv.storageState,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  // dev 套件自动拉起 vite dev server；system 套件依赖 docker compose（pnpm test:e2e:up 拉起）
  webServer: isSystemSuite
    ? undefined
    : {
        command: 'pnpm dev',
        url: 'http://localhost:5176',
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
