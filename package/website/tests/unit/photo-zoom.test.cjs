const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const moduleObject = { exports: {} }
const source = fs.readFileSync(path.resolve(__dirname, '../../src/utils/photoZoom.ts'), 'utf8')
vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText,
  { module: moduleObject, exports: moduleObject.exports })
const { constrainPhotoPan, zoomPhotoAt } = moduleObject.exports
const viewport = { width: 400, height: 800 }, landscape = { width: 1600, height: 1000 }

test('a zoomed drag follows the same screen distance rather than multiplying by zoom', () => {
  const start = constrainPhotoPan({ x: 0, y: 0 }, 3, viewport, landscape)
  const moved = constrainPhotoPan({ x: start.x + 30, y: start.y }, 3, viewport, landscape)
  assert.equal(moved.x - start.x, 30)
  assert.equal(moved.y, 0)
})

test('pan clamps each axis to the actual fitted image, including letterboxed axes', () => {
  const pan = constrainPhotoPan({ x: 10000, y: -10000 }, 2.5, viewport, landscape)
  assert.equal(pan.x, 300)
  assert.equal(pan.y, 0)
  const portrait = constrainPhotoPan({ x: -10000, y: 10000 }, 2.5, viewport, { width: 1000, height: 2000 })
  assert.equal(portrait.x, -300)
  assert.equal(portrait.y, 600)
})

test('zoom preserves the photo coordinate under an off-center pointer', () => {
  const pan = { x: 30, y: -20 }, point = { x: 80, y: 100 }
  const result = zoomPhotoAt(pan, 1.5, 3, point)
  assert.equal((point.x - result.x) / 3, (point.x - pan.x) / 1.5)
  assert.equal((point.y - result.y) / 3, (point.y - pan.y) / 1.5)
})

test('reset and unavailable dimensions return a centered, unshifted photo', () => {
  for (const scale of [0.5, 1]) {
    const pan = constrainPhotoPan({ x: 120, y: -200 }, scale, viewport, landscape)
    assert.equal(pan.x, 0); assert.equal(pan.y, 0)
  }
  const pan = constrainPhotoPan({ x: 120, y: 200 }, 3, viewport, { width: 0, height: 0 })
  assert.equal(pan.x, 0); assert.equal(pan.y, 0)
})
