const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const { ref, computed, reactive } = require('vue')
const root = path.resolve(__dirname, '../../src')
const transpile = source => ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
const utils = { exports: {} }
const crop = { exports: {} }
vm.runInNewContext(transpile(fs.readFileSync(path.join(root, 'utils/faceCrop.ts'), 'utf8')), { exports: crop.exports, module: crop })
vm.runInNewContext(transpile(fs.readFileSync(path.join(root, 'utils/photoFaces.ts'), 'utf8')), { exports: utils.exports, module: utils, require: () => crop.exports })
const { containFaceRect, containFaceCircle } = utils.exports

function livePhotoHarness() {
  const source = fs.readFileSync(path.join(root, 'components/PhotoLightbox.vue'), 'utf8')
  const section = (start, end) => source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)))
  const state = { ref, computed, props: reactive({ image: { file_type: 'live_photo' } }), panoramaActive: ref(false),
    showFaces: ref(false), showOCR: ref(true), controlsVisible: ref(false), selectedPhotoFace: ref({ id: 7 }),
    isPlayingLive: ref(true), isLiveVideoVisible: ref(true), facesError: ref(false), loadPhotoFaces() {}, paused: false, finishMobileDetailsSettle() {} }
  state.liveVideoRef = ref({ pause() { state.paused = true } })
  vm.createContext(state)
  vm.runInContext(transpile(section('const isStillImage =', 'const isCurrentVideo =')
    + section('const toggleLivePlayback =', 'const onLivePlaying =')
    + section('const toggleFaces =', 'watch([() => props.image?.id')
    + '\nglobalThis.actions = { canShowFaces, isStillImage, toggleFaces, toggleLivePlayback };'), state)
  return { state, source, actions: state.actions }
}

test('face marking is available for Live Photo and planar photos while video and 360 mode stay excluded', () => {
  const { state, actions } = livePhotoHarness()
  for (const type of ['image', 'live_photo', undefined]) {
    state.props.image = { file_type: type }
    assert.equal(actions.canShowFaces.value, true)
    state.panoramaActive.value = true
    assert.equal(actions.canShowFaces.value, false)
    state.panoramaActive.value = false
  }
  state.props.image = { file_type: 'video' }
  assert.equal(actions.canShowFaces.value, false)
})

test('entering Live Photo face marking stops motion and explicitly playing Live leaves marking', () => {
  const { state, actions } = livePhotoHarness()
  actions.toggleFaces()
  assert.equal(state.showFaces.value, true)
  assert.equal(state.isPlayingLive.value, false)
  assert.equal(state.isLiveVideoVisible.value, false)
  assert.equal(state.paused, true)
  actions.toggleLivePlayback()
  assert.equal(state.showFaces.value, false)
  assert.equal(state.selectedPhotoFace.value, null)
  assert.equal(state.isPlayingLive.value, true)
  assert.equal(state.isLiveVideoVisible.value, false)
})

test('switching to or reopening Live Photo in marking mode does not restart its motion', () => {
  const { state, source } = livePhotoHarness()
  const changing = source.slice(source.indexOf('// Auto play if live photo'), source.indexOf('// Init new player if switching to video'))
  const visibleStart = source.indexOf('watch(() => props.visible, async')
  const openStart = source.indexOf("if (props.image.file_type === 'live_photo')", visibleStart)
  const opening = source.slice(openStart, source.indexOf("if (props.image.file_type === 'video')", openStart))
  state.newImg = { file_type: 'live_photo' }
  for (const marking of [true, false]) {
    state.showFaces.value = marking
    vm.runInContext(transpile(changing), state)
    assert.equal(state.isPlayingLive.value, !marking)
    vm.runInContext(transpile(opening), state)
    assert.equal(state.isPlayingLive.value, !marking)
  }
})

test('face coordinates exclude object-contain margins for landscape and portrait images', () => {
  const landscape = containFaceRect([0, 0, 1, 1], 400, 400, 800, 400)
  assert.equal(landscape.x, 0); assert.equal(landscape.y, 100)
  assert.equal(landscape.width, 400); assert.equal(landscape.height, 200)
  const portrait = containFaceRect([.25, .25, .75, .75], 400, 400, 400, 800)
  assert.equal(portrait.x, 150); assert.equal(portrait.y, 100)
  assert.equal(portrait.width, 100); assert.equal(portrait.height, 200)
})

test('invalid face boxes and unloaded images never produce hit targets', () => {
  for (const box of [null, [], [0, 0, NaN, 1], [-1, 0, 1, 1], [0, 0, 2, 1], [.5, 0, .2, 1]])
    assert.equal(containFaceRect(box, 400, 400, 800, 400), null)
  assert.equal(containFaceRect([0, 0, 1, 1], 400, 400, 0, 0), null)
})

test('circle uses the avatar crop center and padding and stays circular on portrait and landscape photos', () => {
  for (const [width, height] of [[400, 800], [800, 400]]) {
    const box = containFaceRect([.2, .1, .4, .4], 500, 500, width, height)
    const circle = containFaceCircle([.2, .1, .4, .4], 500, 500, width, height)
    assert.equal(circle.width, circle.height)
    assert.equal(circle.width, Math.max(box.width, box.height) * crop.exports.FACE_CROP_SCALE)
    assert.ok(Math.abs(circle.x + circle.width / 2 - (box.x + box.width / 2)) < 1e-8)
    assert.ok(Math.abs(circle.y + circle.height / 2 - (box.y + box.height / 2)) < 1e-8)
  }
})

