const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')
const vm = require('node:vm')

function harness(mode, options = {}) {
  const calls = []
  const source = fs.readFileSync(path.resolve(__dirname, '../../src/stores/desktopUpdates.ts'), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  const module = { exports: {} }
  const directory = {
    getDesktopDataDirectory: async () => ({ mode }), restartDesktop: async () => calls.push('restart'),
    isDesktopDrainPending: cause => String(cause).startsWith('后台任务仍在结束'),
    waitForDesktopDrain: async () => { calls.push('wait'); if (options.pending) throw '后台任务仍在结束，请继续等待' },
  }
  const api = {
    getDesktopUpdateStatus: async () => ({ transaction: options.rolledBack ? { phase: 'rolled_back', version: '1.0.1', error: '照片校验失败' } : null, backupPath: 'D:/Library/userdata/backups/test' }),
    checkPortableUpdate: async () => { if (options.checkError) throw Error('catalog 404'); return { phase: options.ready ? 'ready' : 'available', version: options.latestVersion || '1.0.1', size: 10 } },
    downloadPortableUpdate: async () => calls.push('portable-download'),
    applyPortableUpdate: async () => { calls.push('portable-apply'); if (options.pending) throw '后台任务仍在结束，请继续等待' },
    checkInstalledUpdate: async () => ({ version: '1.0.1', download: async () => calls.push('installer-download'), install: async () => calls.push('installer-install') }),
    prepareInstalledUpdate: async () => { calls.push('drain-backup'); if (options.failDrain) throw Error('backup failed') },
  }
  vm.runInNewContext(`(function(require,module,exports){${code}\n})`)(name => {
    if (name === 'vue') return { ref: value => ({ value }) }
    if (name === 'pinia') return { defineStore: (_name, setup) => setup }
    if (name === '@tauri-apps/api/event') return { listen: async () => () => {} }
    if (name === '@/api/desktopDataDirectory') return directory
    if (name === '@/api/desktopUpdates') return api
    throw Error(name)
  }, module, module.exports)
  return { store: module.exports.useDesktopUpdatesStore(), calls }
}

test('automatic and manual checks share one download', async () => {
  const { store, calls } = harness('portable')
  await Promise.all([store.check(), store.check(true)])
  assert.deepEqual(calls, ['portable-download'])
  assert.equal(store.phase.value, 'ready')
})

test('a manual check joining an automatic check still reports an offline catalog', async () => {
  const { store } = harness('portable', { checkError: true })
  await Promise.all([store.check(), store.check(true)])
  assert.equal(store.visible.value, true)
  assert.equal(store.phase.value, 'error')
  assert.match(store.message.value, /暂时无法检查更新/)
})

test('portable updates use only the signed portable update route', async () => {
  const { store, calls } = harness('portable')
  await store.check(); await store.install()
  assert.deepEqual(calls, ['portable-download', 'portable-apply'])
})
test('a verified portable update survives app restart without downloading again', async () => {
  const { store, calls } = harness('portable', { ready: true })
  await store.check(); await store.install()
  assert.deepEqual(calls, ['portable-apply'])
})
test('installed updates drain and back up before running the installer', async () => {
  const { store, calls } = harness('legacy-installed')
  await store.check(); await store.install()
  assert.deepEqual(calls, ['installer-download', 'drain-backup', 'installer-install', 'restart'])
})
test('failed backup never runs the installer', async () => {
  const { store, calls } = harness('legacy-installed', { failDrain: true })
  await store.check(); await store.install()
  assert.deepEqual(calls, ['installer-download', 'drain-backup'])
  assert.equal(store.phase.value, 'error')
})

test('an update waiting for writers offers continued waiting and does not restart or redownload', async () => {
  const { store, calls } = harness('portable', { pending: true })
  await store.check(); await store.install()
  assert.equal(store.waitingForTasks.value, true)
  assert.equal(store.needsRestart.value, false)
  await store.install()
  assert.deepEqual(calls, ['portable-download', 'portable-apply', 'wait'])
  assert.equal(store.phase.value, 'error')
})

test('a rollback is explained before downloading the failed release again', async () => {
  const { store, calls } = harness('portable', { rolledBack: true })
  await store.check()
  assert.deepEqual(calls, [])
  assert.equal(store.phase.value, 'error')
  assert.match(store.message.value, /已恢复升级前/)
  assert.match(store.message.value, /照片校验失败/)
  assert.match(store.message.value, /backups/)
  await store.check(true)
  assert.deepEqual(calls, ['portable-download'])
})

test('a newer fixed release can download automatically after an earlier rollback', async () => {
  const { store, calls } = harness('portable', { rolledBack: true, latestVersion: '1.0.2' })
  await store.check()
  assert.deepEqual(calls, ['portable-download'])
  assert.equal(store.phase.value, 'ready')
})

test('an unavailable automatic update catalog does not look like a failed installation', async () => {
  const { store, calls } = harness('portable', { checkError: true })
  await store.check()
  assert.equal(store.visible.value, false)
  assert.deepEqual(calls, [])
  await store.check(true)
  assert.equal(store.visible.value, true)
  assert.match(store.message.value, /暂时无法检查更新/)
})

test('an offline catalog never hides the persisted rollback explanation', async () => {
  const { store } = harness('portable', { rolledBack: true, checkError: true })
  await store.check()
  assert.equal(store.visible.value, true)
  assert.match(store.message.value, /已恢复升级前/)
  assert.match(store.message.value, /backups/)
})
