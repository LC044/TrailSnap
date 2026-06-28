/**
 * TrailSnap E2E test environment configuration.
 *
 * 集中定义所有 E2E 相关环境变量的默认值和类型，
 * 避免散落在多个 playwright config 文件里。
 *
 * 使用：
 *   import { e2eEnv, E2ESuite } from './playwright/e2e-env'
 *   e2eEnv.apiBaseUrl  // string
 *
 * 环境变量约定（与 e2e-run.ps1 / e2e-up.ps1 一致）：
 *
 *   TS_E2E_SUITE        测试套件：dev | p0 | smoke | all
 *                       默认 dev（pnpm test:e2e 行为不变）
 *   TS_API_BASE_URL     后端地址
 *                       dev  默认 http://localhost:8000
 *                       sys  默认 http://localhost:8800 (e2e-up 暴露端口)
 *   TS_WEB_BASE_URL     前端地址
 *                       dev  默认 http://localhost:5176
 *                       sys  默认 http://localhost:8082 (frontend nginx)
 *   TS_PHOTO_DIR        测试照片目录（默认 /testdata/photos）
 *   TS_TEST_USERNAME    P0 套件登录账号（默认 e2e-admin，bootstrap.ts 注册）
 *   TS_TEST_PASSWORD    P0 套件登录密码（默认 Passw0rd!123）
 *   TS_ADMIN_USERNAME   Admin 账号（默认 e2e-admin）
 *   TS_ADMIN_EMAIL      Admin 邮箱
 *   TS_ADMIN_PASSWORD   Admin 密码
 *   TS_ADMIN_SECURITY_QUESTION  Admin 安全问题
 *   TS_ADMIN_SECURITY_ANSWER    Admin 安全问题答案
 */

import path from 'node:path'

/** 测试套件标识 */
export type E2ESuite = 'dev' | 'p0' | 'smoke' | 'all'

/** 套件到默认 baseURL 后端的映射 */
const BACKEND_BY_SUITE: Record<E2ESuite, string> = {
  dev: 'http://localhost:8000',
  p0: 'http://localhost:8800',
  smoke: 'http://localhost:8800',
  all: 'http://localhost:8800',
}

/** 套件到默认 baseURL 前端的映射 */
const WEB_BY_SUITE: Record<E2ESuite, string> = {
  dev: 'http://localhost:5176',
  p0: 'http://localhost:8082',
  smoke: 'http://localhost:8082',
  all: 'http://localhost:8082',
}

/**
 * 解析 E2E 套件，未设或非法值时返回 dev。
 * Suite 决定 testDir / testMatch / globalSetup 等。
 */
export function resolveSuite(): E2ESuite {
  const raw = (process.env.TS_E2E_SUITE || 'dev').toLowerCase()
  if (raw === 'p0' || raw === 'smoke' || raw === 'all') return raw
  return 'dev'
}

/** 读取环境变量，trim 后返回；空字符串视为未设 */
function env(key: string): string | undefined {
  const v = process.env[key]
  if (v == null) return undefined
  const trimmed = v.trim()
  return trimmed === '' ? undefined : trimmed
}

export const e2eEnv = {
  /** 当前套件 */
  get suite(): E2ESuite {
    return resolveSuite()
  },

  /** 后端 base URL（取决于套件 + 环境变量覆盖） */
  get apiBaseUrl(): string {
    return env('TS_API_BASE_URL') ?? BACKEND_BY_SUITE[this.suite]
  },

  /** 前端 base URL（取决于套件 + 环境变量覆盖） */
  get webBaseUrl(): string {
    return env('TS_WEB_BASE_URL') ?? WEB_BY_SUITE[this.suite]
  },

  /** 测试照片目录（用于 bootstrap.ts 自动注册） */
  get photoDirectory(): string {
    return env('TS_PHOTO_DIR') ?? '/testdata/photos'
  },

  /** P0 套件登录账号 */
  get testUsername(): string {
    return env('TS_TEST_USERNAME') ?? 'e2e-admin'
  },

  /** P0 套件登录密码 */
  get testPassword(): string {
    return env('TS_TEST_PASSWORD') ?? 'Passw0rd!123'
  },

  /** Bootstrap 注册的 admin 账号 */
  get adminUser() {
    return {
      username: env('TS_ADMIN_USERNAME') ?? 'e2e-admin',
      email: env('TS_ADMIN_EMAIL') ?? 'e2e-admin@example.com',
      password: env('TS_ADMIN_PASSWORD') ?? 'Passw0rd!123',
      securityQuestion:
        env('TS_ADMIN_SECURITY_QUESTION') ?? '测试问题',
      securityAnswer: env('TS_ADMIN_SECURITY_ANSWER') ?? '测试答案',
    }
  },

  /** 是否在 CI 模式（增加 retries、串行） */
  get isCI(): boolean {
    return !!env('CI')
  },

  /** 套件对应的 testDir（Playwright 1.60 不支持数组） */
  get testDir(): string {
    switch (this.suite) {
      case 'smoke':
        return './e2e-system'
      case 'all':
        // all = P0 + smoke。用 tests/e2e 作主目录，testMatch 同时匹配 e2e-system 下的 spec
        return './tests/e2e'
      case 'p0':
      case 'dev':
      default:
        return './tests/e2e'
    }
  },

  /** 套件对应的 testMatch 正则 */
  get testMatch(): RegExp {
    switch (this.suite) {
      case 'p0':
        // P0: 收集 tests/e2e/specs 下全部 spec（含域子目录），
        // 由 e2e-run.ps1 传 --grep @smoke 仅跑 @smoke 标记的关键用例。
        // 这样 spec 可自由分子目录，不再被文件名正则绑死。
        return /specs\/.*\.spec\.ts$/
      case 'smoke':
        // smoke: 只跑 e2e-system/{api,ui}/smoke.spec.ts
        return /(api|ui)\/smoke\.spec\.ts$/
      case 'all':
        // all 模式在 e2e-run.ps1 里通过两次串行执行实现 (TS_E2E_SUITE=p0 → smoke)；
        // 此处 'all' 几乎不会被直接调用（仅 e2e-run.ps1 切换 suite 后跑单套件），
        // 保留兜底：等价于 dev（跑全部 spec）
        return /.*\.spec\.ts$/
      case 'dev':
      default:
        // dev: 默认全部
        return /.*\.spec\.ts$/
    }
  },

  /** 套件对应的 globalSetup 路径（dev/p0/smoke/all 都需要登录态） */
  get globalSetup(): string | undefined {
    if (this.suite === 'dev') return './tests/e2e/helpers/dev-global-setup.ts'
    return './e2e-system/helpers/bootstrap.ts'
  },

  /** 套件对应的 storageState（用于全局已登录态） */
  get storageState(): string | undefined {
    if (this.suite === 'dev') {
      return path.resolve(process.cwd(), '.playwright-dev', 'storage-state.json')
    }
    return path.resolve(process.cwd(), '.playwright-system', 'storage-state.json')
  },

  /** 套件对应的 outputDir - 统一 .playwright-system 目录 */
  get outputDir(): string {
    return '.playwright-system/results'
  },

  /** 套件对应的 report 目录 - 统一 .playwright-system 目录 */
  get reportDir(): string {
    return '.playwright-system/report'
  },
}
