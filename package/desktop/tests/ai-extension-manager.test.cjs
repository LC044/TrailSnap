const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { execFileSync } = require('node:child_process')
const test = require('node:test')

const { AIExtensionManager, assertArchiveEntries, sha256File } = require('../src/ai-extension-manager.cjs')

test('archive traversal paths are rejected', () => {
  assert.throws(() => assertArchiveEntries(['manifest.json', '../escape.txt']), /不安全路径/)
  assert.throws(() => assertArchiveEntries(['C:/escape.txt']), /不安全路径/)
})

test('offline extension import validates manifest and persists installed state', async (context) => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'trailsnap-ai-test-'))
  context.after(() => fs.rmSync(temp, { recursive: true, force: true }))
  const source = path.join(temp, 'source')
  fs.mkdirSync(path.join(source, 'runtime'), { recursive: true })
  fs.writeFileSync(path.join(source, 'runtime', 'trailsnap-ai'), 'test-runtime')
  fs.writeFileSync(path.join(source, 'manifest.json'), JSON.stringify({
    id: 'core-ai',
    version: '1.0.0',
    platform: 'test-x64',
    capabilities: ['ocr'],
    entrypoint: 'runtime/trailsnap-ai',
  }))
  const archive = path.join(temp, 'extension.tar.gz')
  execFileSync('tar', ['-czf', archive, '-C', source, '.'])

  const catalog = path.join(temp, 'catalog.json')
  fs.writeFileSync(catalog, JSON.stringify({ schemaVersion: 1, extensions: [{ id: 'core-ai', assets: {} }] }))
  const manager = new AIExtensionManager({ userData: path.join(temp, 'user'), catalogPath: catalog, platformKey: 'test-x64' })
  await manager.initialize()
  const installed = await manager.importArchive(archive)

  assert.equal(installed.version, '1.0.0')
  assert.equal(installed.checksum, await sha256File(archive))
  assert.ok(fs.existsSync(path.join(installed.directory, 'runtime', 'trailsnap-ai')))
  assert.equal(manager.list().extensions[0].installed.version, '1.0.0')

  await manager.uninstall('core-ai')
  assert.equal(manager.getInstalled('core-ai'), null)
})

test('an extension for another platform is rejected', async (context) => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'trailsnap-ai-platform-'))
  context.after(() => fs.rmSync(temp, { recursive: true, force: true }))
  const source = path.join(temp, 'source')
  fs.mkdirSync(path.join(source, 'runtime'), { recursive: true })
  fs.writeFileSync(path.join(source, 'runtime', 'trailsnap-ai'), 'test-runtime')
  fs.writeFileSync(path.join(source, 'manifest.json'), JSON.stringify({
    id: 'core-ai', version: '1.0.0', platform: 'other-x64', capabilities: ['ocr'], entrypoint: 'runtime/trailsnap-ai',
  }))
  const archive = path.join(temp, 'extension.tar.gz')
  execFileSync('tar', ['-czf', archive, '-C', source, '.'])
  const catalog = path.join(temp, 'catalog.json')
  fs.writeFileSync(catalog, JSON.stringify({ schemaVersion: 1, extensions: [{ id: 'core-ai', assets: {} }] }))
  const manager = new AIExtensionManager({ userData: path.join(temp, 'user'), catalogPath: catalog, platformKey: 'test-x64' })
  await manager.initialize()
  await assert.rejects(manager.importArchive(archive), /平台不匹配/)
})
