const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')
const vue = require('vue')

function load(filename, dependencies = {}) {
  const source = fs.readFileSync(path.resolve(__dirname, '../../src', filename), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  const module = { exports: {} }
  new Function('require', 'module', 'exports', code)(name => dependencies[name] ?? require(name), module, module.exports)
  return module.exports
}
const sizes = load('utils/momentLayout.ts')
const { useVirtualLayout } = load('composables/useVirtualLayout.ts', {
  vue,
  '@/utils/momentLayout': sizes,
  '@/utils/photoGridLayout': load('utils/photoGridLayout.ts'),
})

test('a single portrait highlight reserves its full height and updates when highlights change', async () => {
  const scope = vue.effectScope()
  const highlights = vue.ref({ '2025-11-4': { photoIds: ['portrait'] } })
  const photo = (id, width, height) => ({ id, width, height, timestamp: new Date(2025, 10, 4).getTime() })
  const layout = scope.run(() => useVirtualLayout({
    timelineStats: vue.ref({ timeline: [
      { year: 2025, month: 11, day: 4, count: 2 },
      { year: 2025, month: 11, day: 2, count: 1 },
    ] }),
    containerWidth: vue.ref(1000), layoutMode: vue.ref('moments'), viewSize: vue.ref('md'),
    photos: vue.ref([photo('wide', 1600, 900), photo('portrait', 600, 800)]),
    dayHighlights: highlights,
  }))
  try {
    const day = () => layout.monthBlocks.value[0].days[0]
    assert.equal(day().rows, 1)
    assert.ok(day().height >= 250 + 120 + 32)
    assert.equal(layout.monthBlocks.value[0].days[1].top, day().height)
    const portraitHeight = day().height
    highlights.value['2025-11-4'].photoIds = ['wide']
    await vue.nextTick()
    assert.equal(portraitHeight - day().height, 250 - 135)
    highlights.value['2025-11-4'].photoIds = []
    await vue.nextTick()
    assert.equal(day().rows, 1)
    assert.ok(day().height < portraitHeight)
  } finally { scope.stop() }
})

test('single photo dimensions are bounded for portrait, landscape and missing metadata', () => {
  assert.deepEqual(sizes.getMomentSinglePhotoSize({ width: 600, height: 800 }), { width: 188, height: 250 })
  assert.deepEqual(sizes.getMomentSinglePhotoSize({ width: 1600, height: 900 }), { width: 240, height: 135 })
  assert.deepEqual(sizes.getMomentSinglePhotoSize({}), { width: 240, height: 250 })
})
