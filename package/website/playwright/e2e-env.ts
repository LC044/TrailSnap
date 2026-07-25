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
 * 环境变量约定（与 run-e2e.mjs / e2e-up 等脚本一致）：
 *
 *   TS_E2E_SUITE        测试套件：dev | p0 | p1 | smoke | scan | all
 *                       默认 dev（pnpm test:e2e 行为不变）
 *   TS_API_BASE_URL     后端地址
 *                       dev  默认 http://localhost:8000
 *                       sys  默认 http://localhost:8800 (e2e-up 暴露端口)
 *   TS_WEB_BASE_URL     前端地址
 *                       dev  默认 http://localhost:5176
 *                       sys  默认 http://localhost:8082 (frontend nginx)
 *   TS_PHOTO_DIR        测试照片目录（默认 /testdata/photos）
 *   TS_TEST_USERNAME    P0/P1 套件登录账号（默认 e2e-admin，bootstrap.ts 注册）
 *   TS_TEST_PASSWORD    P0/P1 套件登录密码（默认 Passw0rd!123）
 *   TS_ADMIN_USERNAME   Admin 账号（默认 e2e-admin）
 *   TS_ADMIN_EMAIL      Admin 邮箱
 *   TS_ADMIN_PASSWORD   Admin 密码
 *   TS_ADMIN_SECURITY_QUESTION  Admin 安全问题
 *   TS_ADMIN_SECURITY_ANSWER    Admin 安全问题答案
 */

import path from 'node:path'

/** 测试套件标识 */
export type E2ESuite = 'dev' | 'p0' | 'p1' | 'smoke' | 'scan' | 'all' | 'light' | 'full'

/** 套件到默认 baseURL 后端的映射 */
const BACKEND_BY_SUITE: Record<E2ESuite, string> = {
  dev: 'http://localhost:8000',
  p0: 'http://localhost:8800',
  p1: 'http://localhost:8800',
  smoke: 'http://localhost:8800',
  scan: 'http://localhost:8800',
  all: 'http://localhost:8800',
  light: 'http://localhost:8800',
  full: 'http://localhost:8800',
}

/** 套件到默认 baseURL 前端的映射 */
const WEB_BY_SUITE: Record<E2ESuite, string> = {
  dev: 'http://localhost:5176',
  p0: 'http://localhost:8082',
  p1: 'http://localhost:8082',
  smoke: 'http://localhost:8082',
  scan: 'http://localhost:8082',
  all: 'http://localhost:8082',
  light: 'http://localhost:8082',
  full: 'http://localhost:8082',
}

/**
 * 解析 E2E 套件，未设或非法值时返回 dev。
 * Suite 决定 testDir / testMatch / globalSetup 等。
 */
export function resolveSuite(): E2ESuite {
  const raw = (process.env.TS_E2E_SUITE || 'dev').toLowerCase()
  if (raw === 'full_setup' || raw === 'full_teardown') return 'full'
  if (raw === 'p0' || raw === 'p1' || raw === 'smoke' || raw === 'scan' || raw === 'all' || raw === 'light' || raw === 'full') return raw as E2ESuite
  return 'dev'
}

/** 读取环境变量，trim 后返回；空字符串视为未设 */
function env(key: string): string | undefined {
  const v = process.env[key]
  if (v == null) return undefined
  const trimmed = v.trim()
  return trimmed === '' ? undefined : trimmed
}

