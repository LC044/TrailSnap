const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const vue = require('vue')
const { parse, compileScript, compileTemplate } = require('vue/compiler-sfc')

const read = file => fs.readFileSync(path.resolve(__dirname, '../../src', file), 'utf8')
function load(source, dependencies = {}, globals = {}) {
  const module = { exports: {} }
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  vm.runInNewContext(code, { module, exports: module.exports, ...globals, require: name => {
    if (name === 'vue') return vue
    if (name in dependencies) return dependencies[name]
    throw new Error(`Unexpected import: ${name}`)
  } })
  return module.exports
}
const helpers = load(read('utils/mediaTypeFilters.ts'))

test('cached panorama toggle becomes a file type without a hidden AND condition', () => {
  const cached = { file_types: ['video'], is_panorama: true, years: [2026] }
  const localStorage = { getItem: () => JSON.stringify({ timestamp: Date.now(), data: cached }), setItem() {} }
  const store = load(read('stores/photoStore.ts'), {
    pinia: { defineStore: () => {} }, '@/api/album': {}, '@/api/search': {},
    '@/config/server': {}, '@/utils/mediaUrl': {}, '@/utils/mediaTypeFilters': helpers,
  }, { localStorage }).photoStoreSetup()
  assert.deepEqual(Array.from(store.selectedFilters.file_types), ['video', 'panorama'])
  assert.equal('is_panorama' in store.selectedFilters, false)
  assert.deepEqual(Array.from(store.getPickerSearchFilters().file_types), ['video', 'panorama'])
  store.selectedFilters.file_types.splice(1, 1)
  assert.deepEqual(Array.from(store.getPickerSearchFilters().file_types), ['video'])
})

test('photo routes accept new virtual types and upgrade old panorama links', () => {
  const source = read('views/PhotosPage.vue')
  const functions = source.slice(source.indexOf('const parseQueryFilter ='), source.indexOf("let lastQueryStr ="))
  for (const [query, expected] of [
    [{ file_types: 'video,panorama' }, ['video', 'panorama']],
    [{ file_types: ['video', 'panorama'], is_panorama: 'true' }, ['video', 'panorama']],
    [{ is_panorama: 'true' }, ['panorama']],
    [{ file_types: 'video', is_panorama: 'true' }, ['video', 'panorama']],
    [{}, []],
  ]) {
    const selectedFilters = {}
    load(functions + '\napplyQueryFilters()', {}, {
      route: { query }, photoStore: { selectedFilters }, ...helpers,
    })
    assert.deepEqual(Array.from(selectedFilters.file_types), expected)
    assert.equal('is_panorama' in selectedFilters, false)
  }
})

test('all four type buttons use the same selection state and reload behavior', () => {
  const store = { availableFilters: { file_types: ['image', 'video', 'live_photo', 'panorama'] },
    selectedFilters: { file_types: ['video'], image_types: [] }, loadPhotos: value => calls.push(value) }
  const calls = []
  const { descriptor } = parse(read('components/FilterPanel.vue'))
  const component = load(compileScript(descriptor, { id: 'filter-test' }).content, {
    '@/stores/photoStore': { usePhotoStore: () => store }, 'lucide-vue-next': { ChevronDown: {} },
  }).default
  const state = vue.proxyRefs(component.setup({ store }, { expose() {} }))
  const template = compileTemplate({ source: descriptor.template.content, filename: 'FilterPanel.vue', id: 'filter-test' })
  assert.deepEqual(template.errors, [])
  const { render } = load(template.code)
  function buttons(node, result = []) {
    if (node?.props?.['data-testid']?.startsWith('filter-type-')) result.push(node)
    if (Array.isArray(node?.children)) node.children.forEach(child => buttons(child, result))
    return result
  }
  let types = buttons(render(state, []))
  assert.equal(types.length, 4)
  types[3].props.onClick()
  assert.deepEqual(store.selectedFilters.file_types, ['video', 'panorama'])
  types = buttons(render(state, []))
  assert.equal(types[1].props['aria-pressed'], true)
  assert.equal(types[3].props['aria-pressed'], true)
  types[3].props.onClick()
  assert.deepEqual(store.selectedFilters.file_types, ['video'])
  assert.deepEqual(calls, [true, true])
})
