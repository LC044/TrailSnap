const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const { ref, reactive, computed } = require('vue')

function harness(options = {}) {
  const source = fs.readFileSync(path.resolve(__dirname, '../../src/views/settings/ExternalGallery.vue'), 'utf8')
  const script = source.split('<script setup lang="ts">')[1].split('</script>')[0].replace(/^import .*$/gm, '')
  const calls = [], timers = [], watchers = []
  let cleanup
  const context = { ref, reactive, computed, onMounted() {}, onUnmounted(fn) { cleanup = fn },
    watch: (target, fn) => watchers.push(fn), nextTick: async () => {}, isTauriApp: () => false,
    useUserStore: () => ({ userInfo: { is_superuser: true } }),
    usePhotoStore: () => ({ markDataStale() {} }), usePhotosPageStore: () => ({ markDataStale() {} }),
    settingsApi: { scanAllDirectories: options.submit || (async uid => { calls.push(uid); return { task_id: 'scan' } }) },
    tasksApi: { getTask: options.getTask || (async () => ({ status: 'completed', result: { new_files: 3, deleted_files: 2,
      skipped_roots: [{ path: '/offline', reason: 'unreadable' }] } })) },
    ElMessage: { success() {}, error() {} },
    setTimeout: fn => { timers.push(fn); return timers.length }, clearTimeout() {},
  }
  vm.createContext(context)
  vm.runInContext(ts.transpileModule(script + '\nglobalThis.page = { scanAllDirs, scanningAll, selectedUserId, scanMessage, scanSkipped };', {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText, context)
  return { ...context.page, calls, timers, cleanup: () => cleanup(), switchUser: () => watchers[0]() }
}

test('scan sends the selected user and displays counts and unreadable roots', async () => {
  const h = harness()
  h.selectedUserId.value = 'owner'
  await h.scanAllDirs()
  assert.deepEqual(h.calls, ['owner'])
  assert.match(h.scanMessage.value, /3.*2/)
  assert.equal(h.scanSkipped.value[0].path, '/offline')
  assert.equal(h.scanningAll.value, false)
})

test('scan blocks duplicate submissions until completion', async () => {
  const h = harness({ getTask: async () => ({ status: 'processing' }) })
  await h.scanAllDirs()
  await h.scanAllDirs()
  assert.equal(h.calls.length, 1)
  assert.equal(h.scanningAll.value, true)
  assert.equal(h.timers.length, 1)
  h.cleanup()
})

test('submission failure allows retry and switching users discards a late response', async () => {
  const failed = harness({ submit: async () => { throw Error('failed') } })
  await failed.scanAllDirs()
  assert.equal(failed.scanningAll.value, false)
  assert.match(failed.scanMessage.value, /失败/)
  let finish
  const h = harness({ submit: () => new Promise(resolve => { finish = resolve }) })
  const pending = h.scanAllDirs()
  h.switchUser()
  finish({ task_id: 'old-user-scan' })
  await pending
  assert.equal(h.scanMessage.value, '')
  assert.equal(h.scanningAll.value, false)
})
