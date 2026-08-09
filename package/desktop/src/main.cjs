const { app, BrowserWindow, dialog } = require('electron')
const { spawn, spawnSync } = require('node:child_process')
const fs = require('node:fs')
const http = require('node:http')
const net = require('node:net')
const path = require('node:path')
const { AIExtensionManager } = require('./ai-extension-manager.cjs')
const { AIGateway } = require('./ai-gateway.cjs')

if (process.platform === 'win32' && process.env.LOCALAPPDATA) {
  app.setPath('userData', path.join(process.env.LOCALAPPDATA, 'TrailSnap'))
}

let mainWindow
let apiProcess
let webServer
let aiExtensionManager
let aiGateway
let shuttingDown = false

const mimeTypes = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.ico': 'image/x-icon',
  '.jpeg': 'image/jpeg',
  '.jpg': 'image/jpeg',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.webmanifest': 'application/manifest+json',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
}

function reservePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.unref()
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address()
      server.close((error) => error ? reject(error) : resolve(port))
    })
  })
}

function runtimePath(name) {
  if (app.isPackaged) return path.join(process.resourcesPath, name)
  if (name === 'web') return path.join(__dirname, '..', '..', 'website', 'dist')
  return path.join(__dirname, '..', 'server-dist', 'trailsnap-server')
}

function sidecarExecutable() {
  if (process.env.TS_DESKTOP_SERVER_BINARY) return process.env.TS_DESKTOP_SERVER_BINARY
  const binary = process.platform === 'win32' ? 'trailsnap-server.exe' : 'trailsnap-server'
  return path.join(runtimePath('server'), binary)
}

function openLogStreams() {
  const logDir = path.join(app.getPath('userData'), 'logs')
  fs.mkdirSync(logDir, { recursive: true })
  return {
    stdout: fs.openSync(path.join(logDir, 'server.log'), 'a'),
    stderr: fs.openSync(path.join(logDir, 'server.err.log'), 'a'),
  }
}

function startSidecar(port, aiGatewayPort) {
  const executable = sidecarExecutable()
  if (!fs.existsSync(executable)) throw new Error(`找不到后端程序：${executable}`)

  const dataDir = path.join(app.getPath('userData'), 'data')
  fs.mkdirSync(dataDir, { recursive: true })
  const envFile = path.join(dataDir, '.env')
  if (!fs.existsSync(envFile)) {
    fs.writeFileSync(envFile, [
      'DB_URL=postgresql://trailsnap:trailsnap@127.0.0.1:5532/trailsnap',
      'RAILWAY_DB_URL=postgresql://trailsnap:trailsnap@127.0.0.1:5532/railway',
      '# AI_API_URL is injected by the desktop AI gateway at runtime.',
      '',
    ].join('\n'), { encoding: 'utf8', mode: 0o600 })
  }
  const logs = openLogStreams()
  const env = {
    ...process.env,
    TS_DATA_DIR: dataDir,
    AI_API_URL: `http://127.0.0.1:${aiGatewayPort}`,
    TS_AI_API_URL: `http://127.0.0.1:${aiGatewayPort}`,
    TS_DESKTOP_AI_GATEWAY: `http://127.0.0.1:${aiGatewayPort}`,
  }

  apiProcess = spawn(executable, ['--port', String(port), '--parent-pid', String(process.pid)], {
    cwd: dataDir,
    env,
    detached: process.platform !== 'win32',
    windowsHide: true,
    stdio: ['ignore', logs.stdout, logs.stderr],
  })
  apiProcess.once('exit', (code, signal) => {
    if (!shuttingDown) console.error(`TrailSnap server exited unexpectedly (${code ?? signal})`)
  })
}

function jsonResponse(response, status, data) {
  response.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' })
  response.end(JSON.stringify(data))
}

async function readJsonBody(request, maxBytes = 1024 * 1024) {
  const chunks = []
  let size = 0
  for await (const chunk of request) {
    size += chunk.length
    if (size > maxBytes) throw new Error('请求体过大')
    chunks.push(chunk)
  }
  if (!chunks.length) return {}
  return JSON.parse(Buffer.concat(chunks).toString('utf8'))
}

