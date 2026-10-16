const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const { createPinia, setActivePinia } = require('pinia')
const { createRouter, createMemoryHistory, isNavigationFailure } = require('vue-router')

function load(relative, overrides = {}, globals = {}) {
  const source = fs.readFileSync(path.resolve(__dirname, '../../src', relative), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  const module = { exports: {} }
  vm.runInNewContext(`(function(require,module,exports){${code}\n})`, globals)(
    name => overrides[name] || require(name), module, module.exports)
  return module.exports
}

function deferred() {
  let resolve, reject
  const promise = new Promise((a, b) => { resolve = a; reject = b })
  return { promise, resolve, reject }
}
const page = { render: () => null }

async function fixture(routes) {
  setActivePinia(createPinia())
  const stores = load('stores/navigation.ts')
  const { installNavigationFeedback } = load('router/navigationFeedback.ts', { '@/stores/navigation': stores })
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: page }, ...routes] })
  installNavigationFeedback(router)
  await router.push('/')
  return { router, state: stores.useNavigationStore() }
}

test('route failure clears loading and retry preserves query and hash', async () => {
  let attempts = 0
  const { router, state } = await fixture([{ path: '/photos', component: async () => {
    if (++attempts === 1) throw Error('Failed to fetch dynamically imported module')
    return page
  } }])
  await assert.rejects(router.push('/photos?year=2026#today'))
  assert.equal(state.pending, null)
  assert.equal(state.failed.fullPath, '/photos?year=2026#today')
  await router.push(state.failed.fullPath)
  assert.equal(attempts, 2)
  assert.equal(state.failed, null)
  assert.equal(state.pending, null)
  assert.equal(router.currentRoute.value.fullPath, '/photos?year=2026#today')
})

test('older cancelled navigation cannot finish a newer pending navigation', async () => {
  const a = deferred(), b = deferred(), enteredA = deferred(), enteredB = deferred()
  const { router, state } = await fixture([
    { path: '/a', component: () => { enteredA.resolve(); return a.promise } },
    { path: '/b', component: () => { enteredB.resolve(); return b.promise } },
  ])
  const first = router.push('/a'); await enteredA.promise
  const second = router.push('/b'); await enteredB.promise
  a.resolve(page)
  assert.ok(isNavigationFailure(await first))
  assert.equal(state.pending.path, '/b')
  b.resolve(page); await second
  assert.equal(state.pending, null)
})

test('stale load errors do not replace the current navigation with a failure', async () => {
  const a = deferred(), entered = deferred()
  const { router, state } = await fixture([
    { path: '/a', component: () => { entered.resolve(); return a.promise } },
    { path: '/b', component: page },
  ])
  const old = router.push('/a'); const caught = assert.rejects(old)
  await entered.promise; await router.push('/b')
  a.reject(Error('offline')); await caught
  assert.equal(state.failed, null)
  assert.equal(state.pending, null)
})

test('guard aborts, redirects and duplicate links leave no loading indicator', async () => {
  const { router, state } = await fixture([
    { path: '/abort', component: page }, { path: '/redirect', component: page },
  ])
  router.beforeEach(to => to.path === '/abort' ? false : to.path === '/redirect' ? '/' : true)
  await router.push('/abort'); assert.equal(state.pending, null)
  await router.push('/redirect'); assert.equal(state.pending, null)
  await router.push('/'); assert.equal(state.pending, null)
})

function preloadFixture() {
  const timers = [], idles = [], calls = []
  const navigator = { onLine: true, connection: { effectiveType: '4g', downlink: 8, rtt: 50 } }
  const document = { visibilityState: 'visible', readyState: 'complete' }
  const window = {
    requestIdleCallback: fn => { idles.push(fn); return idles.length }, cancelIdleCallback: () => {},
    addEventListener: () => {}, removeEventListener: () => {},
  }
  const api = load('router/preload.ts', {}, { navigator, document, window,
    setTimeout: fn => { timers.push(fn); return timers.length }, clearTimeout: () => {} })
  return { api, navigator, document, calls, timer: () => timers.shift()?.(), idle: () => idles.shift()?.(), idles }
}

test('preloads require a known good connection and reject data saver, offline and slow networks', () => {
  const { api, navigator } = preloadFixture()
  assert.equal(api.canPreloadPages(), true)
  for (const connection of [undefined, {}, { effectiveType: '3g' }, { effectiveType: '4g', saveData: true },
    { effectiveType: '4g', downlink: 1 }, { effectiveType: '4g', rtt: 500 }]) {
    navigator.connection = connection
    assert.equal(api.canPreloadPages(), false)
  }
  navigator.connection = { type: 'wifi' }; assert.equal(api.canPreloadPages(), true)
  navigator.onLine = false; assert.equal(api.canPreloadPages(), false)
})

test('preloads run one at a time and recheck navigation, visibility and network at idle time', async () => {
  const f = preloadFixture(), first = deferred()
  let ready = true
  const stop = f.api.schedulePagePreloads([
    () => { f.calls.push('first'); return first.promise },
    async () => { f.calls.push('second'); throw Error('offline') },
    async () => { f.calls.push('third') },
  ], () => ready)
  f.timer(); const running = f.idle()
  assert.deepEqual(f.calls, ['first'])
  f.timer(); assert.equal(f.idles.length, 0)
  first.resolve(); await running
  ready = false; f.timer(); assert.equal(f.idles.length, 0)
  ready = true; f.timer(); f.document.visibilityState = 'hidden'; await f.idle()
  assert.deepEqual(f.calls, ['first'])
  f.document.visibilityState = 'visible'; f.timer(); f.navigator.connection.saveData = true; await f.idle()
  assert.deepEqual(f.calls, ['first'])
  f.navigator.connection.saveData = false; f.timer(); await f.idle()
  assert.deepEqual(f.calls, ['first', 'second'])
  stop(); f.timer(); await f.idle()
  assert.deepEqual(f.calls, ['first', 'second'])
})

test('PWA shell follows static imports and excludes lazy routes and their CSS', async () => {
  const { collectShellAssets } = await import('../../scripts/pwa-precache.mjs')
  const chunk = (fileName, imports = [], css = [], isEntry = false) => ({
    type: 'chunk', fileName, imports, isEntry, viteMetadata: { importedCss: new Set(css) },
  })
  const assets = collectShellAssets({
    'main.js': { ...chunk('main.js', ['vue.js'], ['main.css'], true), dynamicImports: ['photos.js'] },
    'vue.js': chunk('vue.js'), 'photos.js': chunk('photos.js', [], ['photos.css']),
    'main.css': { type: 'asset' }, 'photos.css': { type: 'asset' },
  })
  assert.deepEqual(assets.sort(), ['/main.css', '/main.js', '/vue.js'])
})
