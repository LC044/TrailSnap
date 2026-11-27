const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const vue = require('vue')
const compiler = require('vue/compiler-sfc')

function load(filename, dependencies = {}, storage = {}, crypto = { randomUUID: () => 'context-id' }) {
  let source = fs.readFileSync(path.resolve(__dirname, '../../src', filename), 'utf8')
  if (filename.endsWith('.vue')) {
    source = compiler.compileScript(compiler.parse(source).descriptor, { id: filename }).content
  }
  const code = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText
  const module = { exports: {} }
  vm.runInThisContext('(function(require,module,exports,sessionStorage,crypto){' + code + '\n})')(
    name => {
      if (name === 'vue') return vue
      if (name === 'lucide-vue-next' || name.endsWith('.vue')) return {}
      if (name === './toolPlanDisplay') return load('views/toolbox/toolPlanDisplay.ts')
      if (name in dependencies) return dependencies[name]
      throw new Error(name)
    }, module, module.exports, storage, crypto,
  )
  return module.exports
}

const renderer = vue.createRenderer({
  insert() {}, remove() {}, createElement: () => ({}), createText: () => ({}), createComment: () => ({}),
  setText() {}, setElementText() {}, parentNode: () => null, nextSibling: () => null, patchProp() {},
})
function mount(component, props = {}, events = {}) {
  let state
  const original = component.setup
  const wrapped = { ...component, render: () => null, setup(props, context) {
    state = original(props, context)
    return state
  } }
  const app = renderer.createApp({ render: () => vue.h(wrapped, { ...props, ...events }) })
  app.mount({})
  return { get state() { return state }, unmount: () => app.unmount() }
}
const api = () => load('api/toolboxWorkflows.ts', { '@/utils/request': {} })
const deferred = () => {
  let resolve
  const promise = new Promise(r => { resolve = r })
  return { promise, resolve }
}

test('cleanup retains server selection while appending results and references', async () => {
  const calls = []
  const plan = vue.reactive({ id: 'scan-one', kind: 'cleanup', version: 1, status: 'preview',
    summary: { phase: 'done', total: 30001, candidate: 20001 },
    request: { scope: api().emptyScope(), config: api().defaultConfig('cleanup') } })
  const workflowApi = {
    items: async (_id, offset) => {
      calls.push(['items', offset])
      return { total: 2, selected_count: offset ? 10002 : 10001,
        items: [{ id: 7 + offset, selected: false, photo_id: 'photo-' + offset, status: 'candidate', detail: { group_id: 2 + offset } }] }
    },
    selection: async (...args) => { calls.push(['selection', ...args]); return { selected_count: 10002 } },
    members: async (...args) => { calls.push(['members', ...args]); return { total: 3000, representative_id: 'representative', items: [{ photo_id: 'reference-' + args[2], in_scope: false }] } },
  }
  const component = load('views/toolbox/ToolPlanPreview.vue', {
    '@/api/toolboxWorkflows': { workflowApi }, '@/utils/mediaUrl': { thumbnailUrl: id => id },
    'element-plus': { ElMessage: { error() {} } },
  }).default
  const ctx = mount(component, { plan, executing: false })
  await ctx.state.load()
  assert.equal(ctx.state.selectedCount.value, 10001)
  await ctx.state.toggle(7, true)
  assert.equal(ctx.state.selectedCount.value, 10002)
  assert.equal(ctx.state.isSelected(ctx.state.rows.value[0]), true)
  assert.deepEqual(calls.find(call => call[0] === 'selection').slice(2), [[7], true])
  assert.equal(ctx.state.photoGroups.value.length, 1)
  assert.equal(ctx.state.photoGroups.value[0].groupId, 2)
  await ctx.state.load()
  assert.deepEqual(calls.filter(call => call[0] === 'items'), [['items', 0], ['items', 1]])
  assert.deepEqual(ctx.state.rows.value.map(item => item.id), [7, 8])
  assert.equal(ctx.state.isSelected(ctx.state.rows.value[0]), true)
  await ctx.state.loadReferences(2)
  await ctx.state.loadReferences(2)
  assert.deepEqual(calls.filter(call => call[0] === 'members').map(call => call[3]), [0, 1])
  assert.deepEqual(ctx.state.references.value[2].items.map(item => item.photo_id), ['reference-0', 'reference-1'])
  ctx.unmount()
})

