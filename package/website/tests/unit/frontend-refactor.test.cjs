const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const vue = require('vue')

// Execute the real TS modules with only network/UI boundaries replaced.
function loadSource(filename, dependencies = {}) {
  let source = fs.readFileSync(path.resolve(__dirname, '../../src', filename), 'utf8')
  if (filename.endsWith('.vue')) {
    const compiler = require('vue/compiler-sfc')
    source = compiler.compileScript(compiler.parse(source).descriptor, { id: filename }).content
  }
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const module = { exports: {} }
  const requireDependency = name => {
    if (name === 'vue') return vue
    if (name in dependencies) return dependencies[name]
    throw new Error(`Unexpected dependency ${name}`)
  }
  vm.runInThisContext(`(function(require, module, exports) { ${code}\n})`, { filename })(requireDependency, module, module.exports)
  return module.exports
}
const renderer = vue.createRenderer({
  insert() {}, remove() {}, createElement: () => ({}), createText: () => ({}), createComment: () => ({}),
  setText() {}, setElementText() {}, parentNode: () => null, nextSibling: () => null, patchProp() {},
})
function mount(setup) {
  let value
  const app = renderer.createApp({ setup() { value = setup(); return () => null } })
  app.mount({})
  return { value, unmount: () => app.unmount() }
}
const flush = async () => { for (let i = 0; i < 8; i++) await Promise.resolve() }
const photo = id => ({ id, filename: `${id}.jpg`, url: `/${id}`, thumbnail: `/${id}`, timestamp: 0 })
const task = (id, status = 'processing') => ({ id, status, type: 'BATCH_RENAME', total_items: 10, processed_items: 2 })

test('viewer keeps the current ID through inserts and selects a neighbor on removal', async () => {
  const { usePhotoViewer } = loadSource('composables/usePhotoViewer.ts')
  const scope = vue.effectScope()
  const photos = vue.ref(['a', 'b', 'c'].map(photo))
  const viewer = scope.run(() => usePhotoViewer(photos))
  viewer.open(1)
  photos.value.unshift(photo('first'))
  await vue.nextTick()
  assert.equal(viewer.currentPhoto.value.id, 'b')
  photos.value = photos.value.filter(item => item.id !== 'b')
  await vue.nextTick()
  assert.equal(viewer.currentPhoto.value.id, 'c')
  photos.value = []
  await vue.nextTick()
  assert.equal(viewer.visible.value, false)
  assert.equal(viewer.hasNext.value, false)
  scope.stop()
})

test('sorting a large photo list batches viewer scans with the preview open or closed', async () => {
  const { usePhotoViewer } = loadSource('composables/usePhotoViewer.ts')
  for (const previewOpen of [false, true]) {
    let idReads = 0
    const size = 3000
    const scope = vue.effectScope()
    const photos = vue.ref(Array.from({ length: size }, (_, timestamp) => ({
      ...photo(String(timestamp)), timestamp,
      get id() { idReads++; return String(timestamp) },
    })))
    const viewer = scope.run(() => usePhotoViewer(photos))
    if (previewOpen) viewer.open(100)
    await vue.nextTick()
    idReads = 0
    photos.value.sort((a, b) => b.timestamp - a.timestamp)
    await vue.nextTick()
    assert.ok(idReads <= size * 2, `sort scanned too many IDs: ${idReads}`)
    assert.equal(viewer.visible.value, previewOpen)
    if (previewOpen) assert.equal(viewer.currentPhoto.value.id, '100')
    scope.stop()
  }
})

test('viewer chooses the last neighbor when the last photo is removed, and stays closed on list changes', async () => {
  const { usePhotoViewer } = loadSource('composables/usePhotoViewer.ts')
  const scope = vue.effectScope()
  const photos = vue.ref(['a', 'b', 'c'].map(photo))
  const viewer = scope.run(() => usePhotoViewer(photos))
  viewer.open(2)
  photos.value.pop()
  await vue.nextTick()
  assert.equal(viewer.currentPhoto.value.id, 'b')
  viewer.close()
  photos.value.push(photo('d'))
  await vue.nextTick()
  assert.equal(viewer.visible.value, false)
  assert.equal(viewer.currentPhoto.value, null)
  scope.stop()
})

test('viewer supports paging at the end and does not navigate past either boundary', () => {
  const { usePhotoViewer } = loadSource('composables/usePhotoViewer.ts')
  const scope = vue.effectScope()
  let loads = 0
  const viewer = scope.run(() => usePhotoViewer(vue.ref([photo('a')]), { onNextAtEnd: () => loads++ }))
  viewer.open(0); viewer.prev(); viewer.next()
  assert.equal(viewer.currentPhoto.value.id, 'a')
  assert.equal(loads, 1)
  viewer.close()
  assert.equal(viewer.currentIndex.value, -1)
  scope.stop()
})

