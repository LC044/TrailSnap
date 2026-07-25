import fs from 'node:fs'
import type { FullConfig } from '@playwright/test'

import { e2eEnv } from '../../playwright/e2e-env'
import { ensureRuntimeDir } from './env'

/**
 * full 套件 globalSetup —— 仅保证 storageState 占位文件存在。
 *
 * full/light 套件不像 p0/p1/smoke 那样跑登录型 globalSetup（bootstrap.ts），
 * 也不像 dev 那样跑 dev-global-setup；真实登录 + 照片扫描交给 00-setup.spec.ts
 * （@setup）在测试阶段完成。但 playwright.config 的 use.storageState 指向
 * .playwright-system/storage-state.json，Playwright 在创建 page/request context
 * 时会立刻读这个文件——全新环境（CI checkout）下文件不存在 → ENOENT，00-setup
 * 还没进 test body 就直接失败，连带 light 阶段全部连锁失败。
 *
 * 这里在测试开始前写一个空占位 { cookies: [], origins: [] }（与 dev-global-setup
 * 一致），让 context 能正常创建；00-setup.spec.ts 登录后会覆写为真实登录态，
 * 供后续 light 阶段复用。本地能跑通是因为上一轮 p0/smoke/dev 残留了该文件。
 *
 * test.use({ storageState: undefined }) 在 Playwright 1.60 下被当 no-op
 * （undefined 不覆盖 config），不能用来绕过，故采用占位文件方案。
 */
export default async function globalSetup(_config: FullConfig) {
  ensureRuntimeDir()
  const statePath = e2eEnv.storageState
  if (statePath && !fs.existsSync(statePath)) {
    fs.writeFileSync(statePath, JSON.stringify({ cookies: [], origins: [] }), 'utf8')
  }
}