async function handleDesktopApi(request, response) {
  const url = new URL(request.url, 'http://desktop.local')
  const segments = url.pathname.split('/').filter(Boolean)
  try {
    if (request.method === 'GET' && url.pathname === '/desktop-api/ai/extensions') {
      return jsonResponse(response, 200, { ...aiExtensionManager.list(), gateway: aiGateway.status() })
    }
    if (request.method === 'POST' && url.pathname === '/desktop-api/ai/extensions/refresh') {
      await aiExtensionManager.refreshCatalog()
      return jsonResponse(response, 200, aiExtensionManager.list())
    }
    if (request.method === 'POST' && url.pathname === '/desktop-api/ai/extensions/import') {
      const selection = await dialog.showOpenDialog(mainWindow, {
        title: '导入 TrailSnap AI 扩展包',
        properties: ['openFile'],
        filters: [{ name: 'TrailSnap AI 扩展包', extensions: ['gz', 'tgz'] }],
      })
      if (selection.canceled || !selection.filePaths[0]) return jsonResponse(response, 200, { canceled: true })
      const installed = await aiExtensionManager.importArchive(selection.filePaths[0])
      return jsonResponse(response, 200, { canceled: false, installed })
    }
    if (segments.length === 5 && segments[0] === 'desktop-api' && segments[1] === 'ai' && segments[2] === 'extensions') {
      const id = decodeURIComponent(segments[3])
      const action = segments[4]
      if (request.method === 'POST' && action === 'install') {
        const body = await readJsonBody(request)
        return jsonResponse(response, 202, aiExtensionManager.startInstall(id, body))
      }
      if (request.method === 'POST' && action === 'pause') return jsonResponse(response, 200, aiExtensionManager.pause(id))
      if (request.method === 'POST' && action === 'retry') return jsonResponse(response, 202, aiExtensionManager.retry(id))
      if (request.method === 'DELETE' && action === 'uninstall') {
        await aiExtensionManager.uninstall(id)
        return jsonResponse(response, 200, { removed: true })
      }
    }
    return jsonResponse(response, 404, { message: 'Desktop API not found' })
  } catch (error) {
    return jsonResponse(response, 400, { message: error.message })
  }
}

function waitForHealth(port, timeoutMs = 45000) {
  const started = Date.now()
  return new Promise((resolve, reject) => {
    const attempt = () => {
      if (apiProcess?.exitCode !== null) return reject(new Error('后端进程已提前退出'))
      const request = http.get(`http://127.0.0.1:${port}/health-check`, (response) => {
        response.resume()
        if (response.statusCode === 200) return resolve()
        retry()
      })
      request.setTimeout(1500, () => request.destroy())
      request.once('error', retry)
    }
    const retry = () => {
      if (Date.now() - started >= timeoutMs) reject(new Error('等待本地服务启动超时'))
      else setTimeout(attempt, 350)
    }
    attempt()
  })
}

function proxyApi(request, response, apiPort) {
  const headers = { ...request.headers, host: `127.0.0.1:${apiPort}` }
  const targetPath = request.url.replace(/^\/api(?=\/|\?|$)/, '') || '/'
  const upstream = http.request({
    hostname: '127.0.0.1',
    port: apiPort,
    path: targetPath,
    method: request.method,
    headers,
  }, (upstreamResponse) => {
    response.writeHead(upstreamResponse.statusCode || 502, upstreamResponse.headers)
    upstreamResponse.pipe(response)
  })
  upstream.once('error', (error) => {
    if (!response.headersSent) response.writeHead(502, { 'content-type': 'application/json; charset=utf-8' })
    response.end(JSON.stringify({ code: 1, message: `本地服务不可用：${error.message}`, data: null }))
  })
  request.pipe(upstream)
}

function safeWebFile(webRoot, requestUrl) {
  let pathname
  try { pathname = decodeURIComponent(new URL(requestUrl, 'http://desktop.local').pathname) }
  catch { return null }
  const relative = pathname.replace(/^\/+/, '')
  const candidate = path.resolve(webRoot, relative || 'index.html')
  if (candidate !== webRoot && !candidate.startsWith(`${webRoot}${path.sep}`)) return null
  if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) return candidate
  return path.join(webRoot, 'index.html')
}

