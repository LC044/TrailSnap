const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')

const apiNames = ['Map', 'TileLayer', 'Marker', 'Label', 'Polyline', 'LngLat', 'Point', 'Geocoder', 'LocalSearch']
const completeSdk = () => Object.fromEntries(apiNames.map(name => [name, function () {}]))
const flush = async () => { for (let i = 0; i < 8; i++) await Promise.resolve() }

function fixture() {
  const entries = new Map([
    ['TDT_version', 'trailsnap2'], ['TDT_components0', 'old-port script'], ['TDT_components1', 'old-token script'],
    ['TDT_style0', 'old-port CSS'], ['trailsnap:theme', 'dark'],
  ])
  const scripts = []
  const timers = new Map()
  let timerId = 0
  const window = {
    localStorage: { get length() { return entries.size }, key: index => [...entries.keys()][index], removeItem: key => entries.delete(key) },
    setTimeout: (callback, delay) => { timers.set(++timerId, { callback, delay }); return timerId },
    clearTimeout: id => timers.delete(id),
  }
  const document = {
    createElement: () => ({ remove() { this.removed = true } }),
    head: { appendChild: script => scripts.push(script) },
  }
  const source = fs.readFileSync(path.resolve(__dirname, '../../src/utils/mapLoader.ts'), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  const module = { exports: {} }
  const dependencies = {
    '@/api/settings': { settingsApi: { getMapRuntime: async () => ({ provider: 'tianditu', access_token: 'new-token' }) } },
    '@/config/server': { toServerUrl: value => `http://127.0.0.1:53373${value}` },
  }
  vm.runInNewContext(code, { window, document, module, exports: module.exports, require: name => dependencies[name] })
  function fire(delay) {
    const entry = [...timers].find(([, timer]) => timer.delay === delay)
    assert.ok(entry, `No ${delay}ms timer`)
    timers.delete(entry[0]); entry[1].callback()
  }
  return { loader: module.exports, window, scripts, entries, timers, fire }
}

test('map loader discards stale SDK caches and waits for overlays and service modules', async () => {
  const f = fixture()
  let resolved = false
  const pending = f.loader.loadMapScript().then(token => { resolved = true; return token })
  await flush()
  assert.equal(f.scripts.length, 1)
  assert.deepEqual([...f.entries], [['trailsnap:theme', 'dark']])
  assert.match(f.scripts[0].src, /53373\/api\/system\/map-proxy\/new-token\//)
  f.window.T = { Map: function () {} }
  f.scripts[0].onload()
  await flush()
  assert.equal(resolved, false)
  f.window.T = completeSdk()
  f.fire(100)
  assert.equal(await pending, 'new-token')
  assert.equal(f.timers.size, 0)
})

test('partial SDK initialization times out and a retry loads external resources again', async () => {
  const f = fixture()
  const failed = assert.rejects(f.loader.loadMapScript(), error => error.code === 'SCRIPT_LOAD_TIMEOUT')
  await flush()
  f.window.T = { Map: function () {} }
  f.scripts[0].onload()
  f.fire(20000)
  await failed
  assert.equal(f.scripts[0].removed, true)
  assert.equal(f.timers.size, 0)
  const retry = f.loader.loadMapScript()
  await flush()
  assert.equal(f.scripts.length, 2)
  f.window.T = completeSdk()
  f.scripts[1].onload()
  assert.equal(await retry, 'new-token')
})

test('an already complete SDK is reused without touching its live resources', async () => {
  const f = fixture()
  f.window.T = completeSdk()
  assert.equal(await f.loader.loadMapScript(), 'new-token')
  assert.equal(f.scripts.length, 0)
  assert.equal(f.entries.get('trailsnap:theme'), 'dark')
})
