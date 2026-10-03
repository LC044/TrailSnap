const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const vue = require('vue')
const pinia = require('pinia')

function loadSource(file, dependencies = {}) {
  const source = fs.readFileSync(path.resolve(__dirname, '../../src', file), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const module = { exports: {} }
  const requireDependency = name => {
    if (name === 'vue') return vue
    if (name === 'pinia') return pinia
    if (name in dependencies) return dependencies[name]
    throw new Error(`Unexpected dependency ${name}`)
  }
  vm.runInThisContext(`(function(require, module, exports) { ${code}\n})`, { filename: file })(requireDependency, module, module.exports)
  return module.exports
}
const dates = loadSource('utils/dailyFrame.ts')
const config = { initialized: true, today: '2026-10-03', timezone: 'Asia/Shanghai', locked: false, revision: 0, export: { available: true } }
function deferred() { let resolve; const promise = new Promise(done => { resolve = done }); return { promise, resolve } }

test('calendar date helpers keep leap days and year boundaries independent of local timezone', () => {
  assert.deepEqual(dates.monthRange('2024-02'), ['2024-02-01', '2024-02-29'])
  assert.deepEqual(dates.monthRange('2023-02'), ['2023-02-01', '2023-02-28'])
  assert.equal(dates.shiftMonth('2026-12', 1), '2027-01')
  assert.equal(dates.shiftMonth('2026-01', -1), '2025-12')
  assert.equal(dates.monthPadding('2026-10'), 3)
  assert.equal(dates.filmFilename('2026-10-01', 3, '生活 / 家人'), '生活 _ 家人_2026-10-01_3天.mp4')
})

test('calendar store deduplicates initialization and rejects stale month responses', async () => {
  const instance = pinia.createPinia(); pinia.setActivePinia(instance)
  let settingsCalls = 0
  const first = deferred(), second = deferred()
  const user = vue.reactive({ userInfo: { id: 'owner' } })
  const { useDailyFrameStore } = loadSource('stores/dailyFrameStore.ts', {
    '@/api/dailyFrame': { dailyFrameApi: { settings: async () => { settingsCalls++; return config }, calendar: start => start === '2026-09-01' ? first.promise : second.promise } },
    '@/stores/user': { useUserStore: () => user }, '@/utils/dailyFrame': dates,
  })
  const store = useDailyFrameStore()
  await Promise.all([store.initialize(), store.initialize()])
  assert.equal(settingsCalls, 1)
  const old = store.loadMonth('2026-09'), current = store.loadMonth('2026-10')
  second.resolve({ days: [{ day: '2026-10-03' }] }); await current
  first.resolve({ days: [{ day: '2026-09-03' }] }); await old
  assert.equal(store.calendar.days[0].day, '2026-10-03')
  user.userInfo.id = 'stranger'; await vue.nextTick()
  assert.equal(store.settings, null); assert.equal(store.calendar, null)
  pinia.disposePinia(instance)
})

test('an account change during initialization cannot publish the previous account settings', async () => {
  const instance = pinia.createPinia(); pinia.setActivePinia(instance)
  const initial = deferred(); let calls = 0
  const user = vue.reactive({ userInfo: { id: 'owner' } })
  const { useDailyFrameStore } = loadSource('stores/dailyFrameStore.ts', {
    '@/api/dailyFrame': { dailyFrameApi: { settings: () => ++calls === 1 ? initial.promise : Promise.resolve({ ...config, timezone: 'UTC' }) } },
    '@/stores/user': { useUserStore: () => user }, '@/utils/dailyFrame': dates,
  })
  const store = useDailyFrameStore()
  const ready = store.initialize()
  user.userInfo.id = 'stranger'; await vue.nextTick()
  initial.resolve(config); await ready
  assert.equal(store.settings.timezone, 'UTC')
  assert.equal(calls, 2)
  pinia.disposePinia(instance)
})
