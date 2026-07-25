import fs from 'node:fs'

import { chromium, request as playwrightRequest, type APIResponse, type FullConfig } from '@playwright/test'

import {
  adminUser,
  apiBaseUrl,
  authStatePath,
  bootstrapStatePath,
  ensureRuntimeDir,
  webBaseUrl,
} from './env'
import { bucketForSuite, preparePhotoFixturesForSuite } from '../../tests/e2e/helpers/photo-fixtures'
import { e2eEnv } from '../../playwright/e2e-env'

async function registerAdminIfNeeded() {
  const request = await playwrightRequest.newContext({
    baseURL: apiBaseUrl,
    extraHTTPHeaders: {
      Accept: 'application/json',
    },
  })

  try {
    // server 刚通过 /health-check 后仍可能有极短的接收窗口；带退避重试，避免瞬时
    // socket hang up 直接让整个 globalSetup 失败。
    let statusResponse: APIResponse | undefined
    for (let attempt = 1; ; attempt++) {
      try {
        statusResponse = await request.get('/auth/status')
        if (statusResponse.ok()) break
      } catch {
        // socket hang up / 连接被 reset → 重试
      }
      if (attempt >= 15) {
        throw new Error('获取认证状态失败：server 在 30s 内未稳定响应 /auth/status')
      }
      await new Promise((r) => setTimeout(r, 2000))
    }

    const status = await statusResponse!.json() as { has_users: boolean }
    if (!status.has_users) {
      const registerResponse = await request.post('/auth/register', {
        data: {
          username: adminUser.username,
          email: adminUser.email,
          password: adminUser.password,
          security_question: adminUser.securityQuestion,
          security_answer: adminUser.securityAnswer,
        },
      })

      if (!registerResponse.ok()) {
        throw new Error(`注册测试管理员失败: ${registerResponse.status()} ${await registerResponse.text()}`)
      }
    }

    const loginResponse = await request.post('/auth/login', {
      form: {
        username: adminUser.username,
        password: adminUser.password,
      },
    })

    if (!loginResponse.ok()) {
      throw new Error(`登录测试管理员失败: ${loginResponse.status()} ${await loginResponse.text()}`)
    }

    const loginResult = await loginResponse.json() as { access_token: string }
    const accessToken = loginResult.access_token

    const fixtureBucket = bucketForSuite(e2eEnv.suite)
    if (fixtureBucket) {
      await preparePhotoFixturesForSuite(request, accessToken, e2eEnv.suite, {
        onUnavailable: 'throw',
      })
    }

    return accessToken
  } finally {
    await request.dispose()
  }
}

async function saveFrontendSession(accessToken: string) {
  const browser = await chromium.launch()
  const context = await browser.newContext()
  const page = await context.newPage()

  try {
    await page.goto(`${webBaseUrl}/login`, { waitUntil: 'networkidle' })
    await page.evaluate(
      ({ token, username }) => {
        localStorage.setItem('user_token', token)
        localStorage.setItem('remember_username', username)
      },
      { token: accessToken, username: adminUser.username },
    )
    await context.storageState({ path: authStatePath })
  } finally {
    await context.close()
    await browser.close()
  }
}

export default async function globalSetup(_config: FullConfig) {
  ensureRuntimeDir()

  const accessToken = await registerAdminIfNeeded()
  await saveFrontendSession(accessToken)
  const fixtureBucket = bucketForSuite(e2eEnv.suite)

  fs.writeFileSync(
    bootstrapStatePath,
    JSON.stringify(
      {
        accessToken,
        username: adminUser.username,
        email: adminUser.email,
        photoDirectory: fixtureBucket ? `${e2eEnv.photoDirectory}/${fixtureBucket}` : e2eEnv.photoDirectory,
      },
      null,
      2,
    ),
    'utf8',
  )
}
