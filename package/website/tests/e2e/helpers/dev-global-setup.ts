import fs from 'node:fs'
import path from 'node:path'

import { chromium, request as playwrightRequest, type FullConfig } from '@playwright/test'

import { e2eEnv } from '../../../playwright/e2e-env'
import { preparePhotoFixturesForSuite } from './photo-fixtures'

/**
 * Dev 套件 globalSetup —— 登录一次，落盘 storageState，供所有测试复用。
 *
 * 目的：消除「每个测试各自 /auth/login」造成的 N 次并发登录（fullyParallel 下
 * 时序竞态 + 后端压力）。与 system 套件（e2e-system/helpers/bootstrap.ts）同思路，
 * 但更轻：不注册账号、不加照片目录、不等任务，只在能登录时落盘已登录态。
 *
 * 登录失败（后端不可达 / e2e-admin 不存在）时不抛错——写一个空 storageState 占位，
 * 让 config 的 use.storageState 不至于因文件缺失而报错；此时 ensureAuthSession 会
 * 检测到 storageState 里没有 token，逐测试回退到登录兜底（仍失败则 skip）。
 */

const storageDir = path.resolve(process.cwd(), '.playwright-dev')
export const storageStatePath = path.join(storageDir, 'storage-state.json')

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

function writeEmptyState() {
  fs.mkdirSync(storageDir, { recursive: true })
  fs.writeFileSync(storageStatePath, JSON.stringify({ cookies: [], origins: [] }), 'utf8')
}

export default async function globalSetup(_config: FullConfig) {
  fs.mkdirSync(storageDir, { recursive: true })

  const req = await playwrightRequest.newContext({
    baseURL: e2eEnv.apiBaseUrl,
    extraHTTPHeaders: { Accept: 'application/json' },
  })

  try {
    let loginRes: Awaited<ReturnType<typeof req.post>> | null = null
    for (let attempt = 1; attempt <= 10; attempt += 1) {
      loginRes = await req
        .post('/auth/login', {
          form: { username: e2eEnv.testUsername, password: e2eEnv.testPassword },
          timeout: 5_000,
        })
        .catch(() => null)

      if (loginRes?.ok()) {
        break
      }

      await sleep(3_000)
    }

    if (!loginRes || !loginRes.ok()) {
      console.warn(
        `[dev-global-setup] login as ${e2eEnv.testUsername} failed (${loginRes?.status() ?? 'unreachable'}) — ` +
          `tests will skip. Register the user or point TS_TEST_USERNAME/TS_TEST_PASSWORD at an existing account.`,
      )
      writeEmptyState()
      return
    }

    const { access_token } = (await loginRes.json()) as { access_token: string }

    if (e2eEnv.enableFixtureScan) {
      await preparePhotoFixturesForSuite(req, access_token, e2eEnv.suite, {
        onUnavailable: 'throw',
      })
    }

    const browser = await chromium.launch()
    const context = await browser.newContext()
    const page = await context.newPage()
    try {
      await page.goto(`${e2eEnv.webBaseUrl}/login`, { waitUntil: 'domcontentloaded' })
      await page.evaluate(
        (token) => {
          localStorage.setItem('user_token', token)
        },
        access_token,
      )
      await context.storageState({ path: storageStatePath })
    } finally {
      await context.close()
      await browser.close()
    }
  } finally {
    await req.dispose()
  }
}