async function startWebServer(apiPort) {
  const webRoot = path.resolve(runtimePath('web'))
  if (!fs.existsSync(path.join(webRoot, 'index.html'))) throw new Error(`找不到前端构建产物：${webRoot}`)
  const port = await reservePort()
  webServer = http.createServer((request, response) => {
    const expectedHost = `127.0.0.1:${port}`
    if (request.headers.host !== expectedHost) {
      response.writeHead(403)
      return response.end('Forbidden host')
    }
    if (/^\/desktop-api(?:\/|\?|$)/.test(request.url)) {
      const mutating = !['GET', 'HEAD', 'OPTIONS'].includes(request.method)
      if (mutating && request.headers.origin !== `http://${expectedHost}`) {
        response.writeHead(403)
        return response.end('Forbidden origin')
      }
      handleDesktopApi(request, response)
      return
    }
    if (/^\/api(?:\/|\?|$)/.test(request.url)) return proxyApi(request, response, apiPort)
    const file = safeWebFile(webRoot, request.url)
    if (!file) {
      response.writeHead(400)
      return response.end('Bad request')
    }
    response.writeHead(200, {
      'content-type': mimeTypes[path.extname(file).toLowerCase()] || 'application/octet-stream',
      'cache-control': path.basename(file) === 'index.html' ? 'no-cache' : 'public, max-age=31536000, immutable',
      'x-content-type-options': 'nosniff',
    })
    fs.createReadStream(file).pipe(response)
  })
  await new Promise((resolve, reject) => {
    webServer.once('error', reject)
    webServer.listen(port, '127.0.0.1', resolve)
  })
  return port
}

async function createWindow(url) {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 960,
    minHeight: 640,
    show: false,
    title: 'TrailSnap 行影集',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })
  mainWindow.once('ready-to-show', () => mainWindow.show())
  mainWindow.webContents.setWindowOpenHandler(({ url: externalUrl }) => {
    require('electron').shell.openExternal(externalUrl)
    return { action: 'deny' }
  })
  await mainWindow.loadURL(url)
}

async function stopSidecar() {
  shuttingDown = true
  if (webServer) await new Promise((resolve) => webServer.close(resolve))
  if (aiGateway) await aiGateway.close()
  if (!apiProcess || apiProcess.exitCode !== null) return

  if (process.platform === 'win32') {
    // Ask Windows to stop the whole sidecar tree. The API process owns a
    // multiprocessing worker, so terminating only the direct child can leave
    // that worker behind.
    spawnSync('taskkill', ['/pid', String(apiProcess.pid), '/t'], { windowsHide: true })
  } else {
    try { process.kill(-apiProcess.pid, 'SIGTERM') } catch { apiProcess.kill('SIGTERM') }
  }

  await new Promise((resolve) => {
    const timer = setTimeout(() => {
      if (process.platform === 'win32') {
        spawnSync('taskkill', ['/pid', String(apiProcess.pid), '/t', '/f'], { windowsHide: true })
      } else {
        try { process.kill(-apiProcess.pid, 'SIGKILL') } catch {}
      }
      resolve()
    }, 5000)
    apiProcess.once('exit', () => { clearTimeout(timer); resolve() })
  })
}

app.whenReady().then(async () => {
  try {
    const catalogUrl = process.env.TS_AI_EXTENSION_CATALOG_URL ||
      `https://github.com/LC044/TrailSnap/releases/download/v${app.getVersion()}/ai-extensions.json`
    aiExtensionManager = new AIExtensionManager({
      userData: app.getPath('userData'),
      catalogPath: path.join(__dirname, 'ai-extensions.json'),
      catalogUrl,
      beforeRemove: async () => aiGateway?.stopSidecar(),
    })
    await aiExtensionManager.initialize()
    aiGateway = new AIGateway({ manager: aiExtensionManager, reservePort, userData: app.getPath('userData') })
    const aiGatewayPort = await aiGateway.listen()
    const apiPort = await reservePort()
    startSidecar(apiPort, aiGatewayPort)
    await waitForHealth(apiPort)
    const webPort = await startWebServer(apiPort)
    await createWindow(`http://127.0.0.1:${webPort}`)
  } catch (error) {
    const logPath = path.join(app.getPath('userData'), 'logs', 'server.err.log')
    const configPath = path.join(app.getPath('userData'), 'data', '.env')
    dialog.showErrorBox('TrailSnap 启动失败', `${error.message}\n\n阶段 0 需要可用的 PostgreSQL。请检查 ${configPath}。\n日志：${logPath}`)
    app.quit()
  }
})

app.on('before-quit', (event) => {
  if (shuttingDown) return
  event.preventDefault()
  stopSidecar().finally(() => app.quit())
})

app.on('window-all-closed', () => app.quit())
