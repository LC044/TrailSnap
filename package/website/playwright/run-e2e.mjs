/**
 * Cross-platform E2E test runner.
 *
 * Usage:  node playwright/run-e2e.mjs <suite>
 * Suites: dev | p0 | p1 | smoke | scan | all
 *
 * 设置 TS_E2E_SUITE 后委托给 `playwright test`，并按套件加 --grep
 * 过滤具体要跑的 tag：
 *   p0    : --grep @p0         （核心路径功能用例，PR 阶段必跑）
 *   p1    : --grep "P1 - "     （P1 核心业务功能，Nightly 跑）
 *   smoke : --grep @smoke      （页面打开 + 系统级冒烟，可 Nightly 或 Release）
 *   all   : p0 → p1 → smoke 串行
 *
 * 标签约定见 tests/e2e/specs/smoke.spec.ts 头部注释：
 *   - @smoke  页面能否打开 / 系统级冒烟
 *   - @p0     核心路径功能是否可用
 *   - P1 - *  业务功能（非 smoke、非 p0）
 */

import { execSync } from 'node:child_process'
import { startServices, stopServices } from './service-manager.mjs'

const VALID_SUITES = ['dev', 'p0', 'p1', 'smoke', 'scan', 'all', 'light', 'full']
const suite = process.argv[2] ?? 'dev'

if (!VALID_SUITES.includes(suite)) {
  console.error(`Unknown suite: "${suite}". Valid: ${VALID_SUITES.join(', ')}`)
  process.exit(1)
}

/** @type {Record<string, { name: string, grep?: string, grepInvert?: string }} */
const SUITE_CONFIG = {
  dev: { name: 'dev' },
  p0: { name: 'p0', grep: '@p0' },
  p1: { name: 'p1', grep: 'P1 - ' },
  smoke: { name: 'smoke', grep: '@smoke' },
  scan: { name: 'scan' },
  light: { name: 'light', grepInvert: '@setup|@teardown' },
  full: { name: 'full' },
  full_setup: { name: 'full', grep: '@setup' },
  full_teardown: { name: 'full', grep: '@teardown' },
}

const runId = process.env.TS_E2E_PREP_RUN_ID ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`

function envFlag(value, defaultValue = false) {
  if (value == null || value.trim() === '') return defaultValue
  return !['0', 'false', 'off', 'no'].includes(value.trim().toLowerCase())
}

function shouldRunFixtureScan() {
  return envFlag(process.env.TS_E2E_ENABLE_FIXTURE_SCAN, false)
}

function runPlaywright(suiteName) {
  const env = {
    ...process.env,
    TS_E2E_SUITE: suiteName,
    TS_E2E_PREP_RUN_ID: runId,
  }
  const cfg = SUITE_CONFIG[suiteName]
  const args = ['test']
  if (cfg && cfg.grep) {
    args.push('--grep', cfg.grep)
  }
  if (cfg && cfg.grepInvert) {
    args.push('--grep-invert', cfg.grepInvert)
  }
  // execSync 走 shell，含空格 / | / < > & 的参数必须加引号，否则
  // `--grep-invert @setup|@teardown` 的 | 会被当管道符、`--grep P1 - ` 会被拆成多参数
  const quoted = args.map((a) => (/[\s|<>&]/.test(a) ? `"${a}"` : a))
  execSync(['pnpm', 'exec', 'playwright', ...quoted].join(' '), { stdio: 'inherit', env })
}

if (suite !== 'scan' && shouldRunFixtureScan()) {
  console.log('[scan] TS_E2E_ENABLE_FIXTURE_SCAN=on, running fixture scan prep...')
  runPlaywright('scan')
}

if (suite === 'all') {
  console.log('[1/3] Running P0 suite (--grep @p0)...')
  runPlaywright('p0')
  console.log('[2/3] Running P1 suite (--grep "P1 - ")...')
  runPlaywright('p1')
  console.log('[3/3] Running smoke suite (--grep @smoke)...')
  runPlaywright('smoke')
} else if (suite === 'full') {
  ;(async () => {
    console.log('[Full Test] 1. Checking and starting services...')
    const startInfo = await startServices()
    try {
      console.log('[Full Test] 2. Running setup tests...')
      runPlaywright('full_setup')
      
      console.log('[Full Test] 3. Running normal tests...')
      runPlaywright('light')
      
      console.log('[Full Test] 4. Running teardown tests...')
      runPlaywright('full_teardown')
    } finally {
      console.log('[Full Test] 5. Stopping services...')
      stopServices(startInfo)
    }
  })()
} else {
  runPlaywright(suite)
}
