const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const vue = require('vue')
const compiler = require('vue/compiler-sfc')
const { renderToString } = require('vue/server-renderer')

const source = fs.readFileSync(path.resolve(__dirname, '../../src/components/UnifiedPhotoPage.vue'), 'utf8')
const { descriptor } = compiler.parse(source)
function findTitle(node) {
  if (node.props?.some(prop => prop.name === 'data-testid' && prop.value?.content === 'photo-page-title')) return node
  for (const child of node.children || []) {
    const found = findTitle(child)
    if (found) return found
  }
}
const compiled = compiler.compileTemplate({ source: findTitle(descriptor.template.ast).loc.source, filename: 'UnifiedPhotoPage.vue', id: 'title' })
assert.deepEqual(compiled.errors, [])
const moduleObject = { exports: {} }
vm.runInNewContext(ts.transpileModule(compiled.code, {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText, { module: moduleObject, exports: moduleObject.exports, require: () => vue })
async function renderTitle(stableTitle, headerScrolled) {
  const app = vue.createSSRApp({
    setup: () => ({ stableTitle, headerScrolled, title: '照片', showBack: false, loadingTitle: false, subtitle: '' }),
    render: moduleObject.exports.render,
  })
  return (await renderToString(app)).replace(/data-scrolled="(?:true|false)"/g, '')
}

test('photo header keeps identical rendered typography, color and background across scroll state changes', async () => {
  assert.equal(await renderTitle(true, false), await renderTitle(true, true))
})

test('other browse pages retain the compact title on scroll', async () => {
  assert.notEqual(await renderTitle(false, false), await renderTitle(false, true))
  assert.match(await renderTitle(false, true), /ts-compact-title/)
})
