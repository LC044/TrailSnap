const crypto = require('node:crypto')
const fs = require('node:fs')
const fsp = require('node:fs/promises')
const http = require('node:http')
const https = require('node:https')
const path = require('node:path')
const { spawn } = require('node:child_process')

const PLATFORM_KEY = `${process.platform}-${process.arch}`

function request(url, options = {}) {
  return new Promise((resolve, reject) => {
    const client = new URL(url).protocol === 'https:' ? https : http
    const { timeoutMs = 30000, ...requestOptions } = options
    const req = client.get(url, requestOptions, (response) => {
      if ([301, 302, 303, 307, 308].includes(response.statusCode) && response.headers.location) {
        response.resume()
        return resolve(request(new URL(response.headers.location, url).toString(), options))
      }
      resolve({ req, response })
    })
    req.setTimeout(timeoutMs, () => req.destroy(new Error('网络请求超时')))
    req.once('error', reject)
  })
}

async function readJsonResponse(url, timeoutMs = 8000) {
  const { response } = await request(url, { timeoutMs })
  if (response.statusCode !== 200) {
    response.resume()
    throw new Error(`扩展包清单返回 HTTP ${response.statusCode}`)
  }
  const chunks = []
  for await (const chunk of response) chunks.push(chunk)
  return JSON.parse(Buffer.concat(chunks).toString('utf8'))
}

async function sha256File(filePath) {
  const hash = crypto.createHash('sha256')
  const stream = fs.createReadStream(filePath)
  for await (const chunk of stream) hash.update(chunk)
  return hash.digest('hex')
}

function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { ...options, windowsHide: true })
    let stdout = ''
    let stderr = ''
    child.stdout?.on('data', (chunk) => { stdout += chunk })
    child.stderr?.on('data', (chunk) => { stderr += chunk })
    child.once('error', reject)
    child.once('exit', (code) => code === 0
      ? resolve({ stdout, stderr })
      : reject(new Error(`${command} 失败 (${code})：${stderr.trim()}`)))
  })
}

function assertArchiveEntries(entries) {
  for (const raw of entries) {
    const entry = raw.trim().replaceAll('\\', '/')
    if (!entry) continue
    if (entry.startsWith('/') || /^[A-Za-z]:\//.test(entry) || entry.split('/').includes('..')) {
      throw new Error(`扩展包包含不安全路径：${raw}`)
    }
  }
}

class AIExtensionManager {
  constructor({ userData, catalogPath, catalogUrl, platformKey = PLATFORM_KEY, beforeRemove } = {}) {
    if (!userData) throw new Error('userData is required')
    this.userData = path.resolve(userData)
    this.root = path.join(this.userData, 'ai-extensions')
    this.downloadDir = path.join(this.root, '.downloads')
    this.statePath = path.join(this.root, 'installed.json')
    this.catalogPath = catalogPath
    this.catalogUrl = catalogUrl
    this.platformKey = platformKey
    this.beforeRemove = beforeRemove
    this.jobs = new Map()
    this.catalog = { schemaVersion: 1, extensions: [] }
    this.installed = {}
  }

  async initialize() {
    await fsp.mkdir(this.downloadDir, { recursive: true })
    try { this.catalog = JSON.parse(await fsp.readFile(this.catalogPath, 'utf8')) } catch {}
    try { this.installed = JSON.parse(await fsp.readFile(this.statePath, 'utf8')).extensions || {} } catch {}
    // Do not delay desktop startup when the release catalog is offline. The
    // settings page polls this manager and will observe the refreshed data.
    this.refreshCatalog()
  }

  async refreshCatalog() {
    if (!this.catalogUrl) return this.catalog
    try {
      const remote = await readJsonResponse(this.catalogUrl)
      if (!Array.isArray(remote.extensions)) throw new Error('清单缺少 extensions 数组')
      this.catalog = remote
      this.catalogError = null
    } catch (error) {
      this.catalogError = error.message
    }
    return this.catalog
  }

