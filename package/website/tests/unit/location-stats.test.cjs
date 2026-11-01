const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')
const source = fs.readFileSync(path.resolve(__dirname, '../../src/utils/locationStats.ts'), 'utf8')
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
const loaded = { exports: {} }
new Function('module', 'exports', code)(loaded, loaded.exports)
const { timeBuckets, calendarWeeks, statsYears } = loaded.exports

test('annual trend preserves missing years and separates photos from distinct record days', () => {
  const data = [{ date: '2020-12-31', count: 8 }, { date: '2022-01-01', count: 3 }, { date: '2022-12-31', count: 5 }]
  assert.deepEqual(statsYears(data), [2022, 2020])
  const buckets = timeBuckets(data, 'year', 2022)
  assert.deepEqual(buckets.map(b => [b.label, b.photos, b.days]), [['2020', 8, 1], ['2021', 0, 0], ['2022', 8, 2]])
  assert.equal(buckets[0].start, '2020-01-01')
  assert.equal(buckets[2].end, '2022-12-31')
})
test('monthly drilldown uses the selected year, real month ends and zero-filled months', () => {
  const data = [{ date: '2024-02-29', count: 4 }, { date: '2023-02-28', count: 20 }, { date: '2024-12-31', count: 2 }]
  const leap = timeBuckets(data, 'month', 2024)
  assert.equal(leap.length, 12)
  assert.deepEqual(leap[1], { label: '2月', start: '2024-02-01', end: '2024-02-29', photos: 4, days: 1 })
  assert.equal(timeBuckets(data, 'month', 2023)[1].end, '2023-02-28')
  assert.equal(leap[0].photos, 0)
  assert.equal(leap[11].end, '2024-12-31')
})
test('calendar shows every day once, including leap day, and excludes neighbouring years', () => {
  const data = [{ date: '2024-02-29', count: 6 }, { date: '2023-12-31', count: 99 }]
  const days = calendarWeeks(data, 2024).flatMap(w => w.days).filter(d => !d.outside)
  assert.equal(days.length, 366)
  assert.equal(new Set(days.map(d => d.date)).size, 366)
  assert.equal(days[0].date, '2024-01-01')
  assert.equal(days.at(-1).date, '2024-12-31')
  assert.equal(days.find(d => d.date === '2024-02-29').count, 6)
  assert.equal(days.reduce((sum, d) => sum + d.count, 0), 6)
  assert.equal(calendarWeeks([], 2023).flatMap(w => w.days).filter(d => !d.outside).length, 365)
  assert.deepEqual(timeBuckets([], 'year', 2024), [])
})