test('new scope is empty, and directory cancellation does not select a folder', async () => {
  const scope = api().emptyScope()
  assert.equal(scope.source, 'all')
  const updates = []
  const component = load('views/toolbox/MediaScopeSelector.vue', {
    '@/api/album': { albumService: {} },
    '@/stores/user': { useUserStore: () => ({ userInfo: { id: 'owner' } }) },
    '@/stores/selectionStore': { useSelectionStore: () => ({}) },
  }).default
  const ctx = mount(component, { scope, count: null, checking: false }, {
    'onUpdate:scope': value => updates.push(value),
  })
  assert.equal(ctx.state.valid.value, true)
  ctx.state.folderPicker.value = true
  await vue.nextTick()
  ctx.state.folderPicker.value = false
  await vue.nextTick()
  assert.equal(updates.length, 0)
  ctx.state.addFolder('E:/Photos/2026')
  assert.deepEqual(updates[0].folders, ['E:/Photos/2026'])
  assert.deepEqual(scope.folders, [])
  ctx.unmount()
})

test('rename variables insert at the cursor and unknown variables are rejected', async () => {
  const config = api().defaultConfig('rename')
  config.template = 'before_after'
  const component = load('views/toolbox/RenameTemplateEditor.vue', { '@/api/toolboxWorkflows': api() }).default
  const ctx = mount(component, { modelValue: config })
  const selections = []
  ctx.state.input.value = {
    input: { selectionStart: 7, selectionEnd: 7, setSelectionRange: (...args) => selections.push(args) },
    focus() {},
  }
  ctx.state.rememberCursor()
  await ctx.state.insert('date')
  assert.equal(config.template, 'before_{date}after')
  assert.deepEqual(selections, [[13, 13]])
  config.template = '{date}_{date}'
  assert.equal(ctx.state.templateError.value, '')
  config.template = '{unknown}'
  // defineModel returns the parent value; make it reactive for validation.
  assert.match(ctx.state.config.value.template, /unknown/)
  ctx.unmount()
  const invalid = mount(component, { modelValue: vue.reactive({ ...config }) })
  assert.match(invalid.state.templateError.value, /未知变量/)
  invalid.unmount()
})

