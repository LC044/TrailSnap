import { execSync, spawn } from 'node:child_process'
import path from 'node:path'

export async function isPortInUse(port) {
  try {
    // 用 127.0.0.1 而非 localhost：Windows 下 localhost 可能先解析到 IPv6 ::1，
    // 若服务只绑了 IPv4 会误判端口空闲（参见 commit 2569165 健康检查同类问题）。
    const res = await fetch(`http://127.0.0.1:${port}/system/version`, { signal: AbortSignal.timeout(2000) })
    return res.ok || res.status < 500
  } catch {
    return false
  }
}

export async function startServices() {
  const isCI = !!process.env.CI
  const isDocker = process.env.TS_ENV === 'docker' || process.env.TS_E2E_SUITE === 'smoke' || process.env.TS_E2E_SUITE === 'full'

  const serverRunning8000 = await isPortInUse(8000)
  const serverRunning8800 = await isPortInUse(8800)
  const serverRunning = serverRunning8000 || serverRunning8800

  if (serverRunning) {
    console.log('Services are already running.')
    // 只在未设置时兜底，绝不覆盖 .env.test 已注入的 TS_API_BASE_URL / TS_WEB_BASE_URL。
    // photo-fixtures 的 state cache 以 apiBaseUrl 为 key（photo-fixtures.ts getStatePaths），
    // scan-prep 用的是 .env.test 里的 127.0.0.1:8000；若这里把 127.0.0.1 改写成 localhost，
    // full_setup 阶段会算出不同的 cache key → 缓存未命中 → 00-setup 重复 POST /settings/directories，
    // 撞上瞬时状态就回 400 Path does not exist。统一用 127.0.0.1 也可避开 IPv6 ::1 歧义。
    if (serverRunning8800) {
      process.env.TS_API_BASE_URL ??= 'http://127.0.0.1:8800'
      process.env.TS_WEB_BASE_URL ??= 'http://127.0.0.1:8082'
    } else {
      process.env.TS_API_BASE_URL ??= 'http://127.0.0.1:8000'
      process.env.TS_WEB_BASE_URL ??= 'http://127.0.0.1:5176'
    }
    return { startedByUs: false }
  }

  console.log('Services are not running. Starting them...')
  
  if (isCI || isDocker) {
    // Docker compose start
    execSync('node playwright/e2e-up.mjs up', { stdio: 'inherit' })
    process.env.TS_API_BASE_URL ??= 'http://127.0.0.1:8800'
    process.env.TS_WEB_BASE_URL ??= 'http://127.0.0.1:8082'
    return { startedByUs: true, method: 'docker' }
  } else {
    // Dev environment start
    // Start backend
    const serverProcess = spawn('uv', ['run', 'python', 'start.py'], {
      cwd: path.resolve(process.cwd(), '../server'),
      stdio: 'inherit',
      shell: true
    })
    
    // Start AI service
    const aiProcess = spawn('uv', ['run', 'uvicorn', 'main:app', '--host', '0.0.0.0', '--port', '8001'], {
      cwd: path.resolve(process.cwd(), '../ai'),
      stdio: 'inherit',
      shell: true
    })

    // Wait for them to be ready
    let retries = 30
    while (retries > 0) {
      if (await isPortInUse(8000)) break
      await new Promise(r => setTimeout(r, 2000))
      retries--
    }
    
    process.env.TS_API_BASE_URL ??= 'http://127.0.0.1:8000'
    process.env.TS_WEB_BASE_URL ??= 'http://127.0.0.1:5176'
    return { startedByUs: true, method: 'dev', processes: [serverProcess, aiProcess] }
  }
}

export function stopServices(startInfo) {
  if (!startInfo || !startInfo.startedByUs) {
    console.log('Services were not started by us, leaving them running.')
    return
  }

  console.log('Stopping services...')
  if (startInfo.method === 'docker') {
    execSync('node playwright/e2e-up.mjs down', { stdio: 'inherit' })
  } else if (startInfo.method === 'dev') {
    for (const proc of startInfo.processes) {
      try {
        proc.kill()
      } catch (e) {
        console.error('Failed to kill process:', e)
      }
    }
  }
}
