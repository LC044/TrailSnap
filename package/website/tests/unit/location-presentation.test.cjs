const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')

function loadPresentation() {
  const source = fs.readFileSync(path.join(__dirname, '../../src/utils/locationPresentation.ts'), 'utf8')
  const code = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText
  const module = { exports: {} }
  vm.runInNewContext(code, { module, exports: module.exports, Intl, Number, Math, Date, String })
  return module.exports
}

test('location level labels keep the measure word that reads naturally', () => {
  const { locationLevelMeta } = loadPresentation()
  assert.equal(locationLevelMeta('province').unit, '个省份')
  assert.equal(locationLevelMeta('city').unit, '座城市')
  assert.equal(locationLevelMeta('district').unit, '个区县')
  assert.equal(locationLevelMeta('scene').unit, '处景区')
  assert.equal(locationLevelMeta('unexpected').unit, '处地点')
})

test('counts are grouped and compacted only when a badge would become long', () => {
  const { formatCount, formatCompactCount } = loadPresentation()
  assert.equal(formatCount(4133), '4,133')
  assert.equal(formatCompactCount(9999), '9,999')
  assert.equal(formatCompactCount(10000), '1万')
  assert.equal(formatCompactCount(18320), '1.8万')
  assert.equal(formatCompactCount(150000), '15万')
  assert.equal(formatCompactCount(-4), '0')
})

test('cover dates use the capture month and fall back cleanly', () => {
  const { formatCoverMonth, coverTimestamp, formatIndex } = loadPresentation()
  assert.equal(formatCoverMonth({ photo_time: '2026-11-05 08:00:00' }), '2026.11')
  assert.equal(formatCoverMonth({ upload_time: '2024-03-09T12:00:00' }), '2024.03')
  assert.equal(formatCoverMonth({ photo_time: 'not-a-date' }), '')
  assert.equal(formatCoverMonth(null), '')
  assert.equal(coverTimestamp(null), 0)
  assert.ok(coverTimestamp({ photo_time: '2026-11-05 08:00:00' }) > 0)
  assert.equal(formatIndex(0), '01')
  assert.equal(formatIndex(11), '12')
})