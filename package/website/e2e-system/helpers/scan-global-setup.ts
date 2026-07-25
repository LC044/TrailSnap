import fs from 'node:fs'
import { request as playwrightRequest, type FullConfig } from '@playwright/test'

import { adminUser, apiBaseUrl, ensureRuntimeDir } from './env'
import { preparePhotoFixturesForSuite } from '../../tests/e2e/helpers/photo-fixtures'
import { e2eEnv } from '../../playwright/e2e-env'

async function loginForAccessToken(
  request: Awaited<ReturnType<typeof playwrightRequest.newContext>>,
  username: string,
  password: string,
  failureLabel: string,
): Promise<string> {
  const loginResponse = await request.post('/auth/login', {
    form: {
      username,
      password,
    },
  })
  if (!loginResponse.ok()) {
    throw new Error(`${failureLabel}失败: ${loginResponse.status()} ${await loginResponse.text()}`)
  }

  const loginResult = await loginResponse.json() as { access_token: string }
  return loginResult.access_token
}

async function ensureAccessToken(): Promise<string> {
  const request = await playwrightRequest.newContext({
    baseURL: apiBaseUrl,
    extraHTTPHeaders: {
      Accept: 'application/json',
    },
  })

  try {
    const statusResponse = await request.get('/auth/status')
    if (!statusResponse.ok()) {
      throw new Error(`获取认证状态失败: ${statusResponse.status()} ${statusResponse.statusText()}`)
    }

    const status = await statusResponse.json() as { has_users: boolean }
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

      return await loginForAccessToken(
        request,
        adminUser.username,
        adminUser.password,
        '登录测试管理员',
      )
    }

    return await loginForAccessToken(
      request,
      e2eEnv.testUsername,
      e2eEnv.testPassword,
      `登录测试账号 ${e2eEnv.testUsername}`,
    )
  } finally {
    await request.dispose()
  }
}

export default async function globalSetup(_config: FullConfig) {
  ensureRuntimeDir()

  // scan 套件 config.use.storageState 指向 .playwright-system/storage-state.json，
  // 全新 CI checkout 下该文件不存在 → scan-prep spec 创建 context 时 ENOENT。
  // 写空占位（与 full-global-setup / dev-global-setup 一致），scan 阶段不依赖预存登录态。
  const statePath = e2eEnv.storageState
  if (statePath && !fs.existsSync(statePath)) {
    fs.writeFileSync(statePath, JSON.stringify({ cookies: [], origins: [] }), 'utf8')
  }

  if (!e2eEnv.enableFixtureScan) {
    return
  }

  const accessToken = await ensureAccessToken()
  const request = await playwrightRequest.newContext({
    baseURL: apiBaseUrl,
    extraHTTPHeaders: {
      Accept: 'application/json',
    },
  })

  try {
    await preparePhotoFixturesForSuite(request, accessToken, e2eEnv.suite, {
      onUnavailable: 'throw',
    })
  } finally {
    await request.dispose()
  }
}
