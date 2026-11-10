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

test('default rename template wins over recent and save-as clears rename mode', async () => {
  const { defaultConfig } = api()
  const defaultRule = { ...defaultConfig('rename'), template: 'DEFAULT_{date}' }
  const recentRule = { ...defaultConfig('rename'), template: 'RECENT_{date}' }
  const store = {
    preferences: { presets: [{ id: 'default', name: 'Default', config: defaultRule }],
      default_rename_id: 'default', recent: [recentRule] },
    busy: false, load: async () => {},
  }
  const applied = []
  const component = load('views/toolbox/ToolPresetBar.vue', {
    '@/stores/toolbox': { useToolboxStore: () => store },
    'element-plus': { ElMessage: {}, ElMessageBox: {} },
  }).default
  const ctx = mount(component, { modelValue: defaultConfig('rename') }, {
    'onApply-default': value => applied.push(value),
  })
  await vue.nextTick()
  assert.equal(applied[0].template, defaultRule.template)
  ctx.state.renameOnly.value = true
  ctx.state.makeDefault.value = true
  ctx.state.openSave()
  assert.equal(ctx.state.renameOnly.value, false)
  assert.equal(ctx.state.makeDefault.value, false)
  ctx.unmount()
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
