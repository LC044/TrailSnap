import fs from 'node:fs'
import type { APIRequestContext, Page } from '@playwright/test'

import { e2eEnv } from '../../../playwright/e2e-env'

/**
 * 测试账号登录态建立 —— 统一入口，供 album / home / smoke 等 spec 共用。
 *
 * - system / dev 套件：globalSetup 已登录并落盘 storageState，config 的 use.storageState
 *   会在每个 page 启动前注入 token。这里只在 storageState 确含真实 token 时直接返回 true。
 * - 兜底：globalSetup 登录失败（后端不可达 / e2e-admin 不存在，storageState 为空占位）时，
 *   逐测试尝试登录，通过 addInitScript 在 SPA 启动前注入 token；仍失败则 testInfo.skip。
 *
 * 为什么必须 addInitScript 而非「goto 后 evaluate 写 localStorage」：
 *   userStore 在 init 时只读一次 user_token（stores/user.ts:19，普通 ref 不再 re-read）。
 *   先 goto 再写入，store 已以 token=null 初始化；只能靠下一次 goto 整页刷新重建 store
 *   才读到 token —— 该"刷新重读"是隐式时序契约，fullyParallel 下偶发竞态，守卫读到 null
 *   就重定向 /login。addInitScript 在每次导航前注入，store 启动即读到，消除竞态。
 *
 * 返回 access_token（空串表示当前测试已被 skip，调用方应立即 `return`）。
 *
 * - system / dev 套件：globalSetup 已登录并落盘 storageState，config 的 use.storageState
 *   会在每个 page 启动前把 token 注入 localStorage。这里把该 token 读出来返回，供
 *   `request` fixture 直连后端时手动带 Bearer 头（storageState 只作用于浏览器
 *   localStorage，APIRequestContext 不会读取，故直连后端的调用必须自行带 Authorization）。
 * - 兜底：globalSetup 登录失败（后端不可达 / 账号不存在，storageState 为空占位）时，
 *   逐测试尝试登录，通过 addInitScript 在 SPA 启动前注入 token；仍失败则 testInfo.skip。
 *
 * 为什么必须 addInitScript 而非「goto 后 evaluate 写 localStorage」：
 *   userStore 在 init 时只读一次 user_token（stores/user.ts:19，普通 ref 不再 re-read）。
 *   先 goto 再写入，store 已以 token=null 初始化；只能靠下一次 goto 整页刷新重建 store
 *   才读到 token —— 该"刷新重读"是隐式时序契约，fullyParallel 下偶发竞态，守卫读到 null
 *   就重定向 /login。addInitScript 在每次导航前注入，store 启动即读到，消除竞态。
 *
 * 历史调用方 `if (!(await ensureAuthSession(...))) return` 仍兼容：空串为 falsy。
 *
 * @example
 *   test.beforeEach(async ({ page, request }, testInfo) => {
 *     const token = await ensureAuthSession(request, page, testInfo);
 *     if (!token) return;
 *   });
 */

/** 读取 storageState 落盘文件里的 user_token（globalSetup 登录成功的标志），无则返回 null */
function readStorageToken(statePath: string | undefined): string | null {
  if (!statePath) return null
  try {
    const state = JSON.parse(fs.readFileSync(statePath, 'utf8')) as {
      origins?: Array<{ localStorage?: Array<{ name: string; value: string }> }>
    }
    for (const origin of state.origins ?? []) {
      for (const kv of origin.localStorage ?? []) {
        if (kv.name === 'user_token' && kv.value) return kv.value
      }
    }
    return null
  } catch {
    return null
  }
}

/** 构造后端 Bearer 鉴权头，供 `request` fixture 直连后端时使用。 */
export function authHeaders(token: string): { Authorization: string } {
  return { Authorization: `Bearer ${token}` }
}

export async function ensureAuthSession(
  request: APIRequestContext,
  page: Page,
  testInfo: { skip: (condition: boolean, reason: string) => void },
): Promise<string> {
  // globalSetup 已登录：storageState 含真实 token，config 已自动注入到每个 page。
  // 读出来返回，供 `request` fixture 直连后端时手动带 Bearer 头。
  const stored = readStorageToken(e2eEnv.storageState)
  if (stored) return stored

  // 兜底：globalSetup 未拿到 token，逐测试登录
  try {
    const loginRes = await request.post(`${e2eEnv.apiBaseUrl}/auth/login`, {
      form: { username: e2eEnv.testUsername, password: e2eEnv.testPassword },
      timeout: 5_000,
    })
    if (!loginRes.ok()) {
      testInfo.skip(
        true,
        `Test user login failed (${loginRes.status()}) — register e2e-admin first or run system suite`,
      )
      return ''
    }
    const { access_token } = await loginRes.json()
    await page.context().addInitScript((token) => {
      localStorage.setItem('user_token', token)
    }, access_token)
    return access_token
  } catch {
    testInfo.skip(true, `Backend not reachable at ${e2eEnv.apiBaseUrl}`)
    return ''
  }
}
