const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const vue = require('vue')
const sfc = require('vue/compiler-sfc')
const { renderToString } = require('vue/server-renderer')

function evaluate(source, imports, globals = {}) {
  const code = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  } }).outputText
  const module = { exports: {} }
  vm.runInNewContext(`(function(require, module, exports) { ${code}\n})`, { console, ...globals })(
    name => imports[name] || require(name), module, module.exports)
  return module.exports
}
function source(relative) {
  return fs.readFileSync(path.resolve(__dirname, '../../src', relative), 'utf8')
}
function snapshot(overrides = {}) {
  return { platform: 'win32-x64', clientVersion: '0.17.3', serverVersion: '0.17.4', minimumAIExtensionVersion: '0.17.4', operationBusy: false,
    releasePageUrl: 'https://github.com/LC044/TrailSnap/releases', gateway: { running: true },
    extensions: [{ id: 'core-ai', name: 'AI 完整扩展', version: '0.17.4', description: 'test',
      capabilities: ['ocr'], requirements: {}, available: true,
      installed: { version: '0.17.3', capabilities: ['ocr'] }, compatibility: 'required_update',
      updateVersion: '0.17.4', downloadUrl: 'https://github.com/LC044/TrailSnap/releases/download/v0.17.4/ai.tar.gz',
      downloadFilename: 'ai.tar.gz' }], ...overrides }
}
function store(request) {
  return evaluate(source('stores/desktopAIExtensions.ts'), {
    pinia: { defineStore: (_id, setup) => setup }, vue,
    '@/api/desktopAIExtensions': { desktopExtensionRequest: request, importDesktopAIExtension: async () => ({ canceled: true }) },
  }).useDesktopAIExtensionsStore()
}

test('catalog failure remains visible while keeping the installed runtime, and a new check recovers', async () => {
  let fail = true
  const state = store(async p => {
    if (p === '/refresh' && fail) throw Error('网络不可用')
    return snapshot()
  })
  await state.load()
  await state.refresh()
  assert.match(state.catalogError.value, /网络不可用/)
  assert.equal(state.snapshot.value.extensions[0].installed.version, '0.17.3')
  assert.equal(state.desktopAvailable.value, true)
  fail = false
  await state.refresh()
  assert.equal(state.catalogError.value, null)
})

test('checks and writes are deduplicated, and stale polling cannot replace a successful check', async () => {
  let oldPoll, resolveCheck, writes = 0, checks = 0
  const state = store(p => {
    if (!p) return new Promise(resolve => oldPoll = resolve)
    if (p === '/refresh') { checks++; return new Promise(resolve => resolveCheck = resolve) }
    writes++; return Promise.resolve({})
  })
  const poll = state.load()
  const checking = state.refresh()
  await state.refresh()
  assert.equal(checks, 1)
  resolveCheck(snapshot({ clientVersion: '0.17.4' }))
  await checking
  oldPoll(snapshot({ clientVersion: '0.17.3' }))
  await poll
  assert.equal(state.snapshot.value.clientVersion, '0.17.4')
  assert.equal(writes, 0, 'frontend checking never creates downloads')
})

test('busy updates also prevent offline import and release pending state after request errors', async () => {
  const state = store(async p => {
    if (!p) return snapshot({ operationBusy: true })
    throw Error('操作已在进行中')
  })
  await state.load()
  await assert.rejects(state.importArchive(), /操作进行中/)
  await assert.rejects(state.action('core-ai', 'uninstall'), /已在进行中/)
  assert.equal(state.actionPending.value, false)
})

test('API preserves Tauri command names and canceled imports do not invoke installation', async () => {
  const calls = []
  const api = evaluate(source('api/desktopAIExtensions.ts'), {
    '@/config/server': { isTauriApp: () => true },
    '@tauri-apps/api/core': { invoke: async (command, args) => { calls.push([command, args]); return snapshot() } },
    '@tauri-apps/plugin-dialog': { open: async () => null },
  })
  await api.desktopExtensionRequest('/core-ai/retry')
  assert.equal(calls[0][0], 'ai_extension_retry')
  assert.equal(calls[0][1].id, 'core-ai')
  const result = await api.importDesktopAIExtension()
  assert.equal(result.canceled, true)
  assert.equal(calls.length, 1)
  for (const status of ['downloading', 'verifying', 'draining', 'installing']) {
    assert.equal(api.extensionIsBusy({ job: { status } }), true)
  }
})

async function page(data, overrides = {}) {
  const descriptor = sfc.parse(source('views/settings/DesktopAIExtensions.vue')).descriptor
  const script = sfc.compileScript(descriptor, { id: 'extension-page' })
  const template = sfc.compileTemplate({ source: descriptor.template.content, filename: 'DesktopAIExtensions.vue',
    id: 'extension-page', ssr: true, compilerOptions: { bindingMetadata: script.bindings } })
  assert.deepEqual(template.errors, [])
  const state = { snapshot: vue.ref(data), desktopAvailable: vue.ref(true), catalogError: vue.ref(null),
    checking: vue.ref(false), busy: vue.ref(data.operationBusy), ...overrides }
  const component = evaluate(script.content, {
    vue, pinia: { storeToRefs: s => s },
    'vue-router': { useRoute: () => ({ query: {} }), useRouter: () => ({ push() {} }) },
    'element-plus': { ElMessage: {}, ElMessageBox: {} },
    '@/config/server': { isTauriApp: () => false },
    '@/stores/desktopAIExtensions': { useDesktopAIExtensionsStore: () => state },
    '@/api/desktopAIExtensions': { extensionIsBusy: e => ['downloading', 'verifying', 'draining', 'installing'].includes(e.job?.status) },
  }).default
  component.ssrRender = evaluate(template.code, {}).ssrRender
  return renderToString(vue.createSSRApp(component))
}

test('installed updates render progress, failure, target version, platform and manual download instructions', async () => {
  const data = snapshot()
  data.extensions[0].job = { status: 'failed', progress: 42, error: '校验失败' }
  const html = await page(data)
  for (const text of ['42%', '校验失败', '重试', 'win32-x64', 'v0.17.3', 'v0.17.4', '手动下载', 'ai.tar.gz', '下载后无需解压']) {
    assert.ok(html.includes(text), text)
  }
  assert.ok(html.includes(data.extensions[0].downloadUrl))
  assert.ok(html.includes('Server v0.17.4'))
  assert.ok(html.includes('最低支持 AI 扩展 v0.17.4'))
})

test('catalog errors and missing assets retain official downloads and checking state', async () => {
  const data = snapshot()
  Object.assign(data.extensions[0], { available: false, downloadUrl: null, downloadFilename: null, compatibility: 'unknown' })
  const html = await page(data, { checking: vue.ref(true), catalogError: vue.ref('HTTP 503') })
  for (const text of ['兼容性未知', '官方下载页', '暂无当前平台附件', 'HTTP 503', '正在检查…', '离线导入']) {
    assert.ok(html.includes(text), text)
  }
  assert.ok(!html.includes('已是最新'))
})
