const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const { ref, reactive, watch, nextTick } = require('vue')

function harness(service = {}) {
  const source = fs.readFileSync(path.resolve(__dirname, '../../src/views/search/ImageSearch.vue'), 'utf8')
  const script = source.split('<script setup lang="ts">')[1].split('</script>')[0].replace(/^import .*$/gm, '')
  const route = reactive({ query: {} })
  const revoked = [], uploads = []
  let cleanup
  const context = { ref, watch, useRoute: () => route, useRouter: () => ({ async replace(value) { route.query = value.query || {} } }),
    useAppBack: () => () => {}, usePhotoViewer: () => ({ visible: ref(false), index: ref(0), open() {}, close() {}, prev() {}, next() {} }),
    onUnmounted(fn) { cleanup = fn }, mapPhotoToImage: photo => photo, thumbnailUrl: id => `/thumbnail/${id}`,
    URL: { createObjectURL(file) { uploads.push(file); return `blob:${uploads.length}` }, revokeObjectURL(url) { revoked.push(url) } },
    searchService: { async searchByImage() { return [] }, async searchByPhoto() { return [] }, ...service } }
  vm.createContext(context)
  vm.runInContext(ts.transpileModule(script + '\nglobalThis.page = { sourceFile, photoId, selectFile, selectPhoto, photos, loading, error, searched, search, previewUrl };', {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText, context)
  return { ...context.page, route, revoked, cleanup: () => cleanup() }
}
const flush = async () => { await nextTick(); await new Promise(resolve => setImmediate(resolve)) }

test('upload searches without persisting an asset and releases preview on replacement and unmount', async () => {
  const calls = []
  const page = harness({ async searchByImage(file, limit) { calls.push([file.name, limit]); return [{ photo: { id: 'match' } }] } })
  for (const name of ['first.png', 'second.png']) {
    const input = { files: [{ name, type: 'image/png', size: 12 }], value: name }
    await page.selectFile({ target: input }); await flush()
    assert.equal(input.value, '')
  }
  assert.deepEqual(calls, [['first.png', 100], ['second.png', 100]])
  assert.equal(page.photos.value[0].id, 'match')
  assert.deepEqual(page.revoked, ['blob:1'])
  page.cleanup()
  assert.deepEqual(page.revoked, ['blob:1', 'blob:2'])
})

test('library selection and viewer photo query use the photo endpoint; failures can be retried', async () => {
  const calls = []
  let unavailable = true
  const page = harness({ async searchByPhoto(id) { calls.push(id); if (unavailable) throw Error('offline'); return [] } })
  page.selectPhoto(['library-photo']); await flush()
  assert.equal(page.photoId.value, 'library-photo')
  assert.match(page.error.value, /搜索失败/)
  unavailable = false
  await page.search()
  assert.equal(page.error.value, '')
  assert.equal(page.searched.value, true)
  assert.deepEqual(calls, ['library-photo', 'library-photo'])
  page.cleanup()
})

test('late responses cannot replace results for the latest source', async () => {
  let finishFirst
  const page = harness({ searchByPhoto(id) { return id === 'first' ? new Promise(resolve => { finishFirst = resolve }) : Promise.resolve([{ photo: { id: 'new-match' } }]) } })
  page.route.query = { photo: 'first' }; await flush()
  page.route.query = { photo: 'second' }; await flush()
  finishFirst([{ photo: { id: 'stale-match' } }]); await flush()
  assert.equal(page.photos.value[0].id, 'new-match')
  assert.equal(page.loading.value, false)
  page.cleanup()
})

test('invalid uploads never call search', async () => {
  let calls = 0
  const page = harness({ async searchByImage() { calls++; return [] } })
  for (const file of [{ type: 'video/mp4', size: 1 }, { type: 'image/png', size: 0 }, { type: 'image/png', size: 21 * 1024 * 1024 }]) {
    await page.selectFile({ target: { files: [file], value: 'file' } })
    assert.match(page.error.value, /20 MB/)
  }
  assert.equal(calls, 0)
  page.cleanup()
})
