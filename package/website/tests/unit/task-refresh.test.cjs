const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')

function load(file, context = {}, dependencies = {}) {
  const source = fs.readFileSync(path.resolve(__dirname, '../../src', file), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const module = { exports: {} }
  vm.runInNewContext(`(function(require,module,exports){${code}\n})`, context)(name => {
    assert.ok(name in dependencies, `Unexpected dependency: ${name}`)
    return dependencies[name]
  }, module, module.exports)
  return module.exports
}

function harness() {
  let now = 0, sequence = 0
  const timers = new Map()
  const helpers = load('utils/taskRefresh.ts', {
    Date: { now: () => now },
    setTimeout(fn, delay) { const id = ++sequence; timers.set(id, { fn, at: now + delay }); return id },
    clearTimeout(id) { timers.delete(id) },
  })
  return { ...helpers, advance(to) {
    while (true) {
      const next = [...timers].filter(([, timer]) => timer.at <= to).sort((a, b) => a[1].at - b[1].at)[0]
      if (!next) break
      now = next[1].at
      timers.delete(next[0])
      next[1].fn()
    }
    now = to
  }, now: () => now, timers }
}

test('continuous events refresh every four seconds and the final pending event flushes', () => {
  const h = harness(), calls = []
  const refresh = h.createTaskRefresh(() => calls.push(h.now()))
  for (let time = 0; time <= 10000; time += 100) { h.advance(time); refresh.schedule() }
  h.advance(12000)
  assert.deepEqual(calls, [0, 4000, 8000, 12000])
  refresh.schedule()
  refresh.cancel()
  h.advance(20000)
  assert.equal(calls.length, 4)
  assert.equal(h.timers.size, 0)
})

test('summary requests share in-flight work, expire, isolate accounts and retry failures', async () => {
  const h = harness(), cache = h.createTaskStatusCache()
  let calls = 0, resolve
  const loader = () => { calls++; return new Promise(done => { resolve = done }) }
  const first = cache('server:user-a', loader)
  await Promise.resolve()
  h.advance(5000)
  assert.equal(cache('server:user-a', loader), first)
  assert.equal(calls, 1)
  const other = cache('server:user-b', async () => ['b'])
  resolve(['a'])
  await first
  assert.deepEqual(await other, ['b'])
  assert.equal(cache('server:user-b', loader), other)
  h.advance(9000)
  await assert.rejects(cache('server:user-b', async () => { throw Error('offline') }))
  assert.deepEqual(await cache('server:user-b', async () => ['recovered']), ['recovered'])
})

test('task revision refreshes repeated timestamps and bulk creation without IDs, excluding notifications', () => {
  const store = load('stores/notificationStore.ts', { localStorage: { getItem: () => null } }, {
    pinia: { defineStore: (_name, setup) => setup },
    vue: { ref: value => ({ value }), computed: fn => ({ get value() { return fn() } }), watch() {} },
    '@/api/notification': { notificationsApi: {} },
  }).useNotificationStore()
  const sameTask = { id: 'a', status: 'processing', updated_at: 'same timestamp' }
  store.handleEvent('task.updated', sameTask)
  store.handleEvent('task.updated', sameTask)
  store.handleEvent('task.created', { type: 'OCR' })
  store.handleEvent('hello', {})
  assert.equal(store.taskRevision.value, 4)
  store.handleEvent('notification.read', { id: 'n' })
  assert.equal(store.taskRevision.value, 4)
})

for (const file of ['useTaskSSE', 'useNotificationSSE']) {
  test(`${file} dispatches batch task states and accepts legacy single events`, () => {
    const sources = [], cleanups = [], received = []
    class EventSource {
      constructor() { this.handlers = {}; sources.push(this) }
      addEventListener(event, fn) { this.handlers[event] = fn }
      close() {}
    }
    const vue = {
      ref: value => ({ value }), onUnmounted: fn => cleanups.push(fn),
      watch: (get, fn) => fn(get()),
    }
    const api = { buildTaskEventsUrl: () => '/tasks', tasksApi: {} }
    const exports = load(`composables/${file}.ts`, { EventSource, window: {} }, {
      vue, '@/api/tasks': api,
      '@/api/notification': { buildNotificationsEventsUrl: () => '/notifications', notificationsApi: {} },
    })
    exports[file]({ token: { value: 'token' }, onEvent: (event, data) => received.push([event, data.id]) })
    sources[0].handlers['task.batch']({ data: JSON.stringify({ events: [
      { event: 'task.updated', data: { id: 'a', status: 'completed' } },
      { event: 'task.updated', data: { id: 'b', status: 'failed' } },
    ] }) })
    sources[0].handlers['task.updated']({ type: 'task.updated', data: JSON.stringify({ id: 'c' }) })
    assert.deepEqual(received, [['task.updated', 'a'], ['task.updated', 'b'], ['task.updated', 'c']])
    cleanups.forEach(fn => fn())
  })
}