  list() {
    return {
      platform: this.platformKey,
      catalogError: this.catalogError || null,
      extensions: this.catalog.extensions.map((extension) => {
        const asset = extension.assets?.[this.platformKey] || null
        const job = this.jobs.get(extension.id)
        return {
          ...extension,
          assets: undefined,
          available: Boolean(asset?.url && asset?.sha256),
          downloadSize: asset?.size || null,
          installed: this.installed[extension.id] || null,
          job: job ? { ...job, request: undefined } : null,
        }
      }),
    }
  }

  getInstalled(id) {
    const installed = this.installed[id]
    if (!installed) return null
    return { ...installed, directory: path.join(this.root, id) }
  }

  async _saveState() {
    const temp = `${this.statePath}.tmp`
    await fsp.writeFile(temp, JSON.stringify({ schemaVersion: 1, extensions: this.installed }, null, 2))
    await fsp.rename(temp, this.statePath)
  }

  startInstall(id, overrides = {}) {
    const extension = this.catalog.extensions.find((item) => item.id === id)
    if (!extension) throw new Error(`未知 AI 扩展包：${id}`)
    const existing = this.jobs.get(id)
    if (existing && ['downloading', 'verifying', 'installing'].includes(existing.status)) return existing
    const asset = { ...(extension.assets?.[this.platformKey] || {}), ...overrides }
    if (!asset.url || !asset.sha256) throw new Error('当前平台暂无可下载且带 SHA-256 的扩展包')
    const job = {
      id,
      status: 'downloading',
      received: 0,
      total: asset.size || null,
      progress: 0,
      error: null,
      updatedAt: new Date().toISOString(),
    }
    this.jobs.set(id, job)
    this._installRemote(extension, asset, job).catch((error) => {
      if (job.status !== 'paused') job.status = 'failed'
      job.error = job.status === 'paused' ? null : error.message
      job.updatedAt = new Date().toISOString()
    })
    return job
  }

  pause(id) {
    const job = this.jobs.get(id)
    if (!job || job.status !== 'downloading') throw new Error('扩展包当前不在下载中')
    job.status = 'paused'
    job.request?.destroy(Object.assign(new Error('下载已暂停'), { code: 'PAUSED' }))
    job.request = undefined
    return job
  }

  retry(id) {
    const job = this.jobs.get(id)
    if (!job || !['paused', 'failed'].includes(job.status)) throw new Error('扩展包当前不可重试')
    this.jobs.delete(id)
    return this.startInstall(id)
  }

  async _installRemote(extension, asset, job) {
    const archive = path.join(this.downloadDir, `${extension.id}-${this.platformKey}.tar.gz.part`)
    let offset = 0
    try { offset = (await fsp.stat(archive)).size } catch {}
    const headers = offset ? { Range: `bytes=${offset}-` } : {}
    const { req, response } = await request(asset.url, { headers })
    job.request = req
    if (![200, 206].includes(response.statusCode)) {
      response.resume()
      throw new Error(`扩展包下载返回 HTTP ${response.statusCode}`)
    }
    if (offset && response.statusCode === 200) {
      offset = 0
      await fsp.rm(archive, { force: true })
    }
    const contentLength = Number(response.headers['content-length'] || 0)
    job.total = asset.size || (contentLength ? offset + contentLength : null)
    job.received = offset
    const output = fs.createWriteStream(archive, { flags: offset ? 'a' : 'w' })
    await new Promise((resolve, reject) => {
      response.on('data', (chunk) => {
        job.received += chunk.length
        job.progress = job.total ? Math.min(100, Math.round(job.received / job.total * 100)) : 0
        job.updatedAt = new Date().toISOString()
      })
      response.once('error', reject)
      output.once('error', reject)
      output.once('finish', resolve)
      response.pipe(output)
    })
    job.request = undefined
    if (job.status === 'paused') return
    await this._installArchive(extension.id, archive, asset.sha256, job)
    await fsp.rm(archive, { force: true })
  }

