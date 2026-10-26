const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')

function harness({ states = () => [], scans = () => [], deferred = '', pauseFails = false, getFails = false } = {}) {
  let now = 0, polls = 0
  const posts = []
  const source = fs.readFileSync(path.resolve(__dirname, '../../e2e-system/helpers/task-poller.ts'), 'utf8')
  const context = {
    exports: {}, process: { env: { TS_E2E_PREP_DEFERRED_TYPES: deferred } },
    console: { log() {} },
    Date: class extends Date { static now() { return now } },
    setTimeout(fn, ms) { now += ms; fn() },
  }
  vm.createContext(context)
  vm.runInContext(ts.transpileModule(source, { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
  } }).outputText, context)
  const response = data => ({ ok: () => true, json: async () => ({ code: 0, data }) })
  const request = {
    async get(url) {
      if (getFails) throw new Error('connection reset')
      if (url.endsWith('grouped-status')) return response(states(polls++))
      return response(scans(polls))
    },
    async post(url) {
      posts.push(url)
      return { ok: () => !pauseFails, status: () => 500 }
    },
  }
  return { ...context.exports, request, posts, polls: () => polls }
}

const group = (pending = 0, failed = 0, category = 'PROCESS_BASIC') => ({ category, pending, failed })
const wait = h => h.waitForTasksToSettle(h.request, 'test-token', { timeoutMs: 20, intervalMs: 1 })

test('unchanged pending counts never count as readiness', async () => {
  const h = harness({ states: () => [group(2)] })
  await assert.rejects(wait(h), /准备超时/)
  assert.equal(h.posts.length, 0)
})

test('empty processing queue cannot finish while SCAN_FOLDER is still producing children', async () => {
  const h = harness({ states: () => [group()], scans: poll => poll < 4 ? [{ id: 'scan', status: 'processing' }] : [] })
  await wait(h)
  assert.ok(h.polls() >= 7)
  assert.equal(h.posts.length, 1)
})

test('deleted successful scan rows and drained child queues finish without a quiet timeout', async () => {
  const h = harness({ states: () => [group()] })
  await wait(h)
  assert.equal(h.polls(), 3)
})

test('failed prerequisite and failed scan abort rather than freeze and pass', async () => {
  const failedChild = harness({ states: () => [group(0, 1)] })
  await assert.rejects(wait(failedChild), /必需照片处理失败/)
  const failedScan = harness({ states: () => [group()], scans: () => [{ id: 'scan', status: 'failed', error: 'disk error' }] })
  await assert.rejects(wait(failedScan), /扫描未成功/)
})

test('explicitly deferred LLM jobs do not hide pending local AI jobs', async () => {
  const h = harness({ deferred: 'VISUAL_DESCRIPTION', states: poll => [group(poll < 4 ? 2 : 0), group(100, 0, 'VISUAL_DESCRIPTION')] })
  await wait(h)
  assert.equal(h.polls(), 7)
  assert.equal(h.posts.length, 2)
})

test('network errors and empty grouped responses cannot become a successful preparation', async () => {
  await assert.rejects(wait(harness({ getFails: true })), /connection reset/)
  await assert.rejects(wait(harness()), /处理分类为空/)
})

test('failed freeze is surfaced before tests can mutate fixtures', async () => {
  const h = harness({ states: () => [group()], pauseFails: true })
  await assert.rejects(wait(h), /暂停 PROCESS_BASIC 失败/)
})

test('optional categories are paused before prerequisites resume, and request failure is fatal', async () => {
  const h = harness({ deferred: 'VISUAL_DESCRIPTION', states: () => [group(), group(0, 0, 'VISUAL_DESCRIPTION')] })
  await h.configurePreparationTasks(h.request, 'test-token', '/tasks/')
  assert.deepEqual(h.posts, ['/tasks/categories/VISUAL_DESCRIPTION/pause', '/tasks/categories/PROCESS_BASIC/resume'])
  const failing = harness({ states: () => [group()], pauseFails: true })
  await assert.rejects(failing.configurePreparationTasks(failing.request, 'test-token', '/tasks/'), /resume PROCESS_BASIC 失败/)
})
