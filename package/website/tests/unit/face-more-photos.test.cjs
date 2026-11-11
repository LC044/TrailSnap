const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const { ref, computed, watch, reactive, nextTick } = require('vue')

const source = fs.readFileSync(path.resolve(__dirname, '../../src/components/FaceRescanDialog.vue'), 'utf8')
const candidate = id => ({ face_id: id, recommended: true, assignment_type: 'unassigned' })
const result = (threshold = .45, id = 1) => ({ candidate_threshold: threshold, reason: null,
  add_candidates: [candidate(id)], remove_candidates: [], summary: { add_count: 1, remove_count: 0 } })
async function settle() { await nextTick(); await new Promise(setImmediate) }

async function harness(search = async (_id, threshold) => result(threshold)) {
  const script = source.split('<script setup lang="ts">')[1].split('</script>')[0].replace(/^import .*$/gm, '')
  const props = reactive({ visible: true, identity: { id: 'person-1' } })
  const queries = [], applied = [], events = [], watchers = []
  let cleanup
  const context = { ref, computed, AbortController, defineComponent: x => x, console: { error() {} },
    watch: (...args) => { const stop = watch(...args); watchers.push(stop); return stop },
    onBeforeUnmount: fn => { cleanup = fn }, defineProps: () => props,
    defineEmits: () => (...args) => events.push(args), ElMessage: { success() {}, warning() {}, error() {} },
    faceApi: {
      previewIdentityRescan: (...args) => { queries.push(args); return search(...args) },
      applyIdentityRescan: async (...args) => { applied.push(args); return { added_count: 1 } },
    },
  }
  vm.createContext(context)
  vm.runInContext(ts.transpileModule(script + '\nglobalThis.page = { threshold, thresholdChanged, preview, loading, selectedAddIds, applySelection, loadPreview };', {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText, context)
  await settle()
  return { ...context.page, props, queries, applied, events,
    cleanup: () => { watchers.forEach(stop => stop()); cleanup?.() } }
}

test('more photos uses saved default, then reuses reviewed custom threshold when applying', async t => {
  const p = await harness(); t.after(p.cleanup)
  assert.equal(p.queries[0][1], undefined)
  assert.equal(p.threshold.value, .45)
  p.threshold.value = .63
  assert.equal(p.thresholdChanged.value, true)
  await p.applySelection()
  assert.equal(p.applied.length, 0)
  await p.loadPreview()
  assert.equal(p.queries.at(-1)[1], .63)
  assert.equal(p.thresholdChanged.value, false)
  await p.applySelection()
  assert.equal(p.applied[0][1].threshold, .63)
  assert.equal(p.applied[0][1].add_face_ids[0], 1)
})

test('changing person discards stale responses and starts from that persons configured threshold', async t => {
  const pending = []
  const p = await harness((...args) => new Promise(resolve => pending.push({ args, resolve }))); t.after(p.cleanup)
  p.props.identity = { id: 'person-2' }; await settle()
  assert.equal(p.queries[0][2].aborted, true)
  assert.equal(p.queries[1][0], 'person-2')
  assert.equal(p.queries[1][1], undefined)
  pending[1].resolve(result(.5, 2)); await settle()
  pending[0].resolve(result(.45, 1)); await settle()
  assert.equal(p.preview.value.add_candidates[0].face_id, 2)
  assert.equal(p.threshold.value, .5)
  assert.equal(p.loading.value, false)
})

test('closing cancels preview and prevents late results from replacing a reopened search', async t => {
  const pending = []
  const p = await harness(() => new Promise(resolve => pending.push(resolve))); t.after(p.cleanup)
  p.props.visible = false; await settle()
  p.props.visible = true; await settle()
  pending[0](result(.9, 9)); await settle()
  assert.equal(p.preview.value, null)
  pending[1](result(.45, 1)); await settle()
  assert.equal(p.preview.value.add_candidates[0].face_id, 1)
})

test('more photos dialog uses shared mobile presentation and explains threshold scope', () => {
  assert.match(source, /title="查找此人的更多照片"/)
  assert.match(source, /<ResponsiveDialog/)
  assert.match(source, /不会重新检测照片/)
  assert.match(source, /仅用于本次查找/)
})
