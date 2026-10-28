const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const { ref, computed } = require('vue')

function resultHarness(api) {
  const source = fs.readFileSync(path.resolve(__dirname, '../../src/views/agent/components/AgentPhotoSearchResults.vue'), 'utf8')
  const script = source.split('<script setup lang="ts">')[1].split('</script>')[0].replace(/^import .*$/gm, '')
  let dispose
  const context = { ref, computed, defineProps: () => ({ result: { id: 'result-1', total: 65, filters: { location: '西安' } } }),
    agentApi: api, mapPhotoToImage: photo => photo, onMounted() {}, onBeforeUnmount(fn) { dispose = fn } }
  vm.createContext(context)
  vm.runInContext(ts.transpileModule(script + '\nglobalThis.resultPage = { loadMore, photos, total, nextOffset, error, loading, openPhoto, lightboxOpen, photoIndex };', {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText, context)
  return { ...context.resultPage, dispose: () => dispose() }
}

test('result gallery loads all pages in order and opens real photos', async () => {
  const calls = []
  const page = resultHarness({ async getSearchResultPhotos(id, offset) {
    calls.push([id, offset])
    return { data: { total: 65, next_offset: offset === 0 ? 60 : null,
      photos: Array.from({ length: offset === 0 ? 60 : 5 }, (_, i) => ({ id: String(offset + i) })) } }
  } })
  await page.loadMore(); await page.loadMore(); await page.loadMore()
  assert.deepEqual(calls, [['result-1', 0], ['result-1', 60]])
  assert.equal(page.photos.value.length, 65)
  assert.equal(page.photos.value[64].id, '64')
  assert.equal(page.nextOffset.value, null)
  page.openPhoto(page.photos.value[64])
  assert.equal(page.photoIndex.value, 64)
  assert.equal(page.lightboxOpen.value, true)
})

test('failed page keeps existing results and retries the same offset', async () => {
  let unavailable = true
  const calls = []
  const page = resultHarness({ async getSearchResultPhotos(id, offset) {
    calls.push(offset)
    if (unavailable) throw Error('offline')
    return { data: { total: 0, next_offset: null, photos: [] } }
  } })
  await page.loadMore()
  assert.match(page.error.value, /重试/)
  assert.equal(page.loading.value, false)
  unavailable = false
  await page.loadMore()
  assert.deepEqual(calls, [0, 0])
  assert.equal(page.error.value, '')
  assert.equal(page.total.value, 0)
})

test('unmounted result ignores late responses', async () => {
  let resolve
  const page = resultHarness({ getSearchResultPhotos() { return new Promise(done => { resolve = done }) } })
  const pending = page.loadMore()
  page.dispose()
  resolve({ data: { total: 1, next_offset: null, photos: [{ id: 'late' }] } })
  await pending
  assert.equal(page.photos.value.length, 0)
})

test('search entry carries explicit search mode and consumes it once', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../../src/stores/uiStore.ts'), 'utf8').replace(/^import .*$/gm, '').replace('export const', 'const')
  const context = { ref, defineStore: (_, setup) => setup }
  vm.createContext(context)
  vm.runInContext(ts.transpileModule(source + '\nglobalThis.store = useUiStore();', { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText, context)
  context.store.openAgentWithPrompt('去年西安的合照', true, 'search')
  assert.equal(context.store.agentOpen.value, true)
  const request = context.store.consumeAgentPrompt()
  assert.equal(request.mode, 'search')
  assert.equal(request.prompt, '去年西安的合照')
  assert.equal(request.autoSend, true)
  assert.equal(context.store.consumeAgentPrompt().prompt, '')
  context.store.openAgentWithPrompt('写一篇游记', true)
  assert.equal(context.store.consumeAgentPrompt().mode, 'assistant')
})
