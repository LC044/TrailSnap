const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const vue = require('vue')
const pinia = require('pinia')

function load(filename, dependencies = {}) {
  const source = fs.readFileSync(path.resolve(__dirname, '../../src', filename), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const module = { exports: {} }
  vm.runInThisContext(`(function(require,module,exports){${code}\n})`, { filename })(name => {
    if (name === 'vue') return vue
    if (name === 'pinia') return pinia
    if (name in dependencies) return dependencies[name]
    throw Error(`Unexpected import: ${name}`)
  }, module, module.exports)
  return module.exports
}
const renderer = vue.createRenderer({ insert() {}, remove() {}, createElement: () => ({}), createText: () => ({}), createComment: () => ({}), setText() {}, setElementText() {}, parentNode: () => null, nextSibling: () => null, patchProp() {} })
function mount(setup) { let value; const app = renderer.createApp({ setup() { value = setup(); return () => null } }); app.mount({}); return { value, unmount: () => app.unmount() } }
const flush = async () => { await Promise.resolve(); await vue.nextTick() }

test('same ID in different ticket types has independent identity and capabilities', () => {
  const { ticketKey, ticketKinds, ticketLabel } = load('types/ticketWallet.ts')
  assert.notEqual(ticketKey({ type: 'train', id: 'x' }), ticketKey({ type: 'flight', id: 'x' }))
  assert.equal(ticketKinds.train.paper, true)
  for (const type of ['attraction', 'concert', 'movie']) { assert.equal(ticketKinds[type].transport, false); assert.equal(ticketKinds[type].supported, false) }
  assert.equal(ticketLabel('unknown'), '票据')
})

test('wallet pages through all summaries and retains old data after refresh failure', async () => {
  pinia.setActivePinia(pinia.createPinia())
  let calls = 0, fail = false
  const { useTicketWalletStore } = load('stores/ticketWalletStore.ts', { '@/api/ticketWallet': { ticketWalletApi: { list: async ({ skip }) => { calls++; if (fail) throw Error('offline'); return { items: [{ key: String(skip) }], total: 2 } } } } })
  const store = useTicketWalletStore()
  await store.fetch()
  assert.equal(calls, 2); assert.equal(store.items.length, 2)
  fail = true; await store.fetch()
  assert.equal(store.items.length, 2); assert.ok(store.error); assert.equal(store.loading, false)
})

test('mutation waits for an older fetch and then requests fresh relationship data', async () => {
  pinia.setActivePinia(pinia.createPinia())
  let resolve, calls = 0
  const { useTicketWalletStore } = load('stores/ticketWalletStore.ts', { '@/api/ticketWallet': { ticketWalletApi: { list: async () => { calls++; return calls === 1 ? new Promise(done => { resolve = done }) : { items: [{ key: 'fresh' }], total: 1 } } } } })
  const store = useTicketWalletStore(), fetch = store.fetch(), mutation = store.changed()
  resolve({ items: [{ key: 'old' }], total: 1 })
  await Promise.all([fetch, mutation])
  assert.equal(calls, 2); assert.equal(store.items[0].key, 'fresh')
})

test('resetting on account change rejects late responses from the old account', async () => {
  pinia.setActivePinia(pinia.createPinia())
  let resolve
  const { useTicketWalletStore } = load('stores/ticketWalletStore.ts', { '@/api/ticketWallet': { ticketWalletApi: { list: () => new Promise(done => { resolve = done }) } } })
  const store = useTicketWalletStore(), request = store.fetch()
  store.reset()
  resolve({ items: [{ key: 'private-old-user-data' }], total: 1 })
  await request
  assert.equal(store.items.length, 0); assert.equal(store.loading, false)
})

test('cancelled unsaved overlay remains the top overlay on repeated back', async () => {
  const { useOverlayStack, closeTopOverlay, isTopOverlay } = load('composables/useOverlayStack.ts')
  const open = vue.ref(true); let attempts = 0
  const closer = () => { attempts++; if (attempts === 2) open.value = false }
  const component = mount(() => useOverlayStack(open, closer))
  assert.equal(isTopOverlay(closer), true)
  await closeTopOverlay(); assert.equal(open.value, true); assert.equal(isTopOverlay(closer), true)
  await closeTopOverlay(); assert.equal(open.value, false); assert.equal(await closeTopOverlay(), false)
  component.unmount()
})

test('nested dialog scroll locks restore preexisting overflow only after the last close', async () => {
  const body = { style: { overflow: 'auto' } }, main = { style: { overflow: 'scroll' } }
  const original = global.document
  global.document = { body, querySelectorAll: () => [main] }
  const { useModalScrollLock } = load('composables/useModalScrollLock.ts')
  const parent = vue.ref(true), child = vue.ref(true)
  const first = mount(() => useModalScrollLock(parent)), second = mount(() => useModalScrollLock(child))
  assert.equal(main.style.overflow, 'hidden')
  child.value = false; await flush(); assert.equal(main.style.overflow, 'hidden')
  parent.value = false; await flush(); assert.equal(main.style.overflow, 'scroll'); assert.equal(body.style.overflow, 'auto')
  first.unmount(); second.unmount(); global.document = original
})

test('browser back closes only the top dialog and re-arms history after cancelling dirty exit', async () => {
  const original = global.window
  const entries = [{ state: {}, url: '/ticket' }]
  let cursor = 0, pop
  global.window = {
    location: { href: '/ticket' },
    addEventListener(name, callback) { if (name === 'popstate') pop = callback },
    history: {
      get state() { return entries[cursor].state },
      pushState(state, _, url) { entries.splice(++cursor); entries.push({ state, url }) },
      async back() { if (!cursor) return; cursor--; global.window.location.href = entries[cursor].url; await pop() },
    },
  }
  const parent = vue.ref(true), child = vue.ref(true)
  let cancel = false, attempts = 0
  const { useDialogHistory } = load('composables/useDialogHistory.ts', {
    './useOverlayStack': { closeTopOverlay: async () => { attempts++; if (cancel) return true; if (child.value) child.value = false; else parent.value = false; return true } },
  })
  const first = mount(() => useDialogHistory(parent, () => true))
  const second = mount(() => useDialogHistory(child, () => true))
  try {
    await flush(); assert.equal(cursor, 1)
    await global.window.history.back(); await flush()
    assert.equal(child.value, false); assert.equal(parent.value, true); assert.equal(cursor, 1)
    cancel = true
    await global.window.history.back(); await flush()
    assert.equal(parent.value, true); assert.equal(cursor, 1)
    cancel = false
    await global.window.history.back(); await flush()
    assert.equal(parent.value, false); assert.equal(cursor, 0); assert.equal(attempts, 3)
  } finally {
    first.unmount(); second.unmount(); await flush(); global.window = original
  }
})
