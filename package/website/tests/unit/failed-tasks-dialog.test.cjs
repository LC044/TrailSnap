const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const { ref, computed } = require('vue')

function harness() {
  const source = fs.readFileSync(path.resolve(__dirname, '../../src/components/FailedTasksDialog.vue'), 'utf8')
  const script = source.split('<script setup lang="ts">')[1].split('</script>')[0].replace(/^import .*$/gm, '')
  const props = { modelValue: true, category: 'OCR', title: '文字识别' }
  const errors = [], events = [], reveals = []
  let rows = [], photoRows = [], desktop = false, list = async () => rows, retry = async () => {}
  const context = {
    ref, computed, watch() {}, defineAsyncComponent() {}, defineProps: () => props,
    defineEmits: () => (...args) => events.push(args),
    tasksApi: { listTasks: (...args) => list(...args), retryTask: (...args) => retry(...args) },
    albumService: { getPhotosByIds: async ids => photoRows.filter(photo => ids.includes(photo.id)), getMetadata: async () => ({}) },
    isTauriApp: () => desktop, revealDesktopPhoto: async file => reveals.push(file),
    mapPhotoToImage: photo => ({ ...photo, preview: 'preview' }), ElMessage: { error: value => errors.push(value), success() {} },
  }
  vm.createContext(context)
  vm.runInContext(ts.transpileModule(script + '\nglobalThis.page = { loadTasks, tasks, loadError, shownTasks, showMore, photos, viewPhoto, preview, revealPhoto, retryTask, retrying, filename };', {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText, context)
  return { ...context.page, props, errors, events, reveals,
    rows: value => { rows = value }, photosData: value => { photoRows = value }, desktop: value => { desktop = value },
    list: value => { list = value }, retry: value => { retry = value } }
}
const task = (id = 'task-1') => ({ id, type: 'OCR', payload: { photo_id: 'photo-1' }, error: 'failure', created_at: '' })

test('failed list ignores stale category responses and retries failed loading', async () => {
  const page = harness()
  let resolveFirst
  page.list(() => new Promise(resolve => { resolveFirst = resolve }))
  const first = page.loadTasks()
  page.rows([task('new')]); page.list(async () => [task('new')])
  await page.loadTasks()
  resolveFirst([task('old')]); await first
  assert.equal(page.tasks.value[0].id, 'new')
  page.list(async () => { throw new Error('offline') }); await page.loadTasks()
  assert.equal(page.loadError.value, true)
  page.list(async () => []); await page.loadTasks()
  assert.equal(page.loadError.value, false)
})

test('photo preview uses real photo lookup and missing photos produce feedback', async () => {
  const page = harness()
  await page.viewPhoto(task())
  assert.match(page.errors[0], /照片不存在/)
  page.photosData([{ id: 'photo-1', filename: 'trip.jpg' }])
  await page.viewPhoto(task())
  assert.equal(page.preview.value.id, 'photo-1')
})

test('folder reveal is desktop only and uses current photo path or path-only task', async () => {
  const page = harness()
  const row = { ...task(), payload: { file_path: 'C:\\Photos\\trip.jpg' } }
  await page.revealPhoto(row); assert.equal(page.reveals.length, 0)
  page.desktop(true); await page.revealPhoto(row)
  assert.equal(page.reveals[0], row.payload.file_path)
  page.photosData([{ id: 'photo-1', file_path: 'C:\\Photos\\current.jpg' }])
  await page.revealPhoto(task())
  assert.equal(page.reveals[1], 'C:\\Photos\\current.jpg')
})

test('retries prevent duplicate submissions, preserve failures and remove successful tasks', async () => {
  const page = harness(); page.rows([task()]); await page.loadTasks()
  let finish, calls = 0
  page.retry(() => { calls++; return new Promise(resolve => { finish = resolve }) })
  const pending = page.retryTask(task()); await page.retryTask(task())
  assert.equal(calls, 1); assert.equal(page.tasks.value.length, 1)
  finish(); await pending
  assert.equal(page.tasks.value.length, 0); assert.equal(page.events[0][0], 'retried')
  page.rows([task()]); await page.loadTasks()
  page.retry(async () => { throw new Error('offline') }); await page.retryTask(task())
  assert.equal(page.tasks.value.length, 1); assert.equal(page.retrying.value.size, 0)
})

test('large failure lists render progressively and Windows filenames remain readable', async () => {
  const page = harness(); page.rows(Array.from({ length: 45 }, (_, i) => task(`task-${i}`)))
  await page.loadTasks(); assert.equal(page.shownTasks.value.length, 20)
  page.showMore(); assert.equal(page.shownTasks.value.length, 40)
  assert.equal(page.filename({ payload: { file_path: 'C:\\Photos\\trip.jpg' } }), 'trip.jpg')
})
