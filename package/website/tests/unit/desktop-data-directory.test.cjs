const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')

function harness(options = {}) {
  const source = fs.readFileSync(path.join(__dirname, '../../src/stores/desktopDataDirectory.ts'), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const calls = []
  const module = { exports: {} }
  const api = {
    previewPortableMigration: options.preview || (async input => ({ source: input || 'C:/Current/userdata', counts: { photos: 23424 } })),
    convertPortableInstance: async (...args) => calls.push(args),
  }
  vm.runInNewContext(`(function(require,module,exports){${code}\n})`)(name => {
    if (name === 'vue') return { ref: value => ({ value }) }
    if (name === 'pinia') return { defineStore: (_name, setup) => setup }
    if (name === '@/api/desktopDataDirectory') return api
    throw Error(name)
  }, module, module.exports)
  return { store: module.exports.useDesktopDataDirectoryStore(), calls }
}

test('conversion requires a successful preview of the same selected source', async () => {
  const { store, calls } = harness()
  await store.convert('D:/New', false, 'C:/Legacy')
  assert.equal(calls.length, 0)
  await store.inspectPortable('C:/Legacy')
  await store.convert('D:/New', false, 'C:/Other')
  assert.equal(calls.length, 0)
  assert.match(store.error.value, /先检查所选图库/)
})

test('conversion uses the root actually returned by the preview', async () => {
  const { store, calls } = harness({ preview: async () => ({ source: 'C:/Canonical/Legacy', counts: { photos: 23424 } }) })
  await store.inspectPortable('C:/Legacy')
  await store.convert(' D:/New ', true, 'C:/Legacy')
  assert.deepEqual(calls, [['D:/New', true, 'C:/Canonical/Legacy']])
})

test('editing a source discards an older in-flight preview', async () => {
  let finish
  const { store } = harness({ preview: () => new Promise(resolve => { finish = resolve }) })
  const pending = store.inspectPortable('C:/Old')
  store.clearPreview()
  finish({ source: 'C:/Old', counts: { photos: 1 } })
  await pending
  assert.equal(store.preview.value, null)
})

test('a preview error asks for correction without requiring a restart', async () => {
  const { store } = harness({ preview: async () => { throw Error('请改选上一级目录') } })
  await store.inspectPortable('C:/Legacy/data')
  assert.match(store.error.value, /改选上一级/)
  assert.equal(store.needsRestart.value, false)
  assert.equal(store.preview.value, null)
  assert.equal(store.loading.value, false)
})
