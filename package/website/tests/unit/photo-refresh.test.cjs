const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const { watch } = require('vue')

function harness() {
  const photo = id => ({ id, width: 100, height: 100, filename: id, photo_time: '2026-10-01T12:00:00' })
  const stats = { total_photos: 1, timeline: [{ year: 2026, month: 10, day: 1, count: 1 }] }
  const api = { getTimelineStats: async () => stats, getAllPhotos: async () => [photo('old')] }
  const deps = { '@/api/album': { albumService: api }, '@/api/search': {}, '@/config/server': { toServerUrl: url => url }, '@/utils/mediaUrl': { thumbnailUrl: id => `/thumb/${id}` } }
  const source = fs.readFileSync(path.resolve(__dirname, '../../src/stores/photoStore.ts'), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const module = { exports: {} }
  vm.runInThisContext(`(function(require,module,exports){${code}\n})`)(name => deps[name] || require(name), module, module.exports)
  const store = module.exports.photoStoreSetup()
  store.timelineStats.value = stats
  return { store, api, photo }
}

test('background refresh keeps old photos until new data is ready, with no empty frame', async () => {
  const { store, api, photo } = harness()
  await store.loadPhotosByMonth(2026, 10)
  let release
  api.getAllPhotos = () => new Promise(resolve => { release = resolve })
  const lengths = []
  const stop = watch(store.images, photos => lengths.push(photos.length), { flush: 'sync' })
  const refresh = store.refreshCurrentContext()
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(store.images.value[0].id, 'old')
  assert.equal(store.loading.value, false)
  release([photo('new')]); await refresh
  assert.equal(store.images.value[0].id, 'new')
  assert.deepEqual(lengths, [1]); stop()
})

test('failed refresh preserves content and pending revision; changed filters discard late responses', async () => {
  const { store, api, photo } = harness()
  await store.loadPhotosByMonth(2026, 10)
  store.markDataStale('PROCESS_BASIC')
  api.getAllPhotos = async () => { throw new Error('offline') }
  await assert.rejects(store.refreshCurrentContext(), /offline/)
  assert.equal(store.images.value[0].id, 'old')
  assert.equal(store.dataStale.value, true)
  let release
  api.getAllPhotos = () => new Promise(resolve => { release = resolve })
  const refresh = store.refreshCurrentContext()
  await new Promise(resolve => setImmediate(resolve))
  store.selectedFilters.years = [2025]
  release([photo('late')]); await refresh
  assert.equal(store.images.value[0].id, 'old')
})

test('months loaded while a refresh is running keep their virtual offsets', async () => {
  const { store, api, photo } = harness()
  const stats = { total_photos: 2, timeline: [
    { year: 2026, month: 10, day: 1, count: 1 },
    { year: 2026, month: 9, day: 1, count: 1 },
  ] }
  store.timelineStats.value = stats
  api.getTimelineStats = async () => stats
  await store.loadPhotosByMonth(2026, 10)
  let release
  api.getAllPhotos = async (_offset, _count, filters) => filters.start_time.startsWith('2026-09')
    ? [{ ...photo('september'), photo_time: '2026-09-01T12:00:00' }]
    : await new Promise(resolve => { release = resolve })
  const refresh = store.refreshCurrentContext()
  await new Promise(resolve => setImmediate(resolve))
  await store.loadPhotosByMonth(2026, 9)
  release([photo('new')]); await refresh
  assert.deepEqual([...store.photoOffsetMap.values()].map(image => image.id), ['new', 'september'])
})