test('monitor ignores late responses from a replaced task and stops after completion', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  let resolveOld, calls = 0, completions = 0
  const { useTaskMonitor } = loadSource('composables/useTaskMonitor.ts', { '@/api/tasks': { tasksApi: {
    getTask: id => { calls++; return id === 'old' ? new Promise(resolve => { resolveOld = resolve }) : Promise.resolve(task(id, 'completed')) },
  } } })
  const mounted = mount(() => useTaskMonitor({ loadLatest: async () => task('old'), taskType: 'BATCH_RENAME', onCompleted: () => completions++ }))
  await flush()
  t.mock.timers.tick(2000)
  mounted.value.activeTask.value = task('new')
  resolveOld(task('old', 'completed')); await flush()
  assert.equal(mounted.value.activeTask.value.id, 'new')
  assert.equal(completions, 0)
  t.mock.timers.tick(2000); await flush()
  assert.equal(mounted.value.activeTask.value.status, 'completed')
  assert.equal(completions, 1)
  t.mock.timers.tick(10000); await flush()
  assert.equal(calls, 2)
  mounted.unmount()
})

test('monitor does not apply an in-flight request or schedule more work after unmount', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  let resolve, completions = 0, calls = 0
  const { useTaskMonitor } = loadSource('composables/useTaskMonitor.ts', { '@/api/tasks': { tasksApi: {
    getTask: () => { calls++; return new Promise(done => { resolve = done }) },
  } } })
  const mounted = mount(() => useTaskMonitor({ loadLatest: async () => task('a'), taskType: 'BATCH_RENAME', onCompleted: () => completions++ }))
  await flush(); t.mock.timers.tick(2000)
  mounted.unmount(); resolve(task('a', 'completed')); await flush()
  t.mock.timers.tick(10000); await flush()
  assert.equal(completions, 0)
  assert.equal(calls, 1)
  assert.equal(mounted.value.activeTask.value.status, 'processing')
})

test('a task request failure retries without overlapping requests', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  let calls = 0, errors = 0
  const { useTaskMonitor } = loadSource('composables/useTaskMonitor.ts', { '@/api/tasks': { tasksApi: {
    getTask: async () => { if (++calls === 1) throw Error('offline'); return task('a', 'cancelled') },
  } } })
  const mounted = mount(() => useTaskMonitor({ loadLatest: async () => task('a'), taskType: 'BATCH_RENAME', onError: () => errors++ }))
  await flush(); t.mock.timers.tick(2000); await flush()
  assert.equal(errors, 1)
  t.mock.timers.tick(2000); await flush()
  assert.equal(mounted.value.isTaskRunning.value, false)
  mounted.unmount()
})

test('failed-task clearing only clears its own task type', async () => {
  let deletedTypes
  const { useTaskMonitor } = loadSource('composables/useTaskMonitor.ts', { '@/api/tasks': { tasksApi: {
    deleteFailedTasks: async types => { deletedTypes = types },
  } } })
  const mounted = mount(() => useTaskMonitor({ loadLatest: async () => task('a', 'failed'), taskType: 'BATCH_RENAME' }))
  await flush(); await mounted.value.clearFailedTask()
  assert.deepEqual(deletedTypes, ['BATCH_RENAME'])
  assert.equal(mounted.value.activeTask.value, null)
  mounted.unmount()
})

test('download success preserves each gallery policy; failure preserves selection for retry', async () => {
  let fail = false, clears = 0, errors = 0
  const { usePhotoBatchActions } = loadSource('composables/usePhotoBatchActions.ts', {
    'element-plus': { ElMessage: { error: () => errors++, success() {} } },
    '@/api/face': { faceApi: {} },
    '@/api/photo': { photoApi: { downloadPhoto: async () => { if (fail) throw Error('offline') } } },
  })
  const options = { selectedIds: () => new Set(['a']), photos: () => [photo('a')], clearSelection: () => clears++ }
  await usePhotoBatchActions(options).handleDownload()
  assert.equal(clears, 0)
  const grouped = usePhotoBatchActions({ ...options, exitAfterDownload: true })
  await grouped.handleDownload()
  assert.equal(clears, 1)
  fail = true; await grouped.handleDownload()
  assert.equal(clears, 1)
  assert.equal(errors, 1)
  assert.equal(grouped.isDownloading.value, false)
})

