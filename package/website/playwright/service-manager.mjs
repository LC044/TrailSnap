import { execSync, spawn } from 'node:child_process'
import path from 'node:path'

export async function isPortInUse(port) {
  try {
    const res = await fetch(`http://localhost:${port}/system/version`, { signal: AbortSignal.timeout(2000) })
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
    if (serverRunning8800) {
      process.env.TS_API_BASE_URL = 'http://localhost:8800'
      process.env.TS_WEB_BASE_URL = 'http://localhost:8082'
    } else {
      process.env.TS_API_BASE_URL = 'http://localhost:8000'
      process.env.TS_WEB_BASE_URL = 'http://localhost:5176'
    }
    return { startedByUs: false }
  }

  console.log('Services are not running. Starting them...')
  
  if (isCI || isDocker) {
    // Docker compose start
    execSync('node playwright/e2e-up.mjs up', { stdio: 'inherit' })
    process.env.TS_API_BASE_URL = 'http://localhost:8800'
    process.env.TS_WEB_BASE_URL = 'http://localhost:8082'
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
    
    process.env.TS_API_BASE_URL = 'http://localhost:8000'
    process.env.TS_WEB_BASE_URL = 'http://localhost:5176'
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
