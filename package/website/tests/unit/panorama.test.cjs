const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const vue = require('vue')
const { parse, compileScript, compileTemplate } = require('vue/compiler-sfc')

function load(source, dependencies = {}) {
  const module = { exports: {} }
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const context = vm.createContext({ module, exports: module.exports, require: name => {
    if (name === 'vue') return vue
    if (name in dependencies) return dependencies[name]
    throw new Error(`Unexpected import: ${name}`)
  }, navigator: { deviceMemory: 8 }, URL, AbortController, setTimeout, clearTimeout, document: { createElement: () => ({ getContext: () => ({
    MAX_TEXTURE_SIZE: 1, getParameter: () => 16384, getExtension: () => ({ loseContext() {} }),
  }) }) } })
  vm.runInContext(code, context)
  return module.exports
}
const read = file => fs.readFileSync(path.resolve(__dirname, '../../src', file), 'utf8')
const helpers = load(read('utils/panorama.ts'))
const full = { fullWidth: 8192, fullHeight: 4096, croppedWidth: 8192, croppedHeight: 4096, croppedX: 0, croppedY: 0 }

test('panorama isolates gesture starts but lets touch movement and release reach window', () => {
  const { descriptor } = parse(read('components/PanoramaViewer.vue'))
  const template = compileTemplate({ source: descriptor.template.content, filename: 'PanoramaViewer.vue', id: 'panorama-touch' })
  assert.deepEqual(template.errors, [])
  const { render } = load(template.code)
  const root = render({ active: true, busy: false, message: '' }, [])
  const surface = root.children.find(child => child.type === 'div' && child.props?.onTouchstart)
  assert.ok(surface)
  assert.match(surface.props.class, /\btouch-none\b/)
  for (const name of ['onTouchstart', 'onMousedown', 'onClick', 'onWheel']) {
    let stopped = false
    surface.props[name]({ stopPropagation() { stopped = true } })
    assert.equal(stopped, true, `${name} must not start a lightbox gesture`)
  }
  // Photo Sphere Viewer listens on window, beyond the lightbox's media surface.
  for (const name of ['onTouchmove', 'onTouchend', 'onMousemove', 'onMouseup']) {
    assert.equal(surface.props[name], undefined, `${name} must reach the viewer's window listener`)
  }
})

test('panorama texture coordinates preserve complete and partial spherical canvases', () => {
  const result = helpers.textureGeometry(full, 8192, 4096)
  assert.equal(result.fullWidth, 4096)
  assert.equal(result.croppedHeight, 2048)
  const crop = { ...full, croppedWidth: 4096, croppedHeight: 2048, croppedX: 2048, croppedY: 1024 }
  const partial = helpers.textureGeometry(crop, 4096, 2048)
  assert.equal(partial.fullWidth, 4096)
  assert.equal(partial.croppedWidth, 2048)
  assert.equal(partial.croppedX, 1024)
  assert.equal(partial.croppedY, 512)
  assert.equal(helpers.textureGeometry(full, 8192, 4096, true).fullWidth, 8192)
})
test('high resolution obeys texture dimensions, pixel budget, and device memory', () => {
  assert.equal(helpers.canUseHighResolution(8192, 4096, 16384, 8), true)
  assert.equal(helpers.canUseHighResolution(8192, 4096, 4096, 8), false)
  assert.equal(helpers.canUseHighResolution(8192, 4096, 16384, 2), false)
  assert.equal(helpers.canUseHighResolution(16384, 8192, 32768, 16), false)
  assert.equal(helpers.canUseHighResolution(4096, 2048, 16384, 8), false)
})

function deferred() { let resolve; const promise = new Promise(done => { resolve = done }); return { promise, resolve } }
const flush = async () => { for (let i = 0; i < 15; i++) await Promise.resolve(); await vue.nextTick() }
function mount(api, autoViewOriginal = true) {
  const { descriptor } = parse(read('components/PanoramaViewer.vue'))
  const script = compileScript(descriptor, { id: 'panorama-unit' })
  const component = load(script.content, { '@/api/panorama': { panoramaApi: api }, '@/utils/panorama': helpers,
    '@/stores/photoViewing': { usePhotoViewingStore: () => ({ autoViewOriginal }) }, 'lucide-vue-next': { LoaderCircle: {}, RotateCcw: {} },
    '@photo-sphere-viewer/core': { Viewer: class {}, EquirectangularAdapter: {} }, '@photo-sphere-viewer/core/index.css': {} }).default
  component.render = () => null
  const renderer = vue.createRenderer({ createElement: () => ({}), insert() {}, remove() {}, patchProp() {},
    setElementText() {}, createText: () => ({}), setText() {}, createComment: () => ({}), setComment() {},
    parentNode: () => null, nextSibling: () => null })
  const updates = [], active = []
  const app = renderer.createApp(component, { photoId: 'photo', onState: value => updates.push(value), onActive: value => active.push(value) })
  const instance = app.mount({})
  return { state: instance.$.setupState, app, updates, active }
}