  async importArchive(filePath) {
    const archive = path.resolve(filePath)
    const checksum = await sha256File(archive)
    const temp = await this._extractArchive(archive)
    try {
      const manifest = JSON.parse(await fsp.readFile(path.join(temp, 'manifest.json'), 'utf8'))
      const extension = this.catalog.extensions.find((item) => item.id === manifest.id)
      if (!extension) throw new Error(`离线包 ID 不在清单中：${manifest.id}`)
      const job = { id: manifest.id, status: 'installing', progress: 100, received: 0, total: 0, error: null }
      this.jobs.set(manifest.id, job)
      await this._activateExtracted(manifest.id, temp, checksum, job)
      return this.getInstalled(manifest.id)
    } catch (error) {
      await fsp.rm(temp, { recursive: true, force: true })
      throw error
    }
  }

  async _installArchive(id, archive, expectedChecksum, job) {
    job.status = 'verifying'
    const actual = await sha256File(archive)
    if (actual.toLowerCase() !== expectedChecksum.toLowerCase()) {
      throw new Error(`SHA-256 校验失败：期望 ${expectedChecksum}，实际 ${actual}`)
    }
    const temp = await this._extractArchive(archive)
    try {
      await this._activateExtracted(id, temp, actual, job)
    } catch (error) {
      await fsp.rm(temp, { recursive: true, force: true })
      throw error
    }
  }

  async _extractArchive(archive) {
    const temp = await fsp.mkdtemp(path.join(this.root, '.install-'))
    try {
      const listing = await run('tar', ['-tzf', archive])
      assertArchiveEntries(listing.stdout.split(/\r?\n/))
      await run('tar', ['-xzf', archive, '-C', temp])
      return temp
    } catch (error) {
      await fsp.rm(temp, { recursive: true, force: true })
      throw error
    }
  }

  async _activateExtracted(id, temp, checksum, job) {
    job.status = 'installing'
    const manifestPath = path.join(temp, 'manifest.json')
    const manifest = JSON.parse(await fsp.readFile(manifestPath, 'utf8'))
    if (manifest.id !== id) throw new Error(`扩展包 ID 不匹配：${manifest.id}`)
    if (manifest.platform !== this.platformKey) throw new Error(`扩展包平台不匹配：${manifest.platform}`)
    if (!manifest.version || !Array.isArray(manifest.capabilities)) throw new Error('扩展包 manifest 无效')
    const entrypoint = path.resolve(temp, manifest.entrypoint || '')
    if (!entrypoint.startsWith(`${temp}${path.sep}`) || !(await fsp.stat(entrypoint)).isFile()) {
      throw new Error('扩展包入口文件无效')
    }
    const destination = path.join(this.root, id)
    const backup = `${destination}.old`
    await fsp.rm(backup, { recursive: true, force: true })
    try { await fsp.rename(destination, backup) } catch (error) { if (error.code !== 'ENOENT') throw error }
    try {
      await fsp.rename(temp, destination)
      await fsp.rm(backup, { recursive: true, force: true })
    } catch (error) {
      try { await fsp.rename(backup, destination) } catch {}
      throw error
    }
    this.installed[id] = {
      id,
      version: manifest.version,
      platform: manifest.platform,
      capabilities: manifest.capabilities,
      entrypoint: manifest.entrypoint,
      modelPath: manifest.modelPath || null,
      checksum,
      installedAt: new Date().toISOString(),
    }
    await this._saveState()
    job.status = 'installed'
    job.progress = 100
    job.updatedAt = new Date().toISOString()
  }

  async uninstall(id) {
    if (!this.installed[id]) throw new Error('扩展包尚未安装')
    await this.beforeRemove?.(id)
    const target = path.resolve(this.root, id)
    if (path.dirname(target) !== this.root) throw new Error('扩展包路径越界')
    await fsp.rm(target, { recursive: true, force: true })
    delete this.installed[id]
    this.jobs.delete(id)
    await this._saveState()
  }
}

module.exports = { AIExtensionManager, assertArchiveEntries, sha256File }
