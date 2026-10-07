const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const vm = require('node:vm')
const ts = require('typescript')

function loadMotion(reduce = false) {
  let now = 0, id = 0
  const frames = new Map()
  const context = {
    exports: {}, window: { matchMedia: () => ({ matches: reduce }) },
    performance: { now: () => now },
    requestAnimationFrame: callback => { frames.set(++id, callback); return id },
    cancelAnimationFrame: frame => frames.delete(frame),
  }
  const source = fs.readFileSync(require('node:path').resolve(__dirname, '../../src/utils/motion.ts'), 'utf8')
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, context)
  return { ...context.exports, frames, tick(dt = 16) { now += dt; const pending = [...frames.values()]; frames.clear(); pending.forEach(callback => callback(now)) } }
}

test('rubber band preserves in-range travel and bounds overscroll in both directions', () => {
  const { rubberBand } = loadMotion()
  assert.equal(rubberBand(250, 0, 500), 250)
  assert.ok(rubberBand(-10000, 0, 500) > -72)
  assert.ok(rubberBand(10000, 0, 500) < 572)
  assert.ok(rubberBand(-100, 0, 500) < rubberBand(-20, 0, 500))
})

test('the same release position snaps differently with opposite flick velocities', () => {
  const { snapAnchor } = loadMotion()
  assert.equal(snapAnchor(300, 0, [0, 300, 600]), 300)
  assert.equal(snapAnchor(300, 1.5, [0, 300, 600]), 600)
  assert.equal(snapAnchor(300, -1.5, [0, 300, 600]), 0)
})

test('spring settles exactly once despite dropped frames, and cancellation stops updates', () => {
  const motion = loadMotion()
  let value = 0, completed = 0
  motion.spring(0, 600, 2, next => value = next, () => completed++)
  for (let i = 0; i < 200; i++) motion.tick(i % 4 ? 16 : 200)
  assert.equal(value, 600)
  assert.equal(completed, 1)
  const stop = motion.spring(600, 0, -1, next => value = next)
  motion.tick(); stop()
  const stoppedValue = value
  motion.tick()
  assert.equal(value, stoppedValue)
  assert.equal(motion.frames.size, 0)
})

test('reduced motion snaps immediately without scheduling animation', () => {
  const motion = loadMotion(true)
  let value, completed = 0
  motion.spring(0, 600, 2, next => value = next, () => completed++)
  assert.equal(value, 600)
  assert.equal(completed, 1)
  assert.equal(motion.frames.size, 0)
})
