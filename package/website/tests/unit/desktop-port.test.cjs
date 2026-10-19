const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')

function harness(options = {}) {
  const source = fs.readFileSync(path.join(__dirname, '../../src/stores/desktopPort.ts'), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const calls = []
  const module = { exports: {} }
  const api = {
    getDesktopPortConfig: async () => ({ port: 2688, fixed: true, activePort: null, error: 'denied' }),
    setDesktopPort: async port => { calls.push(['save', port]); if (options.saveError) throw Error(options.saveError) },
    restartForDesktopPort: async () => { calls.push(['drain-restart']); if (options.restartError) throw Error(options.restartError) },
    isDesktopDrainPending: cause => String(cause).includes('后台任务仍在结束'),
    waitForDesktopDrain: async () => { calls.push(['wait']); if (options.waitError) throw Error(options.waitError) },
    restartDesktop: async () => calls.push(['restart']),
  }
  vm.runInNewContext(`(function(require,module,exports){${code}\n})`)(name => {
    if (name === 'vue') return { ref: value => ({ value }) }
    if (name === 'pinia') return { defineStore: (_name, setup) => setup }
    return api
  }, module, module.exports)
  return { store: module.exports.useDesktopPortStore(), calls }
}

test('startup recovery loads settings and switches to automatic without HTTP', async () => {
  const { store, calls } = harness()
  await store.load()
  assert.equal(store.config.value.error, 'denied')
  store.fixed.value = false
  await store.saveAndRestart()
  assert.deepEqual(calls, [['save', null], ['drain-restart']])
})

test('custom ports reject invalid values before native mutation', async () => {
  for (const value of ['', '0', '-1', '65536', '1.5', '2e3', 'abc']) {
    const { store, calls } = harness()
    store.fixed.value = true
    store.port.value = value
    await store.saveAndRestart()
    assert.equal(calls.length, 0)
    assert.match(store.error.value, /1–65535/)
  }
})

test('bind validation failure preserves editable form and never restarts', async () => {
  const { store, calls } = harness({ saveError: '端口被占用' })
  store.fixed.value = true
  store.port.value = '65535'
  await store.saveAndRestart()
  assert.deepEqual(calls, [['save', 65535]])
  assert.equal(store.needsRestart.value, false)
  assert.match(store.error.value, /占用/)
})

test('pending drain is resumed before restart without saving configuration twice', async () => {
  const { store, calls } = harness({ restartError: '后台任务仍在结束' })
  await store.saveAndRestart()
  assert.equal(store.waiting.value, true)
  await store.saveAndRestart()
  assert.deepEqual(calls, [['save', null], ['drain-restart'], ['wait'], ['restart']])
})

test('failed drain wait never restarts or unlocks the configuration', async () => {
  const { store, calls } = harness({ restartError: '后台任务仍在结束', waitError: '后台任务仍在结束' })
  await store.saveAndRestart()
  await store.saveAndRestart()
  assert.deepEqual(calls, [['save', null], ['drain-restart'], ['wait']])
  assert.equal(store.needsRestart.value, true)
  assert.equal(store.waiting.value, true)
})
