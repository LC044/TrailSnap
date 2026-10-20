const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const { ref, computed } = require('vue')

function harness(getAIModels) {
  const source = fs.readFileSync(path.resolve(__dirname, '../../src/views/settings/AIModelManagement.vue'), 'utf8')
  const script = source.split('<script setup lang="ts">')[1].split('</script>')[0].replace(/^import .*$/gm, '')
  const timers = new Map()
  let cleanup
  const context = { ref, computed, onMounted() {}, onUnmounted(fn) { cleanup = fn },
    settingsApi: { getAIModels }, ElMessage: {}, ElMessageBox: {},
    window: { setInterval(fn) { timers.set(1, fn); return 1 }, clearInterval(id) { timers.delete(id) } } }
  vm.createContext(context)
  vm.runInContext(ts.transpileModule(script + '\nglobalThis.page = { loadModels, models, maintenance, errorMessage };', {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText, context)
  return { ...context.page, timers, cleanup: () => cleanup() }
}

test('maintenance keeps model status visible and polls until service resumes', async () => {
  let maintenance = true
  const page = harness(async () => ({ maintenance, models: [{ id: 'llm', status: maintenance ? 'downloading' : 'ready' }] }))
  await page.loadModels()
  assert.equal(page.maintenance.value, true)
  assert.equal(page.models.value[0].id, 'llm')
  assert.equal(page.timers.size, 1)
  maintenance = false
  await page.loadModels(true)
  assert.equal(page.maintenance.value, false)
  assert.equal(page.errorMessage.value, '')
  assert.equal(page.timers.size, 0)
})

test('legacy maintenance 503 preserves automatic recovery and unmount clears timers', async () => {
  const page = harness(async () => { throw { response: { data: { msg: 'ai_extension_wait=maintenance 等待 AI 扩展更新' } } } })
  await page.loadModels()
  assert.equal(page.maintenance.value, true)
  assert.equal(page.errorMessage.value, '')
  assert.equal(page.timers.size, 1)
  page.cleanup()
  assert.equal(page.timers.size, 0)
})

test('slow polls cannot overlap or install a timer after unmount', async () => {
  let resolve, calls = 0
  const page = harness(() => { calls++; return new Promise(done => { resolve = done }) })
  const pending = page.loadModels()
  await page.loadModels(true)
  assert.equal(calls, 1)
  page.cleanup()
  resolve({ maintenance: true, models: [] })
  await pending
  assert.equal(page.timers.size, 0)
})
