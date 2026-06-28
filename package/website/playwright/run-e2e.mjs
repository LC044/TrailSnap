/**
 * Cross-platform E2E test runner.
 *
 * Usage:  node playwright/run-e2e.mjs <suite>
 * Suites: dev | p0 | smoke | all
 *
 * Sets TS_E2E_SUITE and delegates to `playwright test`.
 * For the 'all' suite, runs p0 then smoke serially (same as e2e-run.ps1).
 */

import { execSync } from 'node:child_process'

const VALID_SUITES = ['dev', 'p0', 'smoke', 'all']
const suite = process.argv[2] ?? 'dev'

if (!VALID_SUITES.includes(suite)) {
  console.error(`Unknown suite: "${suite}". Valid: ${VALID_SUITES.join(', ')}`)
  process.exit(1)
}

function runPlaywright(suiteName) {
  const env = { ...process.env, TS_E2E_SUITE: suiteName }
  // p0 套件跑关键路径用例。当前功能用例仍挂 @smoke（逐条重打标签未完成），暂 grep @smoke；
  // 待功能用例改挂 @p0 后切回 --grep @p0。
  const args = suiteName === 'p0' ? ['test', '--grep', '@smoke'] : ['test']
  execSync(['pnpm', 'exec', 'playwright', ...args].join(' '), { stdio: 'inherit', env })
}

if (suite === 'all') {
  console.log('[1/2] Running P0 suite...')
  runPlaywright('p0')
  console.log('[2/2] Running smoke suite...')
  runPlaywright('smoke')
} else {
  runPlaywright(suite)
}
