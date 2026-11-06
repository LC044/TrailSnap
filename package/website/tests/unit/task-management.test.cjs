const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const { ref, computed } = require('vue')
const { parse } = require('vue/compiler-sfc')

const read = file => fs.readFileSync(path.resolve(__dirname, '../../src', file), 'utf8')
const result = { exports: {} }
vm.runInNewContext(ts.transpileModule(read('utils/taskPresentation.ts'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText, { module: result, exports: result.exports })
const presentation = result.exports
const { getTaskState, filterTaskGroups, summarizeTaskGroups } = presentation
const group = (category, values = {}) => ({
  category, task_name: category, pending: 0, failed: 0, completed: 0,
  status: 'active', priority: 1, description: '测试任务', ...values,
})

test('an empty queue is idle, not proof that every photo is complete', () => {
  assert.equal(getTaskState(group('empty')), 'idle')
  assert.equal(presentation.taskStateLabels.idle, '无待处理')
  assert.equal(getTaskState(group('error', { failed: 4 })), 'failed')
})

test('paused, model waiting and pending groups retain distinct states', () => {
  assert.equal(getTaskState(group('paused', { pending: 5, failed: 2, status: 'paused' })), 'paused')
  assert.equal(getTaskState(group('waiting', { pending: 5, waiting_reason: '等待模型下载' })), 'waiting')
  assert.equal(getTaskState(group('queued', { pending: 5 })), 'pending')
  assert.equal(getTaskState(group('old-warning', { waiting_reason: '旧等待原因' })), 'idle')
})

test('summary includes paused backlog and keeps job counts separate from category counts', () => {
  const summary = summarizeTaskGroups([
    group('queued', { pending: 1200 }),
    group('paused', { pending: 4, failed: 3, status: 'paused' }),
    group('error', { failed: 2 }),
  ])
  assert.deepEqual({ ...summary }, { pending: 1204, failed: 5, paused: 1 })
})

test('filters overlap intentionally: a paused failed group remains discoverable in each filter', () => {
  const tasks = [group('idle'), group('paused', { pending: 2, failed: 1, status: 'paused' })]
  for (const filter of ['pending', 'failed', 'paused']) {
    assert.equal(filterTaskGroups(tasks, filter).length, 1)
    assert.equal(filterTaskGroups(tasks, filter)[0].category, 'paused')
  }
  assert.equal(filterTaskGroups(tasks, 'all').length, 2)
  assert.equal(filterTaskGroups([], 'failed').length, 0)
})

test('attention sorting surfaces failures and backlog while preserving priority within a state', () => {
  const tasks = [
    group('idle', { priority: 99 }), group('pending-low', { pending: 1 }),
    group('pending-high', { pending: 1, priority: 9 }), group('error', { failed: 1 }),
    group('paused', { pending: 2, status: 'paused' }),
  ]
  assert.equal(filterTaskGroups(tasks, 'all').map(task => task.category).join(','),
    'error,pending-high,pending-low,paused,idle')
  assert.equal(tasks[0].category, 'idle')
})

function pageHarness() {
  let rows = [], fail = false
  const events = [], calls = []
  const script = parse(read('views/settings/TaskManagement.vue')).descriptor.scriptSetup.content.replace(/^import .*$/gm, '')
  const context = {
    ref, computed, watch() {}, onMounted() {}, onUnmounted() {}, useMediaQuery: () => ref(false),
    ...presentation, AlertCircle: {}, CheckCircle2: {}, Circle: {}, Clock3: {}, PauseCircle: {},
    useNotificationStore: () => ({ handleEvent: (...args) => events.push(args) }),
    tasksApi: {
      getGroupedStatus: async () => { if (fail) throw Error('offline'); return rows },
      getGlobalStatus: async () => ({ fast_mode: 'True' }),
      pauseCategory: async category => calls.push(['pause', category]),
      resumeCategory: async category => calls.push(['resume', category]),
    },
    ElMessage: { success() {}, error() {} }, ElMessageBox: {},
    console: { error() {} }, window: {},
  }
  vm.createContext(context)
  vm.runInContext(ts.transpileModule(`${script}\nglobalThis.page = {
    groupedTasks, visibleTasks, summary, taskFilter, fetchTasks, loadFailed, loading,
    handleCategoryCommand, showFailedTasks, failedTasksVisible, failedCategory, failedCategoryTitle, fastMode, formatCategory
  }`, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText, context)
  return {
    ...context.page, calls, events,
    async load(next, shouldFail = false) { rows = next; fail = shouldFail; await context.page.fetchTasks() },
  }
}

test('page retains its filter and cached rows on request failure, then recovers on refresh', async () => {
  const page = pageHarness()
  await page.load([group('error', { failed: 2 }), group('idle')])
  page.taskFilter.value = 'failed'
  await page.load([], true)
  assert.equal(page.loadFailed.value, true)
  assert.equal(page.loading.value, false)
  assert.equal(page.visibleTasks.value.length, 1)
  await page.load([group('idle')])
  assert.equal(page.loadFailed.value, false)
  assert.equal(page.taskFilter.value, 'failed')
  assert.equal(page.visibleTasks.value.length, 0)
  assert.equal(page.fastMode.value, true)
})

test('pause, resume and failure details still target the original task category', async () => {
  const page = pageHarness()
  await page.load([group('OCR', { task_name: '文字识别', failed: 3 })])
  await page.handleCategoryCommand('OCR', 'pause')
  await page.handleCategoryCommand('OCR', 'resume')
  assert.deepEqual(page.calls, [['pause', 'OCR'], ['resume', 'OCR']])
  assert.equal(page.events[0][1].status, 'paused')
  page.showFailedTasks('OCR')
  assert.equal(page.failedTasksVisible.value, true)
  assert.equal(page.failedCategory.value, 'OCR')
  assert.equal(page.failedCategoryTitle.value, '文字识别')
  assert.equal(page.formatCategory('OCR'), '文字识别')
})
