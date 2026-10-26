const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const vue = require('vue')
const compiler = require('vue/compiler-sfc')

// Mount the real image-stage template, leaving the rest of the lightbox's
// network/sidebar dependencies outside this focused DOM identity regression.
const source = fs.readFileSync(path.resolve(__dirname, '../../src/components/PhotoLightbox.vue'), 'utf8')
const { descriptor } = compiler.parse(source)
function findStage(node) {
  if (node.tag === 'div' && node.props?.some(prop => prop.name === 'if' && prop.exp?.content.includes("image.file_type === 'live_photo'"))) return node
  for (const child of node.children || []) {
    const found = findStage(child)
    if (found) return found
  }
}
const stage = findStage(descriptor.template.ast)
const compiled = compiler.compileTemplate({ source: stage.loc.source, filename: 'PhotoLightbox.vue', id: 'photo-stage' })
assert.deepEqual(compiled.errors, [])
const code = ts.transpileModule(compiled.code, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
const moduleObject = { exports: {} }
vm.runInNewContext(code, { module: moduleObject, exports: moduleObject.exports, require: () => vue })

const renderer = vue.createRenderer({
  createElement: tag => ({ tag, props: {}, children: [] }),
  createText: text => ({ text }), createComment: text => ({ text }),
  patchProp: (el, key, _old, value) => { el.props[key] = value },
  insert(el, parent, anchor) {
    if (el.parent) this.remove(el)
    const index = anchor ? parent.children.indexOf(anchor) : -1
    if (index < 0) parent.children.push(el); else parent.children.splice(index, 0, el)
    el.parent = parent
  },
  remove(el) { if (el.parent) el.parent.children.splice(el.parent.children.indexOf(el), 1); el.parent = null },
  setElementText: (el, text) => { el.text = text }, setText: (el, text) => { el.text = text },
  parentNode: el => el.parent, nextSibling: el => el.parent?.children[el.parent.children.indexOf(el) + 1],
})
function fixture() {
  const photo = id => ({ id, url: `/${id}/original`, preview: `/${id}/preview`, file_type: 'image' })
  const state = vue.reactive({
    image: photo('a'), displayImageSrc: '/a/original', scale: 1, translateX: 0, translateY: 0,
    adjacentPreviewSrc: item => item.preview || item.url, startDrag() {},
    highlightedFace: null, photoFaces: [], canShowFaces: false, highlightedOCR: null, showOCR: false, ocrRecords: [], isPlayingLive: false,
    currentImageLoaded: false, onCurrentImageLoad() {},
    isDragging: false, isPinching: false,
  })
  const root = { children: [] }
  const app = renderer.createApp({ setup: () => state, render: moduleObject.exports.render })
  app.mount(root)
  const find = (node, id) => node.props?.['data-testid'] === id ? node : node.children?.map(child => find(child, id)).find(Boolean)
  return { state, app, photo, current: () => find(root, 'photo-lightbox-current-image'), preview: () => find(root, 'photo-lightbox-preview') }
}

test('switching photos never reuses the old bitmap node while the new original loads', async () => {
  const f = fixture()
  const old = f.current()
  old.decodedBitmap = 'a'
  f.state.image = f.photo('b'); f.state.displayImageSrc = '/b/original'
  await vue.nextTick()
  assert.notEqual(f.current(), old)
  assert.equal(f.current().decodedBitmap, undefined)
  assert.equal(f.preview().props.src, '/b/preview')
  f.state.image = f.photo('c'); f.state.displayImageSrc = '/c/original'
  await vue.nextTick()
  assert.equal(f.preview().props.src, '/c/preview')
  f.state.currentImageLoaded = true
  await vue.nextTick()
  assert.equal(f.preview(), undefined, 'decoded originals must not retain a preview underneath transparent pixels')
  f.app.unmount()
})

test('manual quality switching replaces the main bitmap but retains the same photo preview', async () => {
  const f = fixture()
  const original = f.current()
  f.state.displayImageSrc = '/a/preview'
  await vue.nextTick()
  assert.notEqual(f.current(), original)
  assert.equal(f.current().props.src, '/a/preview')
  assert.equal(f.preview(), undefined)
  f.state.displayImageSrc = '/a/original'
  await vue.nextTick()
  assert.equal(f.preview().props.src, '/a/preview')
  f.app.unmount()
})
