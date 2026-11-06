const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')

// Exercise the actual lightbox history handlers against a browser-like stack.
const source = fs.readFileSync(path.resolve(__dirname, '../../src/components/PhotoLightbox.vue'), 'utf8')
const history = source.slice(source.indexOf('const LIGHTBOX_HISTORY_KEY'), source.indexOf('// State', source.indexOf('const LIGHTBOX_HISTORY_KEY')))
const close = source.slice(source.indexOf('const close = () =>'), source.indexOf('const handleMediaTap'))
function fixture() {
  const entries = [{}]
  let index = 0, closed = 0
  const showOCR = { value: false }
  const window = {
    location: { href: '/photos' },
    history: {
      get state() { return entries[index] },
      pushState(state) { entries.splice(++index); entries[index] = state },
      back() { if (index) index--; context.handleHistoryPopState() },
    },
  }
  const context = vm.createContext({ window, showOCR, props: { visible: true }, emit: () => closed++, router: { push() {} } })
  const code = ts.transpileModule(`${history}\n${close}\nhistoryListenerMounted = true; pushLightboxHistoryEntry(); this.close = close; this.handleHistoryPopState = handleHistoryPopState`, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText
  vm.runInContext(code, context)
  return { window, context, showOCR, closed: () => closed, index: () => index }
}

test('lightbox back button dismisses OCR and keeps the photo history entry', () => {
  const f = fixture()
  f.showOCR.value = true
  f.context.close()
  assert.equal(f.showOCR.value, false)
  assert.equal(f.closed(), 0)
  assert.equal(f.index(), 1)
  f.context.close()
  assert.equal(f.closed(), 1)
  assert.equal(f.index(), 0)
})

test('browser back dismisses OCR first and a second back closes the lightbox', () => {
  const f = fixture()
  f.showOCR.value = true
  f.window.history.back()
  assert.equal(f.showOCR.value, false)
  assert.equal(f.closed(), 0)
  assert.equal(f.index(), 1)
  f.window.history.back()
  assert.equal(f.closed(), 1)
  assert.equal(f.index(), 0)
})

test('return from a nested dialog does not close the underlying lightbox', () => {
  const f = fixture()
  f.window.history.pushState({ ...f.window.history.state, nested: true })
  f.window.history.back()
  assert.equal(f.closed(), 0)
  f.context.close()
  assert.equal(f.closed(), 1)
})
