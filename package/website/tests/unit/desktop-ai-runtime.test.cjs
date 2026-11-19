const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')

function harness(options = {}) {
  const source = fs.readFileSync(path.join(__dirname, '../../src/stores/desktopAIRuntime.ts'), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const calls = []
  const snapshot = { selected: 'cpu', runtime: { backend: 'cpu', deviceName: 'CPU' }, progress: null }
  let event
  const module = { exports: {} }
  vm.runInNewContext(`(function(require,module,exports){${code}\n})`)(name => {
    if (name === 'vue') return { ref: value => ({ value }), computed: read => ({ get value() { return read() } }) }
    if (name === 'pinia') return { defineStore: (_name, setup) => setup }
    if (name === '@tauri-apps/api/event') return { listen: async (_name, callback) => { event = callback; return () => {} } }
    if (name === '@/api/desktopAIRuntime') return {
      getAIRuntimeStatus: options.status || (async () => snapshot),
      downloadAIRuntime: options.download || (async backend => { calls.push(['download', backend]) }),
      selectAIRuntime: options.select || (async (backend, device) => { calls.push(['select', backend, device]) }),
    }
    throw Error(name)
  }, module, module.exports)
  return { store: module.exports.useDesktopAIRuntimeStore(), calls, snapshot, emit: payload => event({ payload }) }
}

test('downloading a runtime leaves the current device selected until explicit switch', async () => {
  const { store, calls, snapshot } = harness()
  await store.subscribe()
  await store.act('cuda', 'CPU', true)
  assert.deepEqual(calls, [['download', 'cuda']])
  assert.equal(store.status.value, snapshot)
  assert.equal(store.status.value.runtime.backend, 'cpu')
  await store.act('openvino', 'GPU.0')
  assert.deepEqual(calls[1], ['select', 'openvino', 'GPU.0'])
})

test('global progress remains visible after a settings page remount', async () => {
  const { store, emit } = harness()
  await store.subscribe()
  emit({ backend: 'cuda', phase: 'downloading', downloaded: 50, size: 100 })
  assert.equal(store.busy.value, true)
  assert.equal(store.progress.value.downloaded, 50)
  emit({ backend: 'cuda', phase: 'error', error: 'offline' })
  assert.equal(store.busy.value, false)
})

test('failed selection preserves an actionable error and refreshes the CPU fallback', async () => {
  const { store } = harness({ select: async () => { throw Error('设备不可用，已恢复 CPU') } })
  await store.act('cuda', 'CPU')
  assert.match(store.error.value, /已恢复 CPU/)
  assert.equal(store.status.value.runtime.backend, 'cpu')
  assert.equal(store.busy.value, false)
})

test('repeated download actions cannot start overlapping installs', async () => {
  let finish
  let downloads = 0
  const { store } = harness({ download: () => { downloads++; return new Promise(resolve => { finish = resolve }) } })
  const pending = store.act('cuda', 'CPU', true)
  await store.act('openvino', 'CPU', true)
  assert.equal(downloads, 1)
  finish()
  await pending
  assert.equal(store.busy.value, false)
})
