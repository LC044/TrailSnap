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
  const store = vue.reactive({ availableFilters: { file_types: ['image', 'video', 'live_photo', 'panorama'] },
    selectedFilters: { file_types: ['video'], image_types: [] }, loadPhotos: value => calls.push(value) })
  const calls = []
  const { descriptor } = parse(read('components/FilterPanel.vue'))
  const component = load(compileScript(descriptor, { id: 'filter-test' }).content, {
    '@/stores/photoStore': { usePhotoStore: () => store }, 'lucide-vue-next': { ChevronDown: {} },
    'element-plus': { useZIndex: () => ({ nextZIndex: () => 3000 }) },
    '@/utils/pickerDate': { nextDialogZIndex: next => next() },
    '@/components/PersonAvatar.vue': { default: {} },
    '@/utils/mediaUrl': { thumbnailUrl: id => `/thumb/${id}` },
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
  state.updateFilter('years', [2025])
  state.updateFilter('cities', ['西安市', '三门峡市'])
  state.updateFilter('categories', ['风景'])
  state.updateFilter('people', ['小王'])
  assert.deepEqual(Array.from(store.selectedFilters.years), [2025])
  assert.deepEqual(Array.from(store.selectedFilters.cities), ['西安市', '三门峡市'])
  assert.deepEqual(Array.from(store.selectedFilters.categories), ['风景'])
  assert.deepEqual(Array.from(store.selectedFilters.people), ['小王'])
  assert.deepEqual(calls, [true, true, true, true, true, true])
  store.availableFilters.person_options = [
    { id: 'person-a', name: '未命名', photo_count: 9, photo_id: 'photo-a', face_rect: [0.1, 0.2, 0.4, 0.6] },
    { id: 'person-b', name: '未命名', photo_count: 3 },
    { id: 'person-c', name: '小王', photo_count: 1 },
  ]
  const personIds = state.primaryGroups.find(group => group.key === 'people').options
  assert.deepEqual(Array.from(personIds), ['person-a', 'person-b', 'person-c'])
  state.setSearch('people', '未命名')
  assert.deepEqual(Array.from(state.filteredOptions('people', personIds)), ['person-a', 'person-b'])
  state.updateFilter('people', [])
  state.toggleFilter('people', 'person-a')
  assert.equal(state.isSelected('people', 'person-a'), true)
  assert.equal(state.isSelected('people', 'person-b'), false)
  assert.equal(state.optionLabel('people', 'person-a'), '未命名')
  assert.equal(state.personAvatar('person-a').cover_photo.photo_id, 'photo-a')
  state.raiseOptions(true)
  assert.equal(state.popperStyle.zIndex, 3000)
  for (const [key, query, options, expected] of [
    ['cities', ' 三门 ', ['西安市', '三门峡市'], ['三门峡市']],
    ['people', '小', ['小王', '老李'], ['小王']],
    ['categories', '风', ['风景', '人像'], ['风景']],
    ['years', '2025', [2024, 2025, 2026], [2025]],
  ]) {
    state.setSearch(key, query)
    assert.equal(state.activeGroup, key)
    assert.deepEqual(Array.from(state.filteredOptions(key, options)), expected)
  }
})
