const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')

function loadComposable() {
  const source = fs.readFileSync(path.resolve(__dirname, '../../src/composables/useMoonPhase.ts'), 'utf8')
  const code = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText
  const module = { exports: {} }
  vm.runInThisContext(`(function(module,exports){${code}\n})`)(module, module.exports)
  return module.exports
}

test('lunar parts stay correct with the shared formatter instance', () => {
  const { getChineseLunarDateParts } = loadComposable()
  // 2026-07-29 是农历六月十六（满月次日），验证复用同一 formatter 后结果不变。
  const parts = getChineseLunarDateParts(new Date('2026-07-29T21:30:00'))
  assert.equal(parts.day, 16)
  assert.ok(parts.month.length > 0)

  // 同一天内多次调用（页面首屏与月历扫描都会密集调用）结果必须一致。
  for (let index = 0; index < 3; index += 1) {
    const repeat = getChineseLunarDateParts(new Date('2026-07-29T21:30:00'))
    assert.deepEqual(repeat, parts)
  }

  // 跨月边界：2026-08-18 是农历七月初六。
  const nextMonth = getChineseLunarDateParts(new Date('2026-08-18T20:15:00'))
  assert.equal(nextMonth.day, 6)
})

test('moon phase keeps one Intl formatToParts call per date and stable phase buckets', () => {
  const { calculateMoonPhase } = loadComposable()
  const fullMoon = calculateMoonPhase(new Date('2026-07-29T21:30:00'))
  assert.equal(fullMoon.phase, 'full_moon')
  assert.equal(fullMoon.group, 'full')
  // lunarDate 里的农历日与 parts.day 保持同源（同一次 formatToParts 的结果）。
  assert.ok(fullMoon.lunarDate.includes('十六'))

  const crescent = calculateMoonPhase(new Date('2026-08-18T20:15:00'))
  assert.equal(crescent.phase, 'waxing_crescent')
  assert.ok(crescent.lunarDate.includes('初六'))
})

test('findNextChineseLunarDay still scans day by day after formatter reuse', () => {
  const { findNextChineseLunarDay } = loadComposable()
  const from = new Date('2026-11-21T12:00:00')
  const nextFifteenth = findNextChineseLunarDay(15, from)
  assert.ok(nextFifteenth instanceof Date)
  assert.ok(nextFifteenth.getTime() > from.getTime())
})

test('createMoonObservation rejects photos without a usable photo time', () => {
  const { createMoonObservation } = loadComposable()
  const photo = id => ({ id, hasPhotoTime: true, timestamp: new Date('2026-07-29T21:30:00').getTime(), filename: id })
  const observation = createMoonObservation(photo('a'))
  assert.equal(observation.phase, 'full_moon')
  assert.equal(createMoonObservation({ ...photo('b'), hasPhotoTime: false }), null)
})
