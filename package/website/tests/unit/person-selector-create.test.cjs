const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const { ref, computed } = require('vue')

function selector() {
  const source = fs.readFileSync(path.resolve(__dirname, '../../src/components/PersonSelector.vue'), 'utf8')
  const script = source.split('<script setup lang="ts">')[1].split('</script>')[0].replace(/^import .*$/gm, '')
  const events = [], queries = [], names = [], errors = []
  let failure = false
  const props = { visible: true, submitting: false }
  const state = { ref, computed, watch() {}, defineProps: () => props, defineEmits: () => (...args) => events.push(args),
    console: { error() {} }, ElMessage: { error: text => errors.push(text) },
    faceApi: { listIdentities: async (...args) => { queries.push(args); return [{ id: 'one', identity_name: '一张照片的人', face_count: 1 }] },
      createIdentity: async data => { names.push(data.identity_name); if (failure) throw new Error('offline'); return { id: 'new', identity_name: data.identity_name, face_count: 0 } } } }
  vm.createContext(state)
  vm.runInContext(ts.transpileModule(script + '\nglobalThis.page = { searchQuery, creating, newName, loading, people, loadPeople, beginCreate, createPerson };', {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText, state)
  return { ...state.page, events, queries, names, errors, fail: value => { failure = value } }
}

test('new person can be created from an empty search and selected with zero existing photos', async () => {
  const s = selector()
  await s.loadPeople()
  assert.equal(JSON.stringify(s.queries[0]), JSON.stringify([1, 200, ['named'], 0]))
  assert.equal(s.people.value[0].face_count, 1)
  s.beginCreate()
  assert.equal(s.creating.value, true)
  await s.createPerson()
  assert.equal(s.names.length, 0, 'empty name cannot create a person')
  s.newName.value = '  新朋友  '
  await s.createPerson()
  assert.equal(s.names[0], '新朋友')
  assert.equal(s.events[0][0], 'select')
  assert.equal(s.events[0][1].id, 'new')
  assert.equal(s.events[0][1].face_count, 0)
})

test('failed creation keeps the entered name and allows retry without selecting anything', async () => {
  const s = selector()
  s.searchQuery.value = '新朋友'
  s.beginCreate()
  s.fail(true)
  await s.createPerson()
  assert.equal(s.creating.value, true)
  assert.equal(s.newName.value, '新朋友')
  assert.equal(s.events.length, 0)
  assert.equal(s.loading.value, false)
  assert.equal(s.errors.length, 1)
  s.fail(false)
  await s.createPerson()
  assert.equal(s.events.length, 1)
})