test('first panorama texture follows automatic originals without an extra standard request', async () => {
  for (const autoViewOriginal of [true, false]) {
    const requests = []
    const mounted = mount({
      info: async () => ({ projection: 'equirectangular', geometry: full, width: 8192, height: 4096 }),
      image: (_id, high) => { requests.push(high); return new Promise(() => {}) },
    }, autoViewOriginal)
    await flush()
    assert.deepEqual(requests, [autoViewOriginal])
    assert.equal(mounted.state.high, autoViewOriginal)
    mounted.app.unmount()
  }
})

test('default original preference still respects the device texture limit', async () => {
  const requests = []
  const mounted = mount({
    info: async () => ({ projection: 'equirectangular', geometry: full, width: 8192, height: 4096 }),
    image: (_id, high) => { requests.push(high); return new Promise(() => {}) },
  })
  mounted.state.maxTexture = 4096
  await flush()
  assert.equal(mounted.state.allowHigh, false)
  assert.deepEqual(requests, [false])
  mounted.app.unmount()
})

test('manual panorama quality switching remains available when automatic originals are disabled', async () => {
  const requests = []
  const mounted = mount({
    info: async () => ({ projection: 'equirectangular', geometry: full, width: 8192, height: 4096 }),
    image: (_id, high) => { requests.push(high); return new Promise(() => {}) },
  }, false)
  await flush()
  mounted.state.busy = false
  mounted.state.toggleHigh()
  await flush()
  assert.deepEqual(requests, [false, true])
  mounted.app.unmount()
})
test('unmounted viewer ignores late metadata and aborts its request', async () => {
  const pending = deferred(); let signal
  const mounted = mount({ info: (_id, s) => { signal = s; return pending.promise } })
  mounted.app.unmount()
  assert.equal(signal.aborted, true)
  pending.resolve({ projection: 'equirectangular', geometry: full, width: 8192, height: 4096 })
  await flush()
  assert.equal(mounted.updates.some(value => value.available), false)
  assert.equal(mounted.active.at(-1), false)
})
test('metadata failure stays in flat mode and can be retried', async () => {
  let calls = 0
  const mounted = mount({ info: async () => {
    if (++calls === 1) throw new Error('network')
    return { projection: null, geometry: null, width: 8192, height: 4096 }
  } })
  await flush()
  assert.equal(mounted.state.active, false)
  assert.match(mounted.state.message, /读取失败/)
  await mounted.state.loadInfo()
  assert.equal(mounted.state.message, '')
  assert.equal(mounted.state.info.projection, null)
  mounted.app.unmount()
})

test('a stalled metadata request times out, aborts, and ignores its late response', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const pending = deferred(); let signal
  const mounted = mount({ info: (_id, value) => { signal = value; return pending.promise } })
  assert.equal(mounted.state.busy, true)
  t.mock.timers.tick(25001)
  await flush()
  assert.equal(signal.aborted, true)
  assert.equal(mounted.state.busy, false)
  assert.match(mounted.state.message, /超时/)
  pending.resolve({ projection: 'equirectangular', geometry: full, width: 8192, height: 4096 })
  await flush()
  assert.equal(mounted.state.info, null)
  assert.equal(mounted.state.active, false)
  mounted.app.unmount()
})

test('a stalled texture request times out without leaving an active viewer', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const pending = deferred(); let signal
  const mounted = mount({
    info: async () => ({ projection: 'equirectangular', geometry: full, width: 8192, height: 4096 }),
    image: (_id, _high, value) => { signal = value; return pending.promise },
  })
  await flush()
  assert.equal(mounted.state.busy, true)
  t.mock.timers.tick(25001)
  await flush()
  assert.equal(signal.aborted, true)
  assert.equal(mounted.state.active, false)
  assert.equal(mounted.state.busy, false)
  pending.resolve(new Blob(['texture'], { type: 'image/jpeg' }))
  await flush()
  assert.equal(mounted.state.viewer, undefined)
  mounted.app.unmount()
})

test('a missing render container settles as an error instead of an endless loader', async () => {
  const mounted = mount({
    info: async () => ({ projection: 'equirectangular', geometry: full, width: 8192, height: 4096 }),
    image: async () => new Blob(['texture'], { type: 'image/jpeg' }),
  })
  await flush()
  assert.equal(mounted.state.busy, false)
  assert.equal(mounted.state.active, false)
  assert.match(mounted.state.message, /加载失败/)
  mounted.app.unmount()
})
