const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const { ref, computed, watch, reactive, nextTick } = require('vue')
const root = path.resolve(__dirname, '../../src')

const candidate = (id, identity_id = null) => ({
  id, photo_id: `photo-${id}`, face_rect: [.1, .1, .3, .3], identity_id,
  identity_name: identity_id, photo_time: null, similarity: .8,
  manually_confirmed: false, review_token: `review-${id}`,
})
const result = (items, more = false) => ({
  reference: candidate(1, 'wrong'), items, face_count: 120, photo_count: 100, has_more: more,
})

async function settle() {
  await nextTick()
  // Await promises crossing the VM boundary as well as Vue's watcher queue.
  await new Promise(setImmediate)
}

async function harness(initialSearch) {
  const source = fs.readFileSync(path.join(root, 'composables/useSimilarFaces.ts'), 'utf8')
    .replace(/^import .*$/gm, '')
  const props = reactive({ visible: true, reference: candidate(1, 'wrong') })
  const queries = [], submissions = [], undos = [], updated = []
  let search = initialSearch || (async () => result([candidate(2, 'wrong'), candidate(3)]))
  let apply = async () => ({ face_count: 2, photo_ids: ['photo-1', 'photo-2'], undo_token: 'undo' })
  let undo = async () => ({ face_count: 2, photo_ids: ['photo-1', 'photo-2'] })
  const watchers = []
  let cleanup
  const context = { exports: {}, ref, computed, AbortController, Map,
    watch: (...args) => { const stop = watch(...args); watchers.push(stop); return stop },
    onBeforeUnmount: fn => { cleanup = fn },
    faceApi: {
      searchSimilarFaces: (...args) => { queries.push(args); return search(...args) },
      assignSimilarFaces: (...args) => { submissions.push(args); return apply(...args) },
      undoFaceAssignment: (...args) => { undos.push(args); return undo(...args) },
    },
  }
  vm.createContext(context)
  vm.runInContext(ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, context)
  const page = context.exports.useSimilarFaces(props, ids => updated.push(ids))
  await settle()
  return { ...page, props, queries, submissions, undos, updated,
    search: fn => { search = fn }, submit: fn => { apply = fn }, undoAction: fn => { undo = fn },
    cleanup: () => { watchers.forEach(stop => stop()); cleanup?.() },
  }
}

test('only the reference is preselected and paging or filters preserve explicit selections', async t => {
  const p = await harness(); t.after(p.cleanup)
  assert.equal(p.selectedCount.value, 1)
  assert.equal(p.isSelected(p.items.value[0]), false)
  p.toggle(p.items.value[0])
  p.search(async () => result([candidate(4)]))
  await p.load(1)
  assert.equal(p.selectedCount.value, 2)
  assert.equal(p.page.value, 1)
  p.showSelected.value = true
  assert.equal(p.visibleItems.value.length, 2)
  p.scope.value = 'unassigned'
  await settle()
  assert.equal(p.selectedCount.value, 2)
  assert.equal(p.page.value, 0)
})

test('target assignments are excluded without deleting other selections and new target can be chosen', async t => {
  const p = await harness(); t.after(p.cleanup)
  p.toggle(p.items.value[0])
  p.chooseTarget({ id: 'wrong', identity_name: 'Wrong' })
  await settle()
  assert.equal(p.selectedCount.value, 0)
  assert.equal(p.canSubmit.value, false)
  assert.equal(p.queries.at(-1)[2].exclude_identity_id, 'wrong')
  p.chooseTarget({ id: 'correct', identity_name: 'Correct' })
  await settle()
  assert.equal(p.selectedCount.value, 2)
  assert.equal(p.canSubmit.value, true)
})

test('other-person scope is sent independently of the correction target and preserves selection', async t => {
  const p = await harness(); t.after(p.cleanup)
  p.toggle(p.items.value[0])
  await p.load(1)
  p.scope.value = 'other'
  await settle()
  assert.equal(p.queries.at(-1)[2].scope, 'other')
  assert.equal(p.queries.at(-1)[2].skip, 0)
  assert.equal(p.selectedCount.value, 2)
  p.chooseTarget({ id: 'correct', identity_name: 'Correct' })
  await settle()
  assert.equal(p.queries.at(-1)[2].scope, 'other')
  assert.equal(p.queries.at(-1)[2].exclude_identity_id, 'correct')
  assert.equal(p.selectedCount.value, 2)
})