test('saving face/service settings excludes stale LLM connections and defaults', async () => {
  const payloads = []
  const { useBasicSettings } = loadSource('composables/settings/useBasicSettings.ts', {
    '@/stores/user': { useUserStore: () => ({ userInfo: { is_superuser: true } }) },
    'element-plus': { ElMessage: { error() {}, success() {}, warning() {} }, ElMessageBox: {} },
    '@/api/settings': { settingsApi: {
      getSettings: async () => ({ ai: { ai_api_url: 'http://ai', face_recognition_threshold: 0.7, connections: [{ id: 'stale' }], chat_model_name: 'stale-model' } }),
      getSystemConfig: async () => ({}), updateSettings: async payload => payloads.push(payload),
    } },
    '@/composables/useTheme': { injectTheme: () => ({}) },
    './useMapSettings': { useMapSettings: () => ({ mapForm: vue.ref({ provider: 'tianditu', api_keys: [''] }), resetMapKeyTests() {} }) },
    './useIndexMaintenance': { useIndexMaintenance: () => ({}) },
    './faceRecognitionPresets': loadSource('composables/settings/faceRecognitionPresets.ts'),
  })
  const mounted = mount(useBasicSettings)
  await flush()
  await mounted.value.saveAISettings()
  assert.equal(payloads[0].ai.face_recognition_threshold, 0.7)
  assert.equal('ai_api_url' in payloads[0].ai, false)
  await mounted.value.saveAIServiceSettings()
  assert.deepEqual(Object.keys(payloads[1].ai), ['ai_api_url'])
  assert.equal(payloads[1].ai.ai_api_url, 'http://ai')
  assert.equal('connections' in payloads[0].ai, false)
  assert.equal('chat_model_name' in payloads[0].ai, false)
  mounted.unmount()
})

test('saving LLM settings excludes stale face and AI service configuration', async () => {
  const payloads = []
  const { default: component } = loadSource('views/settings/LLMSettings.vue', {
    'element-plus': { ElMessage: { error() {}, success() {} }, ElMessageBox: {} },
    '@/api/settings': { settingsApi: {
      getSettings: async () => ({ ai: {
        ai_api_url: 'http://old-service', face_recognition_threshold: 0.2,
        connections: [], visual_evaluation_prompt: 'review photos',
      } }),
      updateSettings: async payload => payloads.push(payload),
    } },
  })
  const mounted = mount(() => component.setup({}, { expose() {} }))
  await flush(); await mounted.value.saveAll()
  assert.equal('ai_api_url' in payloads[0].ai, false)
  assert.equal('face_recognition_threshold' in payloads[0].ai, false)
  assert.equal(payloads[0].ai.visual_evaluation_prompt, 'review photos')
  mounted.unmount()
})

// --- 批量主按钮恢复默认「删除」，解除关联移到「更多」菜单 ---
const readSource = file => fs.readFileSync(path.resolve(__dirname, '../../src', file), 'utf8').replace(/\r\n/g, '\n')

function extractBlock(source, name, terminator) {
  const start = source.indexOf(`const ${name} = `)
  assert.notEqual(start, -1, `${name} should exist`)
  const end = terminator === 'blankline'
    ? source.indexOf('\n\n', start)
    : (() => {
        let depth = 0
        for (let i = source.indexOf('{', start); i < source.length; i++) {
          if (source[i] === '{') depth++
          else if (source[i] === '}' && --depth === 0) return i + 1
        }
        return -1
      })()
  assert.ok(end > start, `${name} should have a detectable end`)
  return source.slice(start, end)
}

// 把 SFC 里的函数抽出来真实执行，避免为整个页面 stub 几十个依赖
function buildFn(source, name, names, terminator = 'blankline') {
  const snippet = extractBlock(source, name, terminator)
  const js = ts.transpileModule(`function __factory() {\n${snippet}\nreturn ${name}\n}\nreturn __factory()`, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None },
  }).outputText
  return new Function('ctx', `const { ${names.join(', ')} } = ctx\n${js}`)
}

test('批量主按钮走真删除，灯箱与「更多」解除关联保持原有语义', () => {
  const calls = []
  const ctx = {
    deletePhotosGlobally: (ids, cb) => { calls.push(['delete', ids]); cb(true) },
    detachPhotos: (ids, cb) => { calls.push(['detach', ids]); cb(true) },
    isUserAlbum: { value: true },
  }
  const people = buildFn(readSource('views/album/people/PeopleDetail.vue'), 'handleConfirmDelete',
    ['deletePhotosGlobally', 'detachPhotos'])(ctx)
  people(['p1'], () => {}, 'batch')
  people(['p1'], () => {})
  assert.deepEqual(calls, [['delete', ['p1']], ['detach', ['p1']]])

  calls.length = 0
  const album = buildFn(readSource('views/album/AlbumDetail.vue'), 'handleConfirmDelete',
    ['deletePhotosGlobally', 'detachPhotos', 'isUserAlbum'])(ctx)
  album(['p1'], () => {}, 'batch')
  album(['p1'], () => {})
  assert.deepEqual(calls, [['delete', ['p1']], ['detach', ['p1']]])
  calls.length = 0
  ctx.isUserAlbum.value = false
  album(['p1'], () => {})
  assert.deepEqual(calls, [['delete', ['p1']]], '系统相册没有移出语义，灯箱仍是真删除')
})

