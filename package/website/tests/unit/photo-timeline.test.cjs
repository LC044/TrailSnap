const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')
const source = fs.readFileSync(path.resolve(__dirname, '../../src/utils/photoTimeline.ts'), 'utf8')
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
const mod = { exports: {} }
new Function('exports', code)(mod.exports)
const { overviewBuckets, timelineParts, timelineTimestamp, nearestTimelinePhoto } = mod.exports

test('year and month aggregation preserves complete counts and stable representatives', () => {
  const months = [
    { year: 2026, month: 10, count: 100, cover: { id: 'a' } },
    { year: 2026, month: 8, count: 23, cover: { id: 'b' } },
    { year: 2020, month: 1, count: 6, cover: { id: 'c' } },
    { year: 0, month: 0, count: 2, cover: { id: 'unknown' } },
  ]
  assert.deepEqual(overviewBuckets(months, 'year').map(x => [x.key, x.count, x.cover.id]), [
    ['2026', 123, 'a'], ['2020', 6, 'c'], ['0', 2, 'unknown'],
  ])
  assert.equal(months[0].count, 100)
  assert.equal(overviewBuckets(months, 'month').length, 4)
})

test('time dimension keeps capture and addition separate, including unknown timestamps', () => {
  const photo = { photoTime: '2020-12-31T23:59:59', uploadTime: '2026-01-01T00:00:00' }
  assert.equal(timelineParts(timelineTimestamp(photo, 'photo_time')).dayKey, '2020-12-31')
  assert.equal(timelineParts(timelineTimestamp(photo, 'upload_time')).dayKey, '2026-1-1')
  assert.equal(timelineParts(timelineTimestamp({ ...photo, photoTime: null }, 'photo_time')).dayKey, 'all')
})

test('anchor fallback prefers nearest timestamps, stable ties, and the unknown group', () => {
  const photos = [{ id: 'a', timestamp: 100 }, { id: 'b', timestamp: 120 }, { id: 'c', timestamp: NaN }]
  assert.equal(nearestTimelinePhoto(photos, { timestamp: 110 }).id, 'b')
  assert.equal(nearestTimelinePhoto(photos, { timestamp: NaN }).id, 'c')
  assert.equal(nearestTimelinePhoto([], { timestamp: NaN }), null)
})