test('low similarity uses only the reference as a sample and preserves explicitly selected candidates', async t => {
  const p = await harness(); t.after(p.cleanup)
  p.toggle(p.items.value[0])
  p.scope.value = 'current_low'
  await settle()
  assert.equal(p.queries.at(-1)[2].scope, 'current_low')
  assert.equal(p.selectedCount.value, 1)
  assert.equal(p.canSelect(p.reference.value), false)
  p.toggle(p.reference.value)
  assert.equal(p.selectedCount.value, 1)
  p.chooseTarget({ id: 'wrong', identity_name: 'Wrong' })
  await settle()
  assert.equal(p.canSubmit.value, false)
  p.chooseTarget({ id: 'correct', identity_name: 'Correct' })
  await settle()
  assert.equal(p.canSubmit.value, true)
  assert.equal(p.selectedCount.value, 1)
})

test('release submits null only for assigned selections and retains undo', async t => {
  const p = await harness(); t.after(p.cleanup)
  p.scope.value = 'current_low'; await settle()
  p.toggle(p.items.value[0])
  p.assignmentMode.value = 'unassigned'
  assert.equal(p.canSubmit.value, true)
  p.toggle(candidate(3))
  assert.equal(p.selectedCount.value, 1)
  p.submit(async () => ({ face_count: 1, photo_ids: ['photo-2'], undo_token: 'release-undo' }))
  await p.apply()
  assert.equal(p.submissions[0][2], null)
  assert.deepEqual(Array.from(p.submissions[0][3], item => item.id), [2])
  assert.match(p.successMessage.value, /释放为未标记/)
  assert.equal(p.undoToken.value, 'release-undo')
  await p.undo()
  assert.equal(p.undos[0][0], 'release-undo')
  assert.equal(p.updated.length, 2)
})

test('release and correction destination modes are independent from the search scope', async t => {
  const p = await harness(); t.after(p.cleanup)
  p.chooseTarget({ id: 'wrong', identity_name: 'Wrong' }); await settle()
  assert.equal(p.selectedCount.value, 0)
  p.assignmentMode.value = 'unassigned'; await settle()
  assert.equal(p.queries.at(-1)[2].exclude_identity_id, undefined)
  assert.equal(p.selectedCount.value, 1)
  p.chooseTarget({ id: 'correct', identity_name: 'Correct' }); await settle()
  assert.equal(p.assignmentMode.value, 'person')
  assert.equal(p.queries.at(-1)[2].exclude_identity_id, 'correct')
  assert.equal(p.selectedCount.value, 1)
})

test('mobile append preserves earlier faces and selection acts only on the last batch', async t => {
  const p = await harness(); t.after(p.cleanup)
  p.search(async () => result(Array.from({ length: 60 }, (_, i) => candidate(2 + i)), true))
  await p.load()
  p.search(async () => result(Array.from({ length: 10 }, (_, i) => candidate(62 + i))))
  await p.load(1, true)
  assert.equal(p.items.value.length, 70)
  p.selectPage()
  assert.equal(p.selectedCount.value, 11)
  assert.equal(p.isSelected(candidate(2)), false)
  assert.equal(p.isSelected(candidate(62)), true)
})

test('later search responses and closure cannot replace current results or selection', async t => {
  const p = await harness(); t.after(p.cleanup)
  let finish
  p.search(() => new Promise(resolve => { finish = resolve }))
  const old = p.load()
  const staleFinish = finish
  p.search(async () => result([candidate(20)]))
  await p.load()
  staleFinish(result([candidate(30)])); await old
  assert.equal(p.items.value[0].id, 20)
  p.search(() => new Promise(resolve => { finish = resolve }))
  const closing = p.load()
  p.props.visible = false; await settle()
  finish(result([candidate(40)])); await closing
  assert.equal(p.items.value[0].id, 20)
})

test('replacing a pending initial search still preselects the reference exactly once', async t => {
  let finish
  const p = await harness(() => new Promise(resolve => { finish = resolve }))
  t.after(p.cleanup)
  p.search(async () => result([candidate(20)]))
  p.scope.value = 'current'
  await settle()
  assert.equal(p.selectedCount.value, 1)
  finish(result([candidate(30)])); await settle()
  assert.equal(p.items.value[0].id, 20)
  p.clearSelection()
  await p.load()
  assert.equal(p.selectedCount.value, 0)
})

test('switching to low similarity during initial loading never selects the reference', async t => {
  let finish
  const p = await harness(() => new Promise(resolve => { finish = resolve }))
  t.after(p.cleanup)
  p.search(async () => result([candidate(20, 'wrong')]))
  p.scope.value = 'current_low'
  await settle()
  assert.equal(p.selectedCount.value, 0)
  finish(result([candidate(30)])); await settle()
  assert.equal(p.selectedCount.value, 0)
})

test('reviewed snapshots are never silently renewed after an assignment changed', async t => {
  const p = await harness(); t.after(p.cleanup)
  p.toggle(p.items.value[0])
  p.search(async () => result([{ ...candidate(2, 'other'), review_token: 'changed' }]))
  await p.load()
  assert.equal(p.selectedItems.value.find(item => item.id === 2).review_token, 'review-2')
  assert.equal(p.items.value[0].identity_id, 'other')
})

