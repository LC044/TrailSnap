const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')
const { parse } = require('vue/compiler-sfc')
const vue = require('vue')

function deferred() {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

function shelf(api) {
  const source = fs.readFileSync(path.resolve(__dirname, '../../src/components/chapter/ChapterShelf.vue'), 'utf8')
  const { descriptor, errors } = parse(source)
  assert.deepEqual(errors, [])
  const code = ts.transpileModule(descriptor.scriptSetup.content + '\nexport { items, candidateCount, loading, shelf }', {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText
  let mount
  const deps = {
    vue: { ...vue, onMounted: fn => { mount = fn } },
    '@/api/chapter': { chapterApi: api },
    '@/utils/mediaUrl': { thumbnailUrl: id => id },
  }
  const module = { exports: {} }
  new Function('require', 'module', 'exports', 'sessionStorage', code)(name => deps[name], module, module.exports, {
    getItem: () => '120',
  })
  return { state: module.exports, mount }
}

test('chapter covers become visible while the parallel suggestion count is still pending', async () => {
  const list = deferred(), count = deferred()
  const calls = []
  const { state, mount } = shelf({
    list: () => { calls.push('list'); return list.promise },
    count: () => { calls.push('count'); return count.promise },
  })
  state.shelf.value = { scrollLeft: 0 }
  const pending = mount()
  assert.deepEqual(calls, ['list', 'count'])
  list.resolve({ items: [{ id: 'chapter', cover_photo_id: 'cover' }] })
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(state.loading.value, false)
  assert.equal(state.items.value[0].cover_photo_id, 'cover')
  assert.equal(state.shelf.value.scrollLeft, 120)
  count.reject(new Error('count unavailable'))
  await pending
  assert.equal(state.items.value.length, 1)
  assert.equal(state.candidateCount.value, 0)
})

test('suggestion count remains available when the chapter list fails', async () => {
  const { state, mount } = shelf({
    list: async () => { throw new Error('list unavailable') },
    count: async () => 3,
  })
  await mount()
  assert.equal(state.loading.value, false)
  assert.equal(state.items.value.length, 0)
  assert.equal(state.candidateCount.value, 3)
})
