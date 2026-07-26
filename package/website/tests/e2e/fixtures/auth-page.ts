import { test as base, expect } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'

import { e2eEnv } from '../../../playwright/e2e-env'

/**
 * 两个「显式登录态」page fixture，替代散落在各 spec 里的 `browser.newContext()` 手写覆盖。
 *
 * 背景（这几个用例在 CI docker 下集体被踢到 /login 的根因）：
 *  - config.use.storageState 注入的全局共享 token 会在并发用例中途失效（被别的用例登出 /
 *    改密 / JWT 过期）。骑共享 token 的用例一旦启动期某个接口 401，request.ts 的 401
 *    拦截器就 resetState() → router.push('/login')。
 *  - 各 spec 此前用 `base.extend({ page: async ({ browser }, use) => browser.newContext() })`
 *    想起「干净上下文」绕开共享 token。但 Playwright 1.60 下 use.storageState 会泄漏进
 *    手动 newContext()（作者已在原 spec 注释里标注 test.use({storageState}) 无法可靠覆盖），
 *    于是「干净上下文」并不干净，照样骑着失效 token → 同样 401 → /login。
 *
 * 这里的修法不依赖 Playwright 的 storageState 语义：
 *  - cleanPage：newContext 后 addInitScript(localStorage.clear)，在 SPA 任何脚本执行前
 *    清空 localStorage，保证 userStore.token 启动即读到 null —— 与 storageState 是否泄漏无关。
 *  - authedPage：worker 级 freshToken 现登录拿一个保证有效的 token，再 addInitScript 注入。
 *    不共享、不被别的用例失效。
 *
 * 用法：
 *   import { test, expect } from '../../fixtures/auth-page'   // 取 cleanPage/authedPage
 *   test('...', async ({ cleanPage: page }) => { ... })
 *   test('...', async ({ authedPage: page }) => { ... })
 *
 * 注：相对 page.goto('/x') 依赖 baseURL，两个 fixture 都显式带上 e2eEnv.webBaseUrl，
 *     避免手动 newContext() 丢失 baseURL 导致 goto 抛 "baseURL is not provided"。
 */

/** Worker 级：每个 worker 现登录一次，拿到保证有效的 access_token。 */
const freshToken = base.extend<{ freshToken: string }>({
  freshToken: [
    async ({ playwright }, use) => {
      const ctx: APIRequestContext = await playwright.request.newContext({
        baseURL: e2eEnv.apiBaseUrl,
      })
      try {
        const res = await ctx.post('/auth/login', {
          form: { username: e2eEnv.testUsername, password: e2eEnv.testPassword },
          timeout: 10_000,
        })
        expect(res.ok(), `fresh worker login failed: ${res.status()}`).toBeTruthy()
        const { access_token } = await res.json()
        await use(access_token as string)
      } finally {
        await ctx.dispose()
      }
    },
    { scope: 'worker' },
  ],
})

/** 真正未登录的干净 page：清空 localStorage，免疫 storageState 泄漏。用于「免登录页」smoke。 */
export const test = freshToken.extend<{
  cleanPage: Page
  authedPage: Page
}>({
  cleanPage: async ({ browser }, use) => {
    const context = await browser.newContext({ baseURL: e2eEnv.webBaseUrl })
    await context.addInitScript(() => {
      try {
        localStorage.clear()
      } catch {
        /* ignore */
      }
    })
    const page = await context.newPage()
    await use(page)
    await context.close()
  },

  authedPage: async ({ browser, freshToken }, use) => {
    const context = await browser.newContext({ baseURL: e2eEnv.webBaseUrl })
    const token = freshToken
    await context.addInitScript((t: string) => {
      try {
        localStorage.clear()
      } catch {
        /* ignore */
      }
      localStorage.setItem('user_token', t)
    }, token)
    const page = await context.newPage()
    await use(page)
    await context.close()
  },
})

export { expect }