function gestures() {
  const source = fs.readFileSync(path.join(root, 'components/PhotoLightbox.vue'), 'utf8')
  const start = source.indexOf('const handleMediaTap =')
  const end = source.indexOf('useOverlayStack(', start)
  const timers = new Map(); let counter = 0, zooms = []
  class Element { constructor(id) { this.dataset = { faceId: String(id) } } closest() { return this } }
  const state = { props: { visible: true }, suppressNextTap: ref(false), showFaces: ref(true), photoFaces: ref([{ id: 7 }]),
    selectedPhotoFace: ref(null), controlsVisible: ref(true), scale: ref(1), showSidebar: ref(false), showOCR: ref(false),
    isCurrentVideo: ref(false), panoramaActive: ref(false), isEditing: ref(false), mediaTapTimer: null, lastTouchZoomAt: 0,
    performance: { now: () => 1000 }, Element,
    setTimeout(fn) { const key = ++counter; timers.set(key, fn); return key }, clearTimeout(key) { timers.delete(key) },
    setPhotoZoom: (...args) => zooms.push(args), resetZoom: () => zooms.push('reset') }
  vm.createContext(state)
  vm.runInContext(transpile(source.slice(start, end) + '\nglobalThis.actions = { handleMediaTap, handleMediaDoubleClick };'), state)
  return { ...state, zooms, tap: () => state.actions.handleMediaTap({ target: new Element(7) }), flush() { for (const [key, fn] of [...timers]) { timers.delete(key); fn() } } }
}

test('single face click selects without toggling controls; double click zooms without selecting', () => {
  const a = gestures(); a.showFaces.value = false; a.tap(); assert.equal(a.selectedPhotoFace.value, null)
  a.flush(); assert.equal(a.selectedPhotoFace.value.id, 7); assert.equal(a.controlsVisible.value, true)
  const b = gestures(); b.tap(); b.tap(); b.actions.handleMediaDoubleClick({ clientX: 30, clientY: 40 }); b.flush()
  assert.equal(b.selectedPhotoFace.value, null)
  assert.deepEqual(b.zooms[0], [2.5, 30, 40])
})

test('drag/pinch suppression prevents accidental face selection; blank taps retain immersive behavior', () => {
  const a = gestures(); a.suppressNextTap.value = true; a.tap(); a.flush()
  assert.equal(a.selectedPhotoFace.value, null)
  a.actions.handleMediaTap({ target: null }); a.flush()
  assert.equal(a.controlsVisible.value, false)
})

test('a late face response or failure cannot replace the next photo or its loading state', async () => {
  const source = fs.readFileSync(path.join(root, 'components/PhotoLightbox.vue'), 'utf8')
  const start = source.indexOf('const loadPhotoFaces =')
  const end = source.indexOf('const toggleFaces =', start)
  const pending = []
  const state = { props: { image: { id: 'old' }, visible: true }, showFaces: ref(true), photoFaces: ref([]),
    selectedPhotoFace: ref(null), canShowFaces: ref(true), facesLoading: ref(false), facesError: ref(false), facesRequest: 0,
    faceApi: { getPhotoFaces: id => new Promise((resolve, reject) => pending.push({ id, resolve, reject })) } }
  vm.createContext(state)
  vm.runInContext(transpile(source.slice(start, end) + '\nglobalThis.load = loadPhotoFaces;'), state)
  const first = state.load()
  state.props.image = { id: 'new' }
  const second = state.load()
  pending[0].reject(new Error('old request failed')); await first
  assert.equal(state.facesError.value, false)
  assert.equal(state.facesLoading.value, true)
  pending[1].resolve([{ id: 20, photo_id: 'new' }]); await second
  assert.equal(state.photoFaces.value[0].photo_id, 'new')
  state.props.image = { id: 'third' }
  const third = state.load()
  state.props.visible = false; await state.load()
  pending[2].resolve([{ id: 30 }]); await third
  assert.equal(state.photoFaces.value.length, 0)
})

test('default face loading debounces quick photo changes and cancels when viewer closes', () => {
  const source = fs.readFileSync(path.join(root, 'components/PhotoLightbox.vue'), 'utf8')
  const start = source.indexOf('watch([() => props.image?.id, () => props.visible, canShowFaces]')
  const timers = new Map(), reads = []
  let callback, counter = 0
  const state = { props: { image: { id: 'first' }, visible: true }, canShowFaces: ref(true), facesLoadTimer: null, facesRequest: 0,
    photoFaces: ref([]), selectedPhotoFace: ref(null), facesLoading: ref(false), facesError: ref(false), showPersonSelector: ref(false),
    watch(_sources, fn, options) { callback = fn; if (options.immediate) fn() },
    setTimeout(fn) { const id = ++counter; timers.set(id, fn); return id }, clearTimeout(id) { timers.delete(id) },
    loadPhotoFaces() { reads.push(state.props.image.id) } }
  vm.createContext(state)
  vm.runInContext(transpile(source.slice(start, source.indexOf('const saveFaceIdentity =', start))), state)
  assert.equal(reads.length, 0)
  state.props.image = { id: 'second' }; callback()
  state.props.image = { id: 'third' }; callback()
  assert.equal(timers.size, 1)
  for (const fn of timers.values()) fn()
  timers.clear()
  assert.deepEqual(reads, ['third'])
  state.props.image = { id: 'fourth' }; callback()
  state.props.visible = false; callback()
  assert.equal(timers.size, 0)
})
