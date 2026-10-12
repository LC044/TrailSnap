const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const vue = require('vue')
const compiler = require('vue/compiler-sfc')
const { renderToString } = require('vue/server-renderer')

function load(file, dependencies, inlineTemplate = false) {
  let source = fs.readFileSync(path.resolve(__dirname, '../../src', file), 'utf8')
  if (file.endsWith('.vue')) {
    source = compiler.compileScript(compiler.parse(source).descriptor, { id: file, inlineTemplate }).content
  }
  source = source.replaceAll('import.meta.env.VITE_API_BASE_URL', "''")
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  const module = { exports: {} }
  vm.runInNewContext(`(function(require,module,exports){${code}\n})`, {
    URL,
    window: { location: { href: 'http://tauri.localhost' } },
    localStorage: { getItem: () => null },
  })(name => name === 'vue' ? vue : dependencies[name], module, module.exports)
  return module.exports
}

function server(base) {
  return load('config/server.ts', {
    '@capacitor/core': { Capacitor: { isNativePlatform: () => false } },
    '@capacitor/preferences': { Preferences: { get: async () => ({ value: base }) } },
    './nativeNetworkPolicy': {},
  })
}

function section(name, config, inlineTemplate = true) {
  return load(`components/annual-report/${name}.vue`, {
    '@/config/server': config,
    './ReportPage.vue': { default: { setup: (_, { slots }) => () => vue.h('div', slots.default()) } },
    'lucide-vue-next': {},
    '@vueuse/core': { useIntersectionObserver() {} },
  }, inlineTemplate).default
}

test('annual report photos use the configured server and preserve browser URLs', async () => {
  for (const base of ['', 'http://127.0.0.1:49152']) {
    const config = server(base)
    await config.initializeServerConfig()
    const photo = '/api/medias/owner/photo/thumbnail'
    const Season = section('SectionSeason', config)
    const html = await renderToString(vue.createSSRApp(Season, { data: { seasonList: [
      { seasonName: '春', representativePhoto: photo },
      { seasonName: '夏', representativePhoto: 'https://example.com/summer.jpg' },
    ] } }))
    assert.ok(html.includes(`src="${base}${photo}"`))
    assert.ok(html.includes('src="https://example.com/summer.jpg"'))
    const Best = section('SectionEasterEgg', config)
    const bestHtml = await renderToString(vue.createSSRApp(Best, { data: { bestPhotoUrl: photo, tags: { main: '', sub: [] } } }))
    assert.ok(bestHtml.includes(`src="${base}${photo}"`))
  }
})

test('default avatar stays bundled and failed custom avatars fall back without looping', async () => {
  const config = server('http://127.0.0.1:49152')
  await config.initializeServerConfig()
  const Cover = section('SectionCover', config, false)
  for (const avatar of ['', '/avatar.png', '/api/users/avatar']) {
    const props = vue.reactive({ user: { avatarUrl: avatar }, year: 2025 })
    const state = Cover.setup(props, { expose() {} })
    assert.equal(state.avatarUrl.value, avatar === '/api/users/avatar' ? `http://127.0.0.1:49152${avatar}` : '/avatar.png')
    state.useDefaultAvatar()
    state.useDefaultAvatar()
    assert.equal(state.avatarUrl.value, '/avatar.png')
    props.user.avatarUrl = '/api/users/new-avatar'
    await vue.nextTick()
    assert.equal(state.avatarUrl.value, 'http://127.0.0.1:49152/api/users/new-avatar')
  }
})
