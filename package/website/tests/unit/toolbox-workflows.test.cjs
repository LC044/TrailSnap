const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const vue = require('vue')
const compiler = require('vue/compiler-sfc')

function load(filename, dependencies = {}, storage = {}) {
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
      if (name in dependencies) return dependencies[name]
      throw new Error(name)
    }, module, module.exports, storage, { randomUUID: () => 'context-id' },
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

test('cleanup saves cross-page selection on server and loads references by page', async () => {
  const calls = []
  const plan = vue.reactive({ id: 'scan-one', kind: 'cleanup', version: 1, status: 'preview',
    summary: { phase: 'done', total: 30001, candidate: 20001 },
    request: { scope: api().emptyScope(), config: api().defaultConfig('cleanup') } })
  const workflowApi = {
    items: async () => ({ total: 20001, selected_count: 10001, items: [{ id: 7, selected: false, photo_id: 'photo', source: '/a.jpg', status: 'candidate', detail: { group_id: 2 } }] }),
    selection: async (...args) => { calls.push(['selection', ...args]); return { selected_count: 10002 } },
    members: async (...args) => { calls.push(['members', ...args]); return { total: 3000, representative_id: 'representative', items: [{ photo_id: 'reference', in_scope: false }] } },
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
  assert.equal(ctx.state.rows.value[0].selected, true)
  assert.deepEqual(calls.find(call => call[0] === 'selection').slice(2), [[7], true])
  assert.equal(ctx.state.photoGroups.value.length, 1)
  assert.equal(ctx.state.photoGroups.value[0].groupId, 2)
  assert.ok(calls.some(call => call[0] === 'members' && call[3] === 0))
  await ctx.state.loadReferences(2, 3)
  assert.deepEqual(calls.at(-1), ['members', 'scan-one', 2, 48])
  assert.equal(ctx.state.references.value[2].items[0].in_scope, false)
  ctx.unmount()
})

test('new scope is empty, and directory cancellation does not select a folder', async () => {
  const scope = api().emptyScope()
  const updates = []
  const component = load('views/toolbox/MediaScopeSelector.vue', {
    '@/api/album': { albumService: {} },
    '@/stores/user': { useUserStore: () => ({ userInfo: { id: 'owner' } }) },
    '@/stores/selectionStore': { useSelectionStore: () => ({}) },
  }).default
  const ctx = mount(component, { scope, count: null, checking: false }, {
    'onUpdate:scope': value => updates.push(value),
  })
  assert.equal(ctx.state.valid.value, false)
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
  }, { setItem: (key, value) => saved.set(key, JSON.parse(value)) })
  const calls = []
  entry.openToolForSelection({ push: value => calls.push(value) }, 'owner', ['a', 'a', 'b'], 'organize')
  assert.deepEqual(saved.get('trailsnap:toolbox:context:context-id').scope.photo_ids, ['a', 'b'])
  assert.equal(saved.get('trailsnap:toolbox:context:context-id').owner, 'owner')
  assert.equal(calls[0].path, '/toolbox/organize')
  entry.openToolForSelection({ push: value => calls.push(value) }, 'owner', [], 'rename')
  assert.equal(calls.length, 1)
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
  assert.match(ctx.state.ruleSummary.value, /指定分组/)
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
