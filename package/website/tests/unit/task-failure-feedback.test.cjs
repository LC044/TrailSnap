const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const { ref, computed } = require('vue')

function harness() {
  const source = fs.readFileSync(path.resolve(__dirname, '../../src/components/SidebarTaskManager.vue'), 'utf8')
  const script = source.split('<script setup lang="ts">')[1].split('</script>')[0].replace(/^import .*$/gm, '')
  let rows = [], cleanup
  const success = [], warnings = [], routes = [], timers = new Map()
  const context = { ref, computed, watch() {}, onMounted() {}, onUnmounted(fn) { cleanup = fn },
    defineProps: () => ({ isCollapsed: true }), useRouter: () => ({ push: route => routes.push(route) }),
    useNotificationStore: () => ({}), createTaskRefresh: fn => ({ schedule: fn, cancel() {} }),
    tasksApi: { getGroupedStatus: async () => rows },
    ElMessage: { success: text => success.push(text), warning: text => warnings.push(text) },
    window: { setTimeout(fn) { timers.set(1, fn); return 1 }, clearTimeout(id) { timers.delete(id) }, clearInterval() {} } }
  vm.createContext(context)
  vm.runInContext(ts.transpileModule(script + '\nglobalThis.page = { compactCount, formatCount, detailCategories, fetchStatus, shouldShow, showSuccess, expanded, totalFailed, toggleExpand };', {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText, context)
  return { ...context.page, success, warnings, routes, timers, cleanup: () => cleanup(),
    async update(next) { rows = next; await context.page.fetchStatus() } }
}

const group = (pending, failed = 0, status = 'active') => ({ category: 'RECOGNIZE_TICKET', task_name: '车票识别', pending, failed, status })

test('existing failures remain visible on initial load and collapsed header opens task details', async () => {
  const page = harness()
  await page.update([group(0, 3)])
  assert.equal(page.shouldShow.value, true)
  assert.equal(page.totalFailed.value, 3)
  assert.equal(page.expanded.value, false)
  page.toggleExpand()
  assert.equal(page.routes[0].query.tab, 'tasks')
  assert.equal(page.success.length, 0)
  await page.update([group(0, 3)])
  assert.equal(page.warnings.length, 1)
})

test('drained queue with failed jobs never produces a success toast', async () => {
  const page = harness()
  await page.update([group(4)])
  await page.update([group(0, 4)])
  assert.equal(page.success.length, 0)
  assert.equal(page.showSuccess.value, false)
  assert.equal(page.shouldShow.value, true)
  assert.equal(page.timers.size, 0)
})

test('paused backlog is not reported as completed', async () => {
  const page = harness()
  await page.update([group(4)])
  await page.update([group(4, 0, 'paused')])
  assert.equal(page.success.length, 0)
})

test('successful completion is temporary and unmount releases its timer', async () => {
  const page = harness()
  await page.update([group(4)])
  await page.update([group(0)])
  assert.equal(page.success.length, 1)
  assert.equal(page.shouldShow.value, true)
  assert.equal(page.timers.size, 1)
  page.cleanup()
  assert.equal(page.timers.size, 0)
})


test('failure updates preserve the user choice to keep details closed or open', async () => {
  const page = harness()
  await page.update([group(5, 1)])
  assert.equal(page.expanded.value, false)
  page.expanded.value = true
  await page.update([group(0, 2)])
  assert.equal(page.expanded.value, true)
  page.expanded.value = false
  await page.update([group(0, 3)])
  assert.equal(page.expanded.value, false)
})

test('summary uses compact numbers while details retain exact counts and paused categories', async () => {
  const page = harness()
  assert.equal(page.compactCount(84856), '8.5 万')
  assert.equal(page.compactCount(10000), '1 万')
  assert.equal(page.formatCount(84856), '84,856')
  await page.update([group(12, 0, 'paused')])
  assert.equal(page.detailCategories.value.length, 1)
})
