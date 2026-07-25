/**
 * Cross-platform E2E environment lifecycle (docker compose stack).
 *
 * Usage:
 *   node playwright/e2e-up.mjs          # default: up   —— pull + up -d + 等就绪
 *   node playwright/e2e-up.mjs up        # 同上
 *   node playwright/e2e-up.mjs down      # 停止并移除容器（保留 volume）
 *
 * 拉起 tests/docker/docker-compose.yml：postgres + server(:8800) + ai(:8801) + frontend(:8082)。
 * p0 / smoke / all 套件依赖这套已启动的环境（playwright.config.ts 的 webServer 为 undefined）。
 * 由 run-tests.ps1 -Mode docker 预起栈后，run-e2e.mjs full 的 startServices 复用本脚本作为 fallback。
 */

import { execSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(__dirname, '..', '..', '..')
const composeFile = path.join(repoRoot, 'tests', 'docker', 'docker-compose.yml')

const action = (process.argv[2] ?? 'up').toLowerCase()
if (!['up', 'down'].includes(action)) {
  console.error(`Unknown action: "${action}". Valid: up, down`)
  process.exit(1)
}

const compose = (...args) =>
  execSync(['docker', 'compose', '-f', composeFile, ...args].join(' '), { stdio: 'inherit' })

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** 轮询直到 url 返回 2xx-4xx（< 500），与 services-up.ps1 一致：后端根路径 404 也算就绪 */
async function waitHttpReady(url, timeoutMs = 180_000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(10_000) })
      if (res.status >= 200 && res.status < 500) {
        console.log(`Ready: ${url}`)
        return
      }
    } catch {
      // 还没起来，继续等
    }
    await sleep(3_000)
  }
  throw new Error(`Timed out waiting for ${url}`)
}

if (action === 'down') {
  console.log('Stopping E2E environment...')
  compose('down')
  console.log('E2E environment stopped.')
  process.exit(0)
}

console.log('Pulling E2E images...')
compose('pull')

console.log('Starting E2E environment...')
compose('up', '-d')

await waitHttpReady('http://localhost:8800/')
await waitHttpReady('http://localhost:8082/')

console.log('E2E environment is ready.')
