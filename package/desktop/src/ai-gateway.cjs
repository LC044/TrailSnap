const fs = require('node:fs')
const http = require('node:http')
const path = require('node:path')
const { spawn, spawnSync } = require('node:child_process')

class AIGateway {
  constructor({ manager, reservePort, userData, parentPid = process.pid, idleTimeoutMs = 10 * 60 * 1000 }) {
    this.manager = manager
    this.reservePort = reservePort
    this.userData = userData
    this.parentPid = parentPid
    this.idleTimeoutMs = idleTimeoutMs
    this.lastRequestAt = 0
    this.startPromise = null
  }

  async listen() {
    this.port = await this.reservePort()
    this.server = http.createServer((request, response) => this.proxy(request, response))
    await new Promise((resolve, reject) => {
      this.server.once('error', reject)
      this.server.listen(this.port, '127.0.0.1', resolve)
    })
    this.idleTimer = setInterval(() => {
      if (this.process && Date.now() - this.lastRequestAt >= this.idleTimeoutMs) this.stopSidecar()
    }, Math.min(60000, this.idleTimeoutMs))
    this.idleTimer.unref()
    return this.port
  }

  status() {
    return {
      port: this.port,
      running: Boolean(this.process && this.process.exitCode === null),
      pid: this.process?.pid || null,
      extension: this.activeExtension?.id || null,
      lastRequestAt: this.lastRequestAt || null,
    }
  }

  async ensureSidecar() {
    if (this.process && this.process.exitCode === null) return
    if (this.startPromise) return this.startPromise
    this.startPromise = this._startSidecar().finally(() => { this.startPromise = null })
    return this.startPromise
  }

  async _startSidecar() {
    const extension = Object.values(this.manager.installed)
      .find((item) => ['ocr', 'tickets', 'classification'].some((capability) => item.capabilities.includes(capability)))
    if (!extension) throw new Error('尚未安装 AI 扩展包')
    const installed = this.manager.getInstalled(extension.id)
    const executable = path.resolve(installed.directory, installed.entrypoint)
    if (!executable.startsWith(`${installed.directory}${path.sep}`) || !fs.existsSync(executable)) {
      throw new Error('AI 扩展包入口不存在，请重新安装')
    }
    const port = await this.reservePort()
    const logDir = path.join(this.userData, 'logs')
    const modelDir = installed.modelPath
      ? path.resolve(installed.directory, installed.modelPath)
      : path.join(this.userData, 'models')
    if (installed.modelPath && !modelDir.startsWith(`${installed.directory}${path.sep}`)) {
      throw new Error('AI 扩展包模型路径无效')
    }
    fs.mkdirSync(logDir, { recursive: true })
    fs.mkdirSync(modelDir, { recursive: true })
    const stdout = fs.openSync(path.join(logDir, 'ai.log'), 'a')
    const stderr = fs.openSync(path.join(logDir, 'ai.err.log'), 'a')
    this.process = spawn(executable, ['--port', String(port), '--parent-pid', String(this.parentPid)], {
      cwd: this.userData,
      env: {
        ...process.env,
        MODEL_PATH: modelDir,
        AI_CONFIG_PATH: path.join(this.userData, 'ai-config.json'),
        TS_AI_LOG_DIR: logDir,
      },
      detached: process.platform !== 'win32',
      windowsHide: true,
      stdio: ['ignore', stdout, stderr],
    })
    this.process.once('exit', () => {
      this.process = null
      this.activeExtension = null
    })
    try {
      await this._waitForHealth(port)
    } catch (error) {
      await this.stopSidecar()
      throw error
    }
    this.sidecarPort = port
    this.activeExtension = extension
    this.lastRequestAt = Date.now()
  }

  _waitForHealth(port, timeoutMs = 90000) {
    const started = Date.now()
    return new Promise((resolve, reject) => {
      const attempt = () => {
        if (!this.process || this.process.exitCode !== null) return reject(new Error('AI Sidecar 提前退出'))
        const req = http.get(`http://127.0.0.1:${port}/health-check`, (response) => {
          response.resume()
          if (response.statusCode === 200) resolve()
          else retry()
        })
        req.setTimeout(1500, () => req.destroy())
        req.once('error', retry)
      }
      const retry = () => Date.now() - started >= timeoutMs
        ? reject(new Error('等待 AI Sidecar 启动超时'))
        : setTimeout(attempt, 400)
      attempt()
    })
  }

  async proxy(request, response) {
    try {
      await this.ensureSidecar()
      this.lastRequestAt = Date.now()
      const upstream = http.request({
        hostname: '127.0.0.1',
        port: this.sidecarPort,
        path: request.url,
        method: request.method,
        headers: { ...request.headers, host: `127.0.0.1:${this.sidecarPort}` },
      }, (upstreamResponse) => {
        response.writeHead(upstreamResponse.statusCode || 502, upstreamResponse.headers)
        upstreamResponse.pipe(response)
      })
      upstream.once('error', (error) => this._error(response, 502, error.message))
      request.pipe(upstream)
    } catch (error) {
      this._error(response, 503, error.message)
    }
  }

  _error(response, status, message) {
    if (!response.headersSent) response.writeHead(status, { 'content-type': 'application/json; charset=utf-8' })
    response.end(JSON.stringify({ detail: message, extensionRequired: true }))
  }

  async stopSidecar() {
    const child = this.process
    if (!child || child.exitCode !== null) return
    if (process.platform === 'win32') {
      spawnSync('taskkill', ['/pid', String(child.pid), '/t'], { windowsHide: true })
    } else {
      try { process.kill(-child.pid, 'SIGTERM') } catch { child.kill('SIGTERM') }
    }
    await new Promise((resolve) => {
      const timer = setTimeout(() => {
        if (process.platform === 'win32') spawnSync('taskkill', ['/pid', String(child.pid), '/t', '/f'], { windowsHide: true })
        else { try { process.kill(-child.pid, 'SIGKILL') } catch {} }
        resolve()
      }, 5000)
      child.once('exit', () => { clearTimeout(timer); resolve() })
    })
  }

  async close() {
    clearInterval(this.idleTimer)
    await this.stopSidecar()
    if (this.server) await new Promise((resolve) => this.server.close(resolve))
  }
}

module.exports = { AIGateway }
