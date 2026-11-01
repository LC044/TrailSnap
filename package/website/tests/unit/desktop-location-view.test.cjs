const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const vue = require('vue')
const compiler = require('vue/compiler-sfc')
const { renderToString } = require('vue/server-renderer')

function component(directory, inlineTemplate, calls) {
  const source = fs.readFileSync(path.join(__dirname, '../../src/views/settings/DesktopDataDirectory.vue'), 'utf8')
  const script = compiler.compileScript(compiler.parse(source).descriptor, { id: 'desktop-location-test', inlineTemplate }).content
  const code = ts.transpileModule(script, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const store = vue.reactive({ directory, discovery: null, error: null, loading: false, clearPreview() {}, async load() {}, async loadDiscovery() {} })
  const deps = {
    vue,
    '@/components/ui/SettingsPageHeader.vue': { default: { render: () => null } },
    'lucide-vue-next': { FolderOpen: { render: () => null } },
    'element-plus': { ElMessageBox: {} },
    '@/config/server': { isTauriApp: () => true },
    '@/stores/desktopDataDirectory': { useDesktopDataDirectoryStore: () => store },
    '@/api/desktopDataDirectory': {
      openDesktopDataDirectory: async () => calls.push('data'),
      openDesktopInstanceDirectory: async () => calls.push('instance'),
    },
  }
  const module = { exports: {} }
  vm.runInThisContext(`(function(require,module,exports){${code}\n})`)(name => {
    if (name in deps) return deps[name]
    throw Error(name)
  }, module, module.exports)
  return module.exports.default
}

async function html(directory) {
  const app = vue.createSSRApp(component(directory, true, []))
  app.component('el-input', { render: () => null })
  app.component('el-checkbox', { render: () => null })
  return renderToString(app)
}

test('portable location renders the actual whole folder exactly once and hides internal data paths', async () => {
  for (const instanceRoot of ['C:\\Users\\86390\\AppData\\Local\\TrailSnap', 'D:\\我的照片\\行影集']) {
    const result = await html({ mode: 'portable', root: `${instanceRoot}\\userdata`, instanceRoot })
    assert.equal(result.split(instanceRoot).length - 1, 1)
    assert.doesNotMatch(result, /userdata|图库数据文件夹|打开程序文件夹/)
    assert.match(result, /整个行影集文件夹移动到新位置/)
    assert.match(result, /仍需保留那些文件夹和磁盘/)
  }
})

test('an advanced detached library is not represented as self contained', async () => {
  const result = await html({ mode: 'portable', root: 'E:\\PrivateLibrary', instanceRoot: 'D:\\TrailSnap' })
  assert.match(result, /独立的资料保存位置/)
  assert.doesNotMatch(result, /程序、相册、照片记录和设置保存在这个文件夹中/)
  assert.doesNotMatch(result, /E:\\PrivateLibrary/)
})

test('open folder uses the instance command for portable mode and the data command for legacy mode', async () => {
  const renderer = vue.createRenderer({ insert() {}, remove() {}, createElement: () => ({}), createText: () => ({}), createComment: () => ({}), setText() {}, setElementText() {}, parentNode: () => null, nextSibling: () => null, patchProp() {} })
  for (const mode of ['portable', 'legacy-installed']) {
    const calls = []
    const view = component({ mode, root: 'C:/Data', instanceRoot: 'D:/TrailSnap' }, false, calls)
    let state
    // Keep lifecycle hooks from calling live native APIs in this focused interaction fixture.
    const app = renderer.createApp({ setup() { state = view.setup({}, { expose() {} }); return () => null } })
    app.config.errorHandler = error => { throw error }
    app.mount({})
    await state.openData()
    assert.deepEqual(calls, [mode === 'portable' ? 'instance' : 'data'])
    app.unmount()
  }
})