test('rename template error names the broken placeholder', () => {
  const { renameTemplateError } = api()
  assert.match(renameTemplateError('IMG_{date}_{time'), /未闭合的变量占位符/)
  assert.match(renameTemplateError('IMG_{date}_{time'), /\{time/)
  assert.match(renameTemplateError('IMG_{unknown}'), /未知变量：unknown/)
  assert.equal(renameTemplateError('IMG_{date}_{time}'), '')
})

test('account changes discard old pending preference responses', async () => {
  const pending = deferred()
  const user = vue.reactive({ userInfo: { id: 'one' } })
  const store = load('stores/toolbox.ts', {
    pinia: { defineStore: (_name, setup) => setup },
    '@/stores/user': { useUserStore: () => user },
    '@/api/toolboxWorkflows': { workflowApi: { preferences: () => pending.promise } },
  }).useToolboxStore()
  const result = store.load().catch(error => error)
  user.userInfo.id = 'two'
  await vue.nextTick()
  pending.resolve({ version: 1, presets: [{ name: 'Private' }], recent: [], default_rename_id: null })
  assert.ok(await result instanceof Error)
  assert.equal(store.preferences.value.presets.length, 0)
  assert.equal(store.loadedOwner.value, '')
})

test('selection entry freezes explicit deduplicated IDs and account context', () => {
  const saved = new Map()
  const entry = load('utils/toolboxEntry.ts', {
    '@/api/toolboxWorkflows': api(),
  }, { setItem: (key, value) => saved.set(key, value), getItem: key => saved.get(key) })
  const calls = []
  entry.openToolForSelection({ push: value => calls.push(value) }, 'owner', ['a', 'a', 'b'], 'organize')
  assert.deepEqual(entry.readToolboxScope('context-id', 'owner').photo_ids, ['a', 'b'])
  assert.equal(entry.readToolboxScope('context-id', 'other'), null)
  const expired = JSON.parse(saved.get('trailsnap:toolbox:context:context-id'))
  expired.created -= 16 * 60 * 1000
  saved.set('trailsnap:toolbox:context:context-id', JSON.stringify(expired))
  assert.equal(entry.readToolboxScope('context-id', 'owner'), null)
  assert.equal(calls[0].path, '/toolbox/organize')
  entry.openToolForSelection({ push: value => calls.push(value) }, 'owner', [], 'rename')
  assert.equal(calls.length, 1)
})

test('selection and folder shortcuts work on HTTP with session storage blocked', () => {
  const blocked = () => { throw new Error('session storage unavailable') }
  let nextByte = 1
  const entry = load('utils/toolboxEntry.ts', { '@/api/toolboxWorkflows': api() },
    { setItem: blocked, getItem: blocked }, { getRandomValues: bytes => bytes.fill(nextByte++) })
  const router = { push: value => value }
  const organize = entry.openToolForSelection(router, 'owner', ['a'], 'organize')
  const rename = entry.openToolForFolder(router, 'owner', 'E:/Photos', 'rename')
  assert.equal(organize.path, '/toolbox/organize')
  assert.equal(rename.path, '/toolbox/rename')
  assert.notEqual(organize.query.context, rename.query.context)
  assert.deepEqual(entry.readToolboxScope(organize.query.context, 'owner').photo_ids, ['a'])
  assert.deepEqual(entry.readToolboxScope(rename.query.context, 'owner').folders, ['E:/Photos'])
  assert.equal(entry.readToolboxScope(organize.query.context, 'other'), null)
})

test('organize preserves file decisions and normalizes removed advanced settings', () => {
  const config = vue.reactive(api().defaultConfig('organize'))
  config.target = '/photos'; config.action = 'move'; config.layout = 'preserve'; config.missing = 'upload'
  const component = load('views/toolbox/OrganizeRuleEditor.vue', { '@/api/toolboxWorkflows': api() }).default
  const ctx = mount(component, { modelValue: config, scope: api().emptyScope() })
  ctx.state.applyPreset('year-city')
  assert.deepEqual(config.rules.map(r => r.strategy), ['time', 'location'])
  assert.equal(config.target, '/photos')
  assert.equal(config.action, 'move')
  assert.equal(config.layout, 'rebuild')
  assert.equal(config.missing, 'skip')
  assert.equal(config.multi_group, 'skip')
  assert.equal(ctx.state.currentPreset.value, 'year-city')
  config.rules[1].groups = ['city-id']
  assert.equal(ctx.state.currentPreset.value, undefined)
  for (const [id, path] of [
    ['year', '2025'], ['day', '2025/05/04'], ['country-province-city', '中国/浙江省/杭州市'],
    ['city-district', '杭州市/西湖区'], ['person', '小林'], ['category', '旅行'],
  ]) {
    ctx.state.applyPreset(id)
    assert.equal(ctx.state.currentPreset.value, id)
    assert.equal(ctx.state.exampleTarget.value, `/photos/${path}/IMG_0001.jpg`)
  }
  ctx.unmount()
})

test('toolbox restores user identity from a token before loading empty presets', async () => {
  const user = vue.reactive({ token: 'session', userInfo: null })
  const calls = []
  user.getUserInfo = async () => { calls.push('user'); user.userInfo = { id: 'restored' } }
  const store = load('stores/toolbox.ts', {
    pinia: { defineStore: (_name, setup) => setup },
    '@/stores/user': { useUserStore: () => user },
    '@/api/toolboxWorkflows': { workflowApi: { preferences: async () => {
      calls.push('preferences')
      return { version: 0, presets: [], recent: [], default_rename_id: null }
    } } },
  }).useToolboxStore()
  await store.load()
  assert.deepEqual(calls, ['user', 'preferences'])
  assert.equal(store.loadedOwner.value, 'restored')
  assert.deepEqual(store.preferences.value.presets, [])
})

test('rename style switches between simple choices and custom rules without accumulating tokens', () => {
  const config = vue.reactive(api().defaultConfig('rename'))
  const component = load('views/toolbox/RenameTemplateEditor.vue', { '@/api/toolboxWorkflows': api() }).default
  const ctx = mount(component, { modelValue: config })
  ctx.state.chooseStyle('custom')
  assert.equal(ctx.state.selectedStyle.value, 'custom')
  config.template = '{date}{city}{sequence3}'
  ctx.state.chooseStyle('IMG_{date}_{time}')
  assert.equal(config.template, 'IMG_{date}_{time}')
  assert.equal(ctx.state.selectedStyle.value, 'IMG_{date}_{time}')
  ctx.unmount()
})

test('active tasks open each cleanup mode and undo in the matching tool with its plan', () => {
  const calls = []
  const component = load('views/toolbox/ToolboxHomePage.vue', {
    'element-plus': {},
    '@/utils/mediaUrl': { thumbnailUrl: id => id },
    'vue-router': { useRouter: () => ({ push: value => calls.push(value) }), useRoute: () => ({ query: {} }) },
    '@/api/toolboxWorkflows': { workflowApi: { history: async () => [] } },
  }).default
  const ctx = mount(component)
  for (const [mode, path] of [['duplicate', '/toolbox/duplicate'], ['similar', '/toolbox/similar'], ['quality', '/toolbox/cleanup']]) {
    ctx.state.open({ id: mode, kind: 'cleanup', request: { config: { cleanup_mode: mode } } })
    assert.deepEqual(calls.at(-1), { path, query: { plan: mode } })
  }
  ctx.state.open({ id: 'undo', kind: 'undo', request: { config: { kind: 'rename' } } })
  assert.deepEqual(calls.at(-1), { path: '/toolbox/rename', query: { plan: 'undo' } })
  ctx.unmount()
})

for (const cleanupMode of ['similar', 'duplicate']) test(cleanupMode + ' group includes every member with independent details and selection', async () => {
  const items = Array.from({ length: 5 }, (_, index) => ({
    id: index + 1, photo_id: 'similar-' + index, source: '/photos/' + index + '.jpg',
    target: '', status: 'candidate', selected: false, detail: { group_id: 8 },
  }))
  const plan = { id: 'similar-plan', kind: 'cleanup', version: 1, status: 'preview',
    summary: { phase: 'done' }, request: { config: { cleanup_mode: cleanupMode } } }
  const workflowApi = {
    items: async (...args) => { assert.equal(args[3], true); return { total: 1, selected_count: 0, items: [items[0]] } },
    members: async () => ({ total: 5, representative_id: items[0].photo_id,
      items: items.map((item, index) => ({ photo_id: item.photo_id, in_scope: index === 0, source: item.source, item })) }),
    selection: async () => ({ selected_count: 1 }),
  }
  const component = load('views/toolbox/ToolPlanPreview.vue', {
    '@/api/toolboxWorkflows': { workflowApi }, '@/utils/mediaUrl': { thumbnailUrl: id => id },
    'element-plus': { ElMessage: { error() {} } },
  }).default
  const ctx = mount(component, { plan, executing: false })
  await ctx.state.load()
  assert.equal(ctx.state.photoGroups.value.length, 1)
  await ctx.state.loadReferences(8)
  assert.deepEqual(ctx.state.photoGroups.value[0].items.map(item => item.source), items.map(item => item.source))
  await ctx.state.toggle(5, true)
  assert.equal(ctx.state.isSelected(ctx.state.photoGroups.value[0].items[4]), true)
  assert.equal(ctx.state.selectedCount.value, 1)
  ctx.unmount()
})

for (const mode of ['duplicate', 'similar']) test(mode + ' group paging serializes requests and retries the failed offset independently', async () => {
  const pending = []
  const plan = { id: 'paging', kind: 'cleanup', status: 'preview', summary: { phase: 'done' },
    request: { config: { cleanup_mode: mode } } }
  const component = load('views/toolbox/ToolPlanPreview.vue', {
    '@/api/toolboxWorkflows': { workflowApi: {
      items: async () => ({ total: 0, items: [] }),
      members: (id, group, offset) => new Promise((resolve, reject) => pending.push({ group, offset, resolve, reject })),
    } }, '@/utils/mediaUrl': { thumbnailUrl: id => id },
  }).default
  const ctx = mount(component, { plan, executing: false })
  await ctx.state.load()
  const first = ctx.state.loadReferences(8)
  await ctx.state.loadReferences(8)
  const otherGroup = ctx.state.loadReferences(9)
  assert.deepEqual(pending.map(({ group, offset }) => [group, offset]), [[8, 0], [9, 0]])
  const result = id => ({ total: 2, items: [{ photo_id: id }] })
  pending[0].resolve(result('first'))
  pending[1].resolve(result('other'))
  await Promise.all([first, otherGroup])
  const failed = ctx.state.loadReferences(8)
  pending[2].reject(new Error('current failure'))
  await failed
  assert.equal(ctx.state.memberErrors.value[8], true)
  assert.equal(ctx.state.canLoadMembers(9), true)
  assert.deepEqual(ctx.state.references.value[8].items.map(item => item.photo_id), ['first'])
  const retry = ctx.state.loadReferences(8)
  assert.equal(pending[3].offset, 1)
  pending[3].resolve(result('second'))
  await retry
  assert.equal(ctx.state.memberErrors.value[8], false)
  assert.equal(ctx.state.canLoadMembers(8), false)
  assert.deepEqual(ctx.state.references.value[8].items.map(item => item.photo_id), ['first', 'second'])
  const stale = ctx.state.loadReferences(9)
  ctx.state.resetResults()
  pending[4].resolve(result('stale'))
  await stale
  assert.equal(ctx.state.references.value[9], undefined)
  ctx.unmount()
})