test('submission is single flight, selected faces only, and success exposes undo', async t => {
  const p = await harness(); t.after(p.cleanup)
  p.chooseTarget({ id: 'correct', identity_name: 'Correct' }); await settle()
  p.toggle(p.items.value[0])
  let finish
  p.submit(() => new Promise(resolve => { finish = resolve }))
  const pending = p.apply()
  await p.apply()
  assert.equal(p.submissions.length, 1)
  assert.deepEqual(Array.from(p.submissions[0][3], item => item.id), [1, 2])
  finish({ face_count: 2, photo_ids: ['photo-1', 'photo-2'], undo_token: 'undo' }); await pending
  assert.equal(p.selectedCount.value, 0)
  assert.equal(p.undoToken.value, 'undo')
  assert.equal(p.updated.length, 1)
  await p.undo()
  assert.equal(p.undos[0][0], 'undo')
  assert.equal(p.undoToken.value, null)
  assert.equal(p.updated.length, 2)
})

test('ordinary failures preserve selection while conflicts clear it and require review', async t => {
  const p = await harness(); t.after(p.cleanup)
  p.chooseTarget({ id: 'correct', identity_name: 'Correct' }); await settle()
  p.submit(async () => { throw new Error('offline') })
  await p.apply()
  assert.equal(p.selectedCount.value, 1)
  assert.match(p.actionError.value, /未保存/)
  p.submit(async () => { throw { response: { status: 409, data: { detail: '归属已变化' } } } })
  await p.apply()
  assert.equal(p.selectedCount.value, 0)
  assert.equal(p.canSubmit.value, false)
  assert.equal(p.actionError.value, '归属已变化')
})

test('reopening resets filters and still preselects only the new reference', async t => {
  const p = await harness(); t.after(p.cleanup)
  p.scope.value = 'current'; p.match.value = 'broad'; await settle()
  p.assignmentMode.value = 'unassigned'
  p.props.visible = false; await settle()
  p.props.visible = true; await settle()
  assert.equal(p.scope.value, 'all')
  assert.equal(p.match.value, 'balanced')
  assert.equal(p.assignmentMode.value, 'person')
  assert.equal(p.selectedCount.value, 1)
})

test('selection cap prevents an accidental oversized batch', async t => {
  const p = await harness(); t.after(p.cleanup)
  for (let i = 2; i <= 501; i++) p.toggle(candidate(i))
  assert.equal(p.selectedCount.value, 500)
  assert.match(p.actionError.value, /最多/)
})

test('changing target cannot exceed the cap through temporarily hidden selections', async t => {
  const p = await harness(); t.after(p.cleanup)
  for (let i = 2; i <= 500; i++) p.toggle(candidate(i, 'wrong'))
  p.chooseTarget({ id: 'wrong', identity_name: 'Wrong' }); await settle()
  assert.equal(p.selectedCount.value, 0)
  p.toggle(candidate(501))
  assert.match(p.actionError.value, /最多/)
  p.chooseTarget({ id: 'correct', identity_name: 'Correct' }); await settle()
  assert.equal(p.selectedCount.value, 500)
})

test('UI uses face crops, separate original preview, fullscreen mobile and explicit discard confirmation', () => {
  const source = fs.readFileSync(path.join(root, 'components/SimilarFacesDialog.vue'), 'utf8')
  const lightbox = fs.readFileSync(path.join(root, 'components/PhotoLightbox.vue'), 'utf8')
  assert.match(source, /mobile-mode="fullscreen" mobile-back history/)
  assert.match(source, /<FaceThumbnail :face="item"/)
  assert.match(source, /containFaceRect/)
  assert.match(source, /title="放弃本次选择？"/)
  assert.match(source, /<el-option label="非当前人物" value="other"/)
  assert.match(source, /label="当前人物 · 低相似" value="current_low"/)
  assert.match(source, /label="释放为未标记人脸" value="unassigned"/)
  assert.match(source, /仅作查找参照，不参与本次更正/)
  assert.match(source, /selectedItems.value.some\(item => item.id !== props.reference.id\)/)
  assert.match(lightbox, /查找相似人脸 · 批量更正/)
})

test('people album defers batch refresh until viewer closes so undo remains available', () => {
  const people = fs.readFileSync(path.join(root, 'views/album/people/PeopleDetail.vue'), 'utf8')
  const page = fs.readFileSync(path.join(root, 'components/UnifiedPhotoPage.vue'), 'utf8')
  assert.match(people, /@photo-update="handlePhotoUpdate"/)
  assert.match(people, /@viewer-close="refreshChangedFaces"/)
  assert.match(people, /if \(event.facesChanged\) facesChanged.value = true/)
  assert.match(page, /emit\('viewer-close'\)/)
})
