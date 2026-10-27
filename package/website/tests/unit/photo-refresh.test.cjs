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
  const helpers = { exports: {} }
  const helperSource = fs.readFileSync(path.resolve(__dirname, '../../src/utils/mediaTypeFilters.ts'), 'utf8')
  const helperCode = ts.transpileModule(helperSource, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  vm.runInThisContext(`(function(exports){${helperCode}\n})`)(helpers.exports)
  deps['@/utils/mediaTypeFilters'] = helpers.exports
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

test('time sorting publishes complete data atomically and keeps the same photo across years', async () => {
  const { store, api, photo } = harness()
  store.browseEnabled.value = true
  const a = { ...photo('a'), photo_time: '2020-05-01T12:00:00', upload_time: '2026-10-01T12:00:00' }
  store.images.value = [store.mapTimelinePhoto(a)]
  api.getTimelineStats = async (_album, filters) => {
    assert.equal(filters.time_field, 'upload_time')
    return { total_photos: 1, timeline: [{ year: 2026, month: 10, day: 1, count: 1 }] }
  }
  let release
  api.getAllPhotos = (_skip, _count, filters) => {
    assert.equal(filters.browse_year, 2026)
    assert.equal(filters.browse_month, 10)
    return new Promise(resolve => { release = resolve })
  }
  const switching = store.changeTimeField('upload_time', store.images.value[0])
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(store.timeField.value, 'photo_time')
  assert.equal(new Date(store.images.value[0].timestamp).getFullYear(), 2020)
  release([a]); assert.equal(await switching, true)
  assert.equal(store.timeField.value, 'upload_time')
  assert.equal(store.images.value[0].id, 'a')
  assert.equal(new Date(store.images.value[0].timestamp).getFullYear(), 2026)
})

test('superseded time queries and failures cannot replace the visible dataset', async () => {
  const { store, api, photo } = harness()
  store.browseEnabled.value = true
  store.images.value = [store.mapTimelinePhoto(photo('old'))]
  let release
  api.getAllPhotos = () => new Promise(resolve => { release = resolve })
  const pending = store.changeTimeField('upload_time', null, () => false)
  await new Promise(resolve => setImmediate(resolve))
  release([photo('stale')]); assert.equal(await pending, false)
  assert.equal(store.images.value[0].id, 'old')
  api.getAllPhotos = async () => { throw new Error('offline') }
  await assert.rejects(store.changeTimeField('upload_time'), /offline/)
  assert.equal(store.timeField.value, 'photo_time')
  assert.equal(store.images.value[0].id, 'old')
})

test('unknown times stay unknown, sort last, and load through an explicit unknown bucket', async () => {
  const { store, api, photo } = harness()
  store.browseEnabled.value = true
  const unknown = { ...photo('unknown'), photo_time: null, upload_time: '2026-10-01T12:00:00' }
  store.timelineStats.value = { total_photos: 2, timeline: [
    { year: 2026, month: 10, day: 1, count: 1 }, { year: 0, month: 0, day: 0, count: 1 },
  ] }
  api.getAllPhotos = async (_skip, _count, filters) => {
    assert.equal(filters.browse_year, 0)
    assert.equal(filters.browse_month, undefined)
    return [unknown]
  }
  await store.loadPhotosByMonth(0, 0)
  assert.ok(Number.isNaN(store.images.value[0].timestamp))
  assert.equal(store.images.value[0].uploadTime, unknown.upload_time)
  assert.equal(store.photoOffsetMap.get(1).id, 'unknown')
})

test('a drill-down waits for the same in-flight month rather than treating it as loaded', async () => {
  const { store, api, photo } = harness()
  let release, calls = 0
  api.getAllPhotos = () => { calls++; return new Promise(resolve => { release = resolve }) }
  const background = store.loadPhotosByMonth(2026, 10)
  let finished = false
  const navigation = store.loadPhotosByMonth(2026, 10).then(() => { finished = true })
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(finished, false)
  assert.equal(calls, 1)
  release([photo('a')]); await Promise.all([background, navigation])
  assert.equal(finished, true)
  assert.equal(store.images.value[0].id, 'a')
})

test('overview sorting only resolves its anchor and defers the full month until drill-down', async () => {
  const { store, api, photo } = harness()
  store.browseEnabled.value = true
  const a = { ...photo('a'), upload_time: '2026-10-01T12:00:00' }
  let fullMonthLoads = 0
  api.getAllPhotos = async (_offset, count, filters) => {
    if (filters.ids) { assert.equal(count, 1); assert.deepEqual(filters.ids, ['a']) }
    else fullMonthLoads++
    return [a]
  }
  await store.loadPhotosByMonth(2026, 10)
  await store.changeTimeField('upload_time', store.images.value[0], () => true, false)
  assert.equal(fullMonthLoads, 1)
  await store.loadPhotosByMonth(2026, 10)
  assert.equal(fullMonthLoads, 2)
})