function envFlag(key: string, defaultValue: boolean): boolean {
  const value = env(key)
  if (!value) return defaultValue
  return !['0', 'false', 'off', 'no'].includes(value.toLowerCase())
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

  /** 宿主机测试照片目录（用于本地校验 smoke/p0 目录是否存在） */
  get photoHostDirectory(): string {
    return env('TS_PHOTO_HOST_DIR') ?? this.photoDirectory
  },

  /** 是否启用文件夹扫描前置。默认关闭；显式开启时先跑独立 scan 入口，再进入实际套件。 */
  get enableFixtureScan(): boolean {
    return envFlag('TS_E2E_ENABLE_FIXTURE_SCAN', false)
  },

  /**
   * 测试结束后是否保留服务与数据（对应 run-tests.ps1 的 TS_TEST_KEEP_SERVICES）。
   * 开启时 99-teardown 跳过清理，方便用浏览器/接口查看测试完成后的现场状态。
   * 默认关闭（测完即清）。
   */
  get keepServices(): boolean {
    return envFlag('TS_TEST_KEEP_SERVICES', false)
  },

  /** P0 / P1 套件登录账号 */
  get testUsername(): string {
    return env('TS_TEST_USERNAME') ?? 'e2e-admin'
  },

  /** P0 / P1 套件登录密码 */
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
      case 'scan':
        // smoke 需要同时覆盖 tests/e2e/specs 与 e2e-system，故把根设为 package/website
        // 再由 testMatch 精确过滤两类目录。
        return '.'
      case 'all':
        // all = P0 + P1 + smoke 串行（由 run-e2e.mjs 实现）。此处 testDir 极少被直接调用，
        // 保留兜底：等价于 dev。
        return './tests/e2e'
      case 'p0':
      case 'p1':
      case 'dev':
      default:
        return './tests/e2e'
    }
  },

  /**
   * 套件对应的 testMatch 正则。
   *
   * - dev    : 全量（默认）
   * - p0     : tests/e2e/specs 下所有 spec，由 run-e2e.mjs 加 --grep @p0 过滤
   * - p1     : 同 p0，由 run-e2e.mjs 加 --grep "P1 - " 过滤
   * - smoke  : 扫 specs/ + e2e-system/，由 run-e2e.mjs 加 --grep @smoke 过滤
   *            （page-load 烟测在 specs/{album,photos,...}.spec.ts；系统烟测在 e2e-system/）
   * - scan   : 仅执行独立扫描准备入口，不跑业务断言
   * - all    : 兜底，等价于 dev
   */
  get testMatch(): RegExp {
    switch (this.suite) {
      case 'p0':
        return /specs\/.*\.spec\.ts$/
      case 'p1':
        return /specs\/.*\.spec\.ts$/
      case 'smoke':
        return /(specs|e2e-system)\/.*\.spec\.ts$/
      case 'scan':
        return /e2e-system\/scan-prep\/.*\.spec\.ts$/
      case 'all':
      case 'light':
      case 'full':
        return /specs\/.*\.spec\.ts$/
      case 'dev':
      default:
        return /.*\.spec\.ts$/
    }
  },

  /** 套件对应的 globalSetup 路径（dev/p0/p1/smoke/all 都需要登录态） */
  get globalSetup(): string | undefined {
    if (this.suite === 'scan') return './e2e-system/helpers/scan-global-setup.ts'
    if (this.suite === 'dev') return './tests/e2e/helpers/dev-global-setup.ts'
    // full：仅写 storageState 占位文件，真实登录/扫描交给 00-setup.spec.ts。
    // full_setup / full_teardown 都 resolve 到 full，故两者都走这里。
    if (this.suite === 'full') return './e2e-system/helpers/full-global-setup.ts'
    // light：复用 full_setup 已落盘的真实 storageState，不再覆盖。
    if (this.suite === 'light') return undefined
    return './e2e-system/helpers/bootstrap.ts'
  },

  /** 套件对应的 globalTeardown，负责清理本轮测试新增的目录配置。 */
  get globalTeardown(): string | undefined {
    if (this.suite === 'scan') return undefined
    if (this.suite === 'light' || this.suite === 'full') return undefined
    return './playwright/global-teardown.ts'
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

  /** 套件运行时目录（storageState / 准备状态缓存等共享） */
  get runtimeDir(): string {
    if (this.suite === 'dev') {
      return path.resolve(process.cwd(), '.playwright-dev')
    }
    return path.resolve(process.cwd(), '.playwright-system')
  },
}
