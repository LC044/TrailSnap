const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')
const source = fs.readFileSync(path.resolve(__dirname, '../../src/utils/diaryPagination.ts'), 'utf8')
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
const moduleExports = { exports: {} }
new Function('exports', 'module', code)(moduleExports.exports, moduleExports)
const { paginateDiaryText, diarySwipeDirection } = moduleExports.exports

test('long diary text is preserved across small paper pages, including emoji and blank lines', () => {
  const text = '旅行🌄日记'.repeat(200)
  const pages = paginateDiaryText(text, 8, 3, value => Array.from(value).length)
  assert.ok(pages.length > 1)
  assert.equal(pages.join('').replaceAll('\n', ''), text)
  for (const page of pages) {
    assert.ok(page.split('\n').length <= 3)
    for (const line of page.split('\n')) assert.ok(Array.from(line).length <= 8)
  }
  assert.deepEqual(paginateDiaryText('第一行\n\n最后一行', 100, 2, value => value.length), ['第一行\n', '最后一行'])
  assert.deepEqual(paginateDiaryText('一', 0, 0, value => value.length), ['一'])
})

test('horizontal and vertical swipes page both ways, while taps and diagonal drags do not', () => {
  assert.equal(diarySwipeDirection(-80, 3, 400), 1)
  assert.equal(diarySwipeDirection(80, 3, 400), -1)
  assert.equal(diarySwipeDirection(3, -80, 400), 1)
  assert.equal(diarySwipeDirection(3, 80, 400), -1)
  assert.equal(diarySwipeDirection(-20, 0, 100), 1)
  assert.equal(diarySwipeDirection(-20, 0, 400), 0)
  assert.equal(diarySwipeDirection(0, 0, 100), 0)
  assert.equal(diarySwipeDirection(50, 50, 100), 0)
})
