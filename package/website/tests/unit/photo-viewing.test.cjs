const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const vue = require('vue')
const pinia = require('pinia')

function load(file, imports, storage) {
  const source = fs.readFileSync(path.resolve(__dirname, '../../src', file), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  const module = { exports: {} }
  vm.runInNewContext(code, { module, exports: module.exports, localStorage: storage,
    require: name => ({ vue, pinia, ...imports })[name] })
  return module.exports
}

function fixture(saved) {
  const data = new Map(saved === undefined ? [] : [['trailsnap_auto_view_original', saved]])
  const storage = { getItem: key => data.get(key) ?? null, setItem: (key, value) => data.set(key, value) }
  const stores = load('stores/photoViewing.ts', {}, storage)
  pinia.setActivePinia(pinia.createPinia())
  const preferences = stores.usePhotoViewingStore()
  const { useOriginalPhoto } = load('composables/useOriginalPhoto.ts', { '@/stores/photoViewing': stores })
  const props = vue.reactive({ visible: true, image: { id: 'a', url: '/a/original', preview: '/a/preview' } })
  const scope = vue.effectScope()
  const viewer = scope.run(() => useOriginalPhoto(props))
  return { preferences, props, viewer, data, stores, scope }
}

test('default original and disabled preference persist across new sessions', () => {
  const f = fixture()
  assert.equal(f.preferences.autoViewOriginal, true)
  assert.equal(f.viewer.displayImageSrc.value, '/a/original')
  f.preferences.autoViewOriginal = false
  assert.equal(f.viewer.displayImageSrc.value, '/a/preview')
  pinia.setActivePinia(pinia.createPinia())
  const reloaded = f.stores.usePhotoViewingStore()
  assert.equal(reloaded.autoViewOriginal, false)
  reloaded.autoViewOriginal = true
  assert.equal(f.data.get('trailsnap_auto_view_original'), 'true')
  f.scope.stop()
})

test('manual overrides only affect the current viewing, for either saved preference', () => {
  for (const saved of ['true', 'false']) {
    const f = fixture(saved)
    const expected = saved === 'true'
    f.viewer.toggleOriginal()
    assert.equal(f.viewer.showOriginal.value, !expected)
    assert.equal(f.preferences.autoViewOriginal, expected)
    // A metadata update for the same photo keeps the manual choice.
    f.props.image = { ...f.props.image, title: 'updated' }
    assert.equal(f.viewer.showOriginal.value, !expected)
    f.props.image = { id: 'b', url: '/b/original', preview: '/b/preview' }
    assert.equal(f.viewer.displayImageSrc.value, expected ? '/b/original' : '/b/preview')
    f.viewer.toggleOriginal()
    f.props.visible = false
    f.props.visible = true
    assert.equal(f.viewer.showOriginal.value, expected)
    f.scope.stop()
  }
})

test('missing preview falls back to original and missing photo has no URL', () => {
  const f = fixture('false')
  f.props.image = { id: 'b', url: '/b/original' }
  assert.equal(f.viewer.displayImageSrc.value, '/b/original')
  f.props.image = null
  assert.equal(f.viewer.displayImageSrc.value, '')
  f.scope.stop()
})

test('storage failure preserves usable session controls', () => {
  const stores = load('stores/photoViewing.ts', {}, {
    getItem() { throw Error('blocked') }, setItem() { throw Error('quota') },
  })
  pinia.setActivePinia(pinia.createPinia())
  const preferences = stores.usePhotoViewingStore()
  assert.equal(preferences.autoViewOriginal, true)
  preferences.autoViewOriginal = false
  assert.equal(preferences.autoViewOriginal, false)
})
