const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const vue = require('vue')
const compiler = require('vue/compiler-sfc')

const read = name => fs.readFileSync(path.resolve(__dirname, '../../src/components', name), 'utf8')
const { descriptor } = compiler.parse(read('TimeBatchEditor.vue'))
const script = descriptor.scriptSetup.content.replace(/^import .*$/gm, '')
const code = ts.transpileModule(script + '\nglobalThis.subject = { photoTime, modifyOriginalFile, submitting, completed, failedIds, handleApply }', {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText

function setup(updatePhoto = async () => {}) {
  const events = []
  const calls = []
  const props = vue.reactive({ modelValue: true, photoIds: ['a', 'b', 'a'] })
  const context = {
    ref: vue.ref, watch: vue.watch, defineProps: () => props,
    defineEmits: () => (...args) => events.push(args),
    albumService: { updatePhoto: async (...args) => { calls.push(args); await updatePhoto(...args) } },
    ElMessage: { success() {}, warning() {} },
  }
  vm.runInNewContext(code, context)
  return { ...context.subject, props, events, calls }
}

test('batch time sends only selected distinct IDs, preserves local time and honors file switch', async () => {
  const s = setup()
  await s.handleApply()
  assert.equal(s.calls.length, 0)
  assert.equal(s.modifyOriginalFile.value, true)
  s.photoTime.value = '2026-10-08 18:52:29'
  s.modifyOriginalFile.value = false
  await s.handleApply()
  assert.deepEqual(s.calls.map(c => c[0]), ['a', 'b'])
  assert.equal(s.calls[0][1].photo_time, '2026-10-08 18:52:29')
  assert.equal(s.calls[0][1].modify_original_file, false)
  assert.deepEqual(s.events, [['updated'], ['update:modelValue', false], ['success']])
})

test('partial failure keeps dialog open and retries only failed IDs', async () => {
  let fail = true
  const s = setup(async id => { if (id === 'b' && fail) throw Error('read-only') })
  s.photoTime.value = '2026-10-08 18:52:29'
  await s.handleApply()
  assert.deepEqual(Array.from(s.failedIds.value), ['b'])
  assert.deepEqual(s.events, [['updated']])
  fail = false
  await s.handleApply()
  assert.deepEqual(s.calls.map(c => c[0]), ['a', 'b', 'b'])
  assert.equal(s.failedIds.value.length, 0)
  assert.equal(s.submitting.value, false)
})

test('duplicate submission is blocked and reopening restores defaults', async () => {
  let release
  const gate = new Promise(resolve => { release = resolve })
  const s = setup(() => gate)
  s.photoTime.value = '2026-10-08 18:52:29'
  const pending = s.handleApply()
  await s.handleApply()
  assert.equal(s.calls.length, 1)
  release()
  await pending
  s.modifyOriginalFile.value = false
  s.props.modelValue = false
  await vue.nextTick()
  s.props.modelValue = true
  await vue.nextTick()
  assert.equal(s.modifyOriginalFile.value, true)
  assert.equal(s.photoTime.value, '')
})

test('gallery event forwarding preserves location action alongside time action', () => {
  for (const name of ['PhotoGallery.vue', 'FlatPhotoGallery.vue']) {
    const source = read(name)
    assert.ok(source.includes('@batch-edit-time="ids => $emit(\'batch-edit-time\', ids)"'))
    assert.ok(source.includes('@batch-edit-location="ids => $emit(\'batch-edit-location\', ids)"'))
  }
  const location = read('LocationBatchEditor.vue')
  assert.match(location, /const writeToFile = ref\(true\)/)
  assert.match(location, /writeToFile.value = true/)
  const sidebar = read('PhotoMetadataSidebar.vue')
  assert.match(sidebar, /const locationWriteToFile = ref\(true\)/)
  assert.match(sidebar, /locationWriteToFile.value = true/)
  assert.match(sidebar, /basicEditForm.modifyOriginalFile = true/)
})
