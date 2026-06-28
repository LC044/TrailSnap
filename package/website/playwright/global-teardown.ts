import fs from 'node:fs'

import { request as playwrightRequest, type FullConfig } from '@playwright/test'

import { e2eEnv } from './e2e-env'
import { cleanupPreparedPhotoFixtures } from '../tests/e2e/helpers/photo-fixtures'

function readStorageToken(statePath: string | undefined): string | null {
  if (!statePath || !fs.existsSync(statePath)) {
    return null
  }

  try {
    const state = JSON.parse(fs.readFileSync(statePath, 'utf8')) as {
      origins?: Array<{ localStorage?: Array<{ name: string; value: string }> }>
    }

    for (const origin of state.origins ?? []) {
      for (const item of origin.localStorage ?? []) {
        if (item.name === 'user_token' && item.value) {
          return item.value
        }
      }
    }
  } catch {
    return null
  }

  return null
}

async function resolveCleanupToken(): Promise<string | null> {
  const storedToken = readStorageToken(e2eEnv.storageState)
  if (storedToken) {
    return storedToken
  }

  const request = await playwrightRequest.newContext({
    baseURL: e2eEnv.apiBaseUrl,
    extraHTTPHeaders: {
      Accept: 'application/json',
    },
  })

  try {
    const loginResponse = await request.post('/auth/login', {
      form: {
        username: e2eEnv.testUsername,
        password: e2eEnv.testPassword,
      },
      timeout: 5_000,
    }).catch(() => null)

    if (!loginResponse?.ok()) {
      return null
    }

    const body = await loginResponse.json() as { access_token: string }
    return body.access_token
  } finally {
    await request.dispose()
  }
}

export default async function globalTeardown(_config: FullConfig) {
  if (!e2eEnv.enableFixtureScan) {
    return
  }

  const token = await resolveCleanupToken()
  if (!token) {
    return
  }

  const request = await playwrightRequest.newContext({
    baseURL: e2eEnv.apiBaseUrl,
    extraHTTPHeaders: {
      Accept: 'application/json',
    },
  })

  try {
    await cleanupPreparedPhotoFixtures(request, token)
  } finally {
    await request.dispose()
  }
}