test('confirmDelete 把批量/灯箱来源传给视图，真删除才播放粒子', () => {
  const build = buildFn(readSource('components/UnifiedPhotoPage.vue'), 'confirmDelete', [
    'lightboxDeleteId', 'props', 'captureVisiblePhoto', 'emit', 'showParticle',
    'galleryRef', 'closeLightbox', 'nextTick', 'requestAnimationFrame', 'restoreVisiblePhoto', 'idsToDelete',
  ], 'braces')
  for (const { lightbox, label, source, particle } of [
    { lightbox: null, label: '从人物中移除', source: 'batch', particle: 1 },
    { lightbox: 'p1', label: '从人物中移除', source: 'lightbox', particle: 0 },
    { lightbox: 'p1', label: '删除', source: 'lightbox', particle: 1 },
  ]) {
    const events = []
    let particles = 0
    const ctx = {
      lightboxDeleteId: { value: lightbox },
      props: { deleteLabel: label, removeLabel: label === '删除' ? '' : label },
      captureVisiblePhoto: () => 'anchor',
      emit: (...args) => events.push(args),
      showParticle: { get value() { return false }, set value(v) { if (v) particles++ } },
      galleryRef: { value: { exitSelectionMode: () => {} } },
      closeLightbox: () => {},
      nextTick: cb => cb(),
      requestAnimationFrame: cb => cb(),
      restoreVisiblePhoto: () => {},
      idsToDelete: { value: ['p1', 'p2'] },
    }
    build(ctx)()
    assert.equal(events.length, 1)
    assert.equal(events[0][0], 'confirm-delete')
    assert.deepEqual(events[0][1], ['p1', 'p2'])
    assert.equal(events[0][3], source)
    events[0][2](true)
    assert.equal(particles, particle)
  }
})

test('主删除按钮恢复默认，解除关联项只出现在「更多」菜单', () => {
  const bar = readSource('components/PhotoBatchActionBar.vue')
  assert.match(bar, /removeLabel\?: string/)
  assert.match(bar, /removeLabel: ''/, '默认关闭，不影响其他页面')
  assert.match(bar, /v-if="removeLabel"/)
  assert.match(bar, /@click="\$emit\('remove-association', selectedArray\)"/)
  assert.match(bar, /:title="removeLabel"/)
  assert.match(bar, /v-if="albumContext && !removeLabel"/, '有专属菜单项时不重复显示「移出相册」')
  assert.match(bar, /'remove-association': \[ids: string\[\]\]/)
  assert.equal((bar.match(/title="deleteLabel"/g) || []).length, 1, '主删除按钮仍然只有一个')

  const gallery = readSource('components/PhotoGallery.vue')
  assert.match(gallery, /:remove-label="removeLabel"/)
  assert.match(gallery, /@remove-association="ids => \$emit\('remove-association', ids\)"/)
  assert.match(gallery, /props\.deleteLabel\.includes\('移除'\)/, '主按钮不含「移除」时走默认删除')

  const page = readSource('components/UnifiedPhotoPage.vue')
  assert.match(page, /props\.removeLabel \? '删除' : props\.deleteLabel/, '批量按钮恢复默认「删除」')
  assert.match(page, /@remove-association="handleBatchRemoveAssociation"/)
  assert.match(page, /\(e: 'confirm-remove-association'/)
  assert.match(page, /仅解除关联，照片本身不会被删除/)
  assert.match(page, /放入回收站，可稍后恢复/, '批量删除要提示可恢复')
  assert.doesNotMatch(page, /:delete-title="batchDeleteLabel"/, '灯箱仍沿用原有移除语义')

  const people = readSource('views/album/people/PeopleDetail.vue')
  assert.match(people, /remove-label="从人物中移除"/)
  assert.match(people, /@confirm-remove-association="handleConfirmRemoveAssociation"/)
  assert.match(people, /await photoStore\.deletePhotos\(ids\)/)
  assert.match(people, /await faceApi\.removePhotos\(identityId, ids\)/)
  assert.doesNotMatch(people, /confirm-remove\s/, '不再复用删除确认流程')

  const album = readSource('views/album/AlbumDetail.vue')
  assert.match(album, /:remove-label="isUserAlbum \? '从相册中移除' : ''"/)
  assert.match(album, /@confirm-remove-association="handleConfirmRemoveAssociation"/)
  assert.match(album, /await photoStore\.deletePhotos\(ids\)/)
  assert.match(album, /await albumStore\.removePhotosFromAlbum\(albumId, ids\)/)
  assert.match(album, /:delete-label="isUserAlbum \? '从相册中移除' : '删除'"/, '灯箱删除标题保持原样')
})
