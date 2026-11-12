const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')
const vm = require('node:vm')
const { ref, computed } = require('vue')

function page(getTags, list) {
  const source = fs.readFileSync(path.resolve(__dirname, '../../src/views/album/intelligent-classification/ClassificationList.vue'), 'utf8')
  const script = source.split('<script setup lang="ts">')[1].split('</script>')[0].replace(/^import .*$/gm, '')
  const context = { ref, computed, useRouter: () => ({}), onMounted() {},
    classificationService: { getTags }, clipClassificationService: { list } }
  vm.createContext(context)
  vm.runInContext(ts.transpileModule(script + '\nglobalThis.page = { fetchTags, tags, categories, error, loading };', {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText, context)
  return context.page
}

test('classification starts both requests before either completes', async () => {
  let resolveTags, resolveCategories
  const calls = []
  const p = page(() => { calls.push('tags'); return new Promise(r => { resolveTags = r }) },
    () => { calls.push('categories'); return new Promise(r => { resolveCategories = r }) })
  const pending = p.fetchTags()
  assert.deepEqual(calls, ['tags', 'categories'])
  resolveTags([{ id: 'tag' }])
  resolveCategories({ groups: ['group'], categories: [{ id: 'category' }] })
  await pending
  assert.equal(p.tags.value[0].id, 'tag')
  assert.equal(p.categories.value[0].id, 'category')
  assert.equal(p.loading.value, false)
})

test('classification keeps tags available if category rules fail', async () => {
  const p = page(async () => [{ id: 'tag' }], async () => { throw Error('rules') })
  await p.fetchTags()
  assert.equal(p.tags.value[0].id, 'tag')
  assert.equal(p.error.value, '分类分组暂不可用，仍可浏览已有标签。')
  assert.equal(p.loading.value, false)
})

test('classification reports tag failure even when both requests fail', async () => {
  const p = page(async () => { throw Error('tags') }, async () => { throw Error('rules') })
  await p.fetchTags()
  assert.equal(p.error.value, '分类加载失败，请重试。')
  assert.equal(p.loading.value, false)
})
