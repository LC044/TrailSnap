const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const vue = require('vue')

function load(name, globals = {}) {
  const source = fs.readFileSync(path.resolve(__dirname, '../../src/composables', name + '.ts'), 'utf8')
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  })
  const dependencies = {
    vue: { ...vue, onBeforeUnmount() {} },
    '@/composables/useOverlayStack': { useOverlayStack() {} },
    '@/stores/uiStore': { useUiStore: () => ({ setSelectionActive() {} }) },
  }
  const exports = {}
  vm.runInNewContext(outputText, { exports, require: id => dependencies[id], ...globals })
  return exports[name]
}

test('Shift range shrinks and crosses its anchor while preserving independent selections', async () => {
  const selection = load('useSelection')()
  const order = () => ['a', 'b', 'c', 'd', 'e']
  selection.toggleSelect('e')
  selection.toggleSelect('c')
  await selection.selectRange(order, 'e')
  await selection.selectRange(order, 'e')
  assert.deepEqual([...selection.selectedIds].sort(), ['c', 'd', 'e'])
  await selection.selectRange(order, 'b')
  assert.deepEqual([...selection.selectedIds].sort(), ['b', 'c', 'e'])
})

test('Shift uses newly loaded photos and drops a request superseded by a normal click', async () => {
  const selection = load('useSelection')()
  let photos = ['a', 'c']
  selection.toggleSelect('a')
  await selection.selectRange(() => photos, 'c', async () => {
    photos = ['a', 'b', 'c']
    return true
  })
  assert.deepEqual([...selection.selectedIds], ['a', 'b', 'c'])

  let release
  const pending = selection.selectRange(() => photos, 'b', () => new Promise(resolve => { release = resolve }))
  selection.toggleSelect('a')
  release(true)
  await pending
  assert.deepEqual([...selection.selectedIds], ['b', 'c'])
})

test('long-press swipe stays in its own gallery and consumes release, while early dragging still scrolls', () => {
  const win = new EventTarget()
  const card = id => ({
    dataset: { photoId: id },
    closest() { return this },
  })
  const first = card('a')
  const second = card('b')
  const foreign = card('other')
  const gallery = { contains: item => item === first || item === second }
  const selected = new Set()
  let activate
  const startSwipe = load('useSwipeSelect', {
    window: win,
    document: { elementFromPoint: x => x < 40 ? first : x < 80 ? second : foreign },
    setTimeout: callback => { activate = callback; return 1 },
    clearTimeout: () => { activate = undefined },
  })
  const { onTouchstart } = startSwipe({
    canStart: () => true,
    canSweep: () => true,
    isSelected: id => selected.has(id),
    onLongPressActivate: id => selected.add(id),
    onSwipePhoto: id => selected.add(id),
    onSuppressClick: () => assert.fail('cancelable release should prevent the click directly'),
  })
  const touch = clientX => ({ identifier: 1, clientX, clientY: 0 })
  const start = () => onTouchstart({ currentTarget: gallery, target: first, touches: [touch(20)] })
  const dispatch = (type, touches, changedTouches = []) => {
    const event = Object.assign(new Event(type, { cancelable: true }), { touches, changedTouches })
    win.dispatchEvent(event)
    return event.defaultPrevented
  }

  start()
  assert.equal(dispatch('touchmove', [touch(50)]), false)
  assert.equal(activate, undefined)
  assert.equal(selected.size, 0)

  start()
  activate()
  assert.equal(dispatch('touchmove', [touch(100)]), true)
  assert.equal(dispatch('touchend', [], [touch(100)]), true)
  assert.deepEqual([...selected], ['a', 'b'])
})
