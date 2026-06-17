import fs from 'node:fs'

import { chromium, request as playwrightRequest, type FullConfig } from '@playwright/test'

import {
  adminUser,
  apiBaseUrl,
  authStatePath,
  bootstrapStatePath,
  ensureRuntimeDir,
  photoDirectory,
  webBaseUrl,
} from './env'
import { waitForTasksToSettle } from './task-poller'

async function registerAdminIfNeeded() {
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

    const directoriesResponse = await request.get('/settings/directories', {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    })

    if (!directoriesResponse.ok()) {
      throw new Error(`获取目录配置失败: ${directoriesResponse.status()} ${await directoriesResponse.text()}`)
    }

    const directories = await directoriesResponse.json() as { external?: string[] }
    const externalDirectories = directories.external || []

    if (!externalDirectories.includes(photoDirectory)) {
      const addDirectoryResponse = await request.post('/settings/directories', {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
        data: {
          path: photoDirectory,
        },
      })

      if (!addDirectoryResponse.ok()) {
        throw new Error(`添加测试目录失败: ${addDirectoryResponse.status()} ${await addDirectoryResponse.text()}`)
      }
    }

    await waitForTasksToSettle(request, accessToken)

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

  fs.writeFileSync(
    bootstrapStatePath,
    JSON.stringify(
      {
        accessToken,
        username: adminUser.username,
        email: adminUser.email,
        photoDirectory,
      },
      null,
      2,
    ),
    'utf8',
  )
}
