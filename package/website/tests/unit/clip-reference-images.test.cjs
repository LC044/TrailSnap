const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const vue = require('vue')
const compiler = require('vue/compiler-sfc')

function load(filename, dependencies = {}, globals = {}) {
  const source = fs.readFileSync(path.resolve(__dirname, '../../src/components', filename), 'utf8')
  const script = compiler.compileScript(compiler.parse(source).descriptor, { id: filename }).content
  const code = ts.transpileModule(script, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const module = { exports: {} }
  vm.runInThisContext('(function(require,module,exports,URL,document){' + code + '\n})')(
    name => {
      if (name === 'vue') return vue
      if (name in dependencies) return dependencies[name]
      if (name === 'lucide-vue-next' || name.endsWith('.vue')) return {}
      throw new Error(name)
    }, module, module.exports, globals.URL || URL, globals.document,
  )
  return module.exports.default
}
const renderer = vue.createRenderer({ insert() {}, remove() {}, createElement: () => ({}), createText: () => ({}),
  createComment: () => ({}), setText() {}, setElementText() {}, parentNode: () => null, nextSibling: () => null, patchProp() {} })
function mount(component, props = {}, events = {}) {
  let state
  const app = renderer.createApp({ ...component, render: () => null, setup(props, ctx) { state = component.setup(props, ctx); return state } }, { ...props, ...events })
  app.mount({})
  return { state, unmount: () => app.unmount() }
}
function manager(api = {}) {
  const revoked = [], saves = []
  let sequence = 0
  const component = load('ClipCategoryManager.vue', {
    'element-plus': { ElMessage: { success() {} }, ElMessageBox: {} },
    '@/api/classification': { clipClassificationService: { list: async () => ({ categories: [], groups: [] }), save: async (...args) => saves.push(args), ...api } },
    '@/stores/photoStore': { mapPhotoToImage: x => x, useClipReferencePhotosStore: () => ({ selectedFilters: {} }) },
  }, { URL: { createObjectURL: () => `blob:${++sequence}`, revokeObjectURL: url => revoked.push(url) } })
  return { ...mount(component, { modelValue: false }), revoked, saves }
}
const file = () => new Blob(['image'], { type: 'image/jpeg' })

test('multiple uploads crop sequentially, retain accepted images on cancellation, and release URLs', async () => {
  const ctx = manager()
  ctx.state.edit()
  ctx.state.selectFiles({ target: { files: [file(), file()], value: 'files' } })
  await vue.nextTick()
  assert.equal(ctx.state.cropping.value, true)
  ctx.state.useCrop('data:first')
  await vue.nextTick()
  assert.deepEqual(ctx.state.draft.value.reference_images, ['data:first'])
  assert.equal(ctx.state.cropSource.value, 'blob:2')
  ctx.state.cancelCrop()
  assert.deepEqual(ctx.state.draft.value.reference_images, ['data:first'])
  assert.deepEqual(ctx.revoked, ['blob:1', 'blob:2'])
  ctx.unmount()
})

test('editing clones reference images and supports recropping, new groups, and image-only save', async () => {
  const ctx = manager()
  const original = { id: 'cat', name: '照片', groups: ['旧分组'], descriptions: [], reference_images: ['data:old'], strictness: 'standard', thresholds: { test: .5 }, revision: 1, enabled: false }
  ctx.state.edit(original)
  ctx.state.recrop(0)
  ctx.state.useCrop('data:new')
  ctx.state.draft.value.groups = [' 新分组 ', '新分组']
  await ctx.state.save()
  assert.deepEqual(original.reference_images, ['data:old'])
  assert.deepEqual(ctx.saves[0][1].reference_images, ['data:new'])
  assert.deepEqual(ctx.saves[0][1].groups, ['新分组'])
  assert.deepEqual(ctx.saves[0][1].descriptions, [])
  ctx.unmount()
})

test('empty rules and too many files are rejected before saving or cropping', async () => {
  const ctx = manager()
  ctx.state.edit()
  ctx.state.draft.value.name = '照片'
  await ctx.state.save()
  assert.equal(ctx.saves.length, 0)
  assert.match(ctx.state.editError.value, /至少添加/)
  ctx.state.selectFiles({ target: { files: Array.from({ length: 6 }, file), value: '' } })
  assert.match(ctx.state.editError.value, /最多添加 5 张/)
  assert.equal(ctx.state.cropping.value, false)
  ctx.unmount()
})

test('a gallery response arriving after closing the editor cannot add a stale reference', async () => {
  let resolve
  const ctx = manager({ referencePhoto: () => new Promise(r => { resolve = r }) })
  ctx.state.edit()
  ctx.state.selectPhotos(['photo'])
  assert.equal(ctx.state.imageLoading.value, true)
  ctx.state.editing.value = false
  await vue.nextTick()
  resolve(file())
  await vue.nextTick()
  assert.equal(ctx.state.cropping.value, false)
  assert.equal(ctx.state.cropSource.value, '')
  assert.deepEqual(ctx.state.draft.value.reference_images, [])
  ctx.unmount()
})

test('crop coordinates export only the chosen region, scale to 768px, and emit a JPEG', () => {
  const draw = [], events = []
  const canvas = { width: 0, height: 0, getContext: () => ({ fillRect() {}, drawImage: (...args) => draw.push(args) }), toDataURL: type => `data:${type};base64,crop` }
  const component = load('ClipReferenceCropper.vue', {}, { document: { createElement: () => canvas } })
  const ctx = mount(component, { modelValue: true, source: 'blob:source' }, { onConfirm: value => events.push(value) })
  ctx.state.ready.value = true
  ctx.state.photo.value = { naturalWidth: 4000, naturalHeight: 2000 }
  ctx.state.box.value = { x: 25, y: 25, width: 50, height: 50 }
  ctx.state.confirm()
  assert.deepEqual(draw[0].slice(1), [1000, 500, 2000, 1000, 0, 0, 768, 384])
  assert.deepEqual(events, ['data:image/jpeg;base64,crop'])
  ctx.unmount()
})
