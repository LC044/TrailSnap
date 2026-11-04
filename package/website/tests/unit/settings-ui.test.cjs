const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const { parse, compileScript, compileTemplate } = require('vue/compiler-sfc')

const read = file => fs.readFileSync(path.resolve(__dirname, '../../src', file), 'utf8')

function aboutHarness({ update = false, fail = false, app = false } = {}) {
  const calls = []
  const requests = []
  let mounted
  const script = parse(read('views/settings/AboutPage.vue')).descriptor.scriptSetup.content
  const code = ts.transpileModule(`${script}\nexport { checkUpdate, availableUpdate }`, {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText
  const module = { exports: {} }
  vm.runInNewContext(`(function(require,module,exports){${code}\n})`, { console: { error() {} } })(name => {
    if (name === 'vue') return { ref: value => ({ value }), onMounted: callback => { mounted = callback } }
    if (name === 'element-plus') return {
      ElMessage: { success: text => calls.push(['success', text]), error: text => calls.push(['error', text]) },
      ElMessageBox: { confirm: () => { calls.push(['confirm']); return Promise.reject('cancel') } },
    }
    if (name === '@/api/system') return { systemApi: {
      getVersion: async () => ({ version: '1.0.0' }),
      checkUpdate: async silent => {
        requests.push(silent)
        if (fail) throw Error('offline')
        return { current_version: '1.0.0', has_update: update, latest_version: '1.1.0' }
      },
    } }
    if (name === '@/config/server') return { getServerUrl: () => '', isMobileApp: () => app, isTauriApp: () => false }
    if (name === '@/composables/useAppUpdate') return { useAppUpdate: () => ({
      supported: app, currentVersion: { value: '' }, errorMessage: { value: '' },
      checkForUpdate: async silent => { calls.push(['app-check', silent]); return false },
    }) }
    if (name === '@/stores/desktopUpdates') return { useDesktopUpdatesStore: () => ({}) }
    if (name.endsWith('.vue')) return {}
    throw Error(name)
  }, module, module.exports)
  return { calls, requests, mounted: () => mounted(), ...module.exports }
}

test('about automatic checks are silent for current versions and failures', async () => {
  for (const fail of [false, true]) {
    const h = aboutHarness({ fail })
    await h.mounted()
    assert.deepEqual(h.calls, [])
    await h.checkUpdate(false)
    assert.equal(h.calls[0][0], fail ? 'error' : 'success')
    assert.deepEqual(h.requests, [true, false])
  }
})

test('about automatic web updates stay inline while manual checks open details', async () => {
  const h = aboutHarness({ update: true })
  await h.mounted()
  assert.equal(h.availableUpdate.value.latest_version, '1.1.0')
  assert.deepEqual(h.calls, [])
  await h.checkUpdate(false)
  assert.deepEqual(h.calls, [['confirm']])
})

test('about app checks preserve native silent and manual update modes', async () => {
  const h = aboutHarness({ app: true })
  await h.mounted()
  assert.deepEqual(h.calls, [['app-check', true]])
  await h.checkUpdate(false)
  assert.deepEqual(h.calls, [['app-check', true], ['app-check', false], ['success', '当前已是最新版本']])
})

test('changed settings components compile their scripts and templates', () => {
  for (const file of [
    'components/PwaInstallPrompt.vue', 'components/ui/SettingsFormRow.vue',
    'views/Settings.vue', 'views/settings/AboutPage.vue', 'views/settings/BasicSettings.vue',
    'views/settings/UserManagement.vue', 'views/settings/ProfileSettings.vue',
    'views/settings/TaskManagement.vue', 'views/settings/Tokens.vue',
    'views/settings/FeedbackPage.vue', 'views/settings/MobileAppConnection.vue',
    'views/settings/sections/TaskSettingsSection.vue',
  ]) {
    const { descriptor, errors } = parse(read(file))
    assert.deepEqual(errors, [], file)
    const script = compileScript(descriptor, { id: file })
    const template = compileTemplate({
      id: file, filename: file, source: descriptor.template.content,
      compilerOptions: { bindingMetadata: script.bindings },
    })
    assert.deepEqual(template.errors, [], file)
  }
})

test('member layout prevents email wrapping and keeps logout in global navigation', () => {
  const source = read('views/settings/UserManagement.vue')
  assert.match(source, /prop="email"[^>]*show-overflow-tooltip/)
  assert.doesNotMatch(source, /handleLogout/)
  for (const file of ['layouts/Sidebar.vue', 'layouts/BottomNav.vue']) {
    assert.match(read(file), /退出登录/)
  }
})

test('PWA space follows actual banner height and clears on dismissal', () => {
  const source = read('components/PwaInstallPrompt.vue')
  assert.match(source, /useResizeObserver\(promptRef, reservePromptSpace\)/)
  assert.match(source, /visible\.value \? promptRef\.value\?\.getBoundingClientRect\(\)\.height/)
  assert.match(source, /onBeforeUnmount/)
  assert.match(read('styles/ui.css'), /--ts-pwa-prompt-space/)
  assert.match(read('views/Settings.vue'), /--ts-pwa-prompt-space/)
})
