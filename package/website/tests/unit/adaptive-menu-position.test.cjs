const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const compiler = require('vue/compiler-sfc')

const source = fs.readFileSync(path.resolve(__dirname, '../../src/components/ui/AdaptiveMenu.vue'), 'utf8')
const { descriptor } = compiler.parse(source)
const script = ts.createSourceFile('menu.ts', descriptor.scriptSetup.content, ts.ScriptTarget.Latest, true)
const declaration = script.statements.find(node => ts.isVariableStatement(node) &&
  node.declarationList.declarations.some(d => d.name.getText(script) === 'positionMenu'))
const code = ts.transpileModule(declaration.getText(script) + '\nglobalThis.positionMenu = positionMenu', {
  compilerOptions: { target: ts.ScriptTarget.ES2022 },
}).outputText

async function position({ top = 700, height = 320, viewportTop = 0 } = {}) {
  const rect = { top, bottom: top + 44, left: 1000, right: 1080, width: 80 }
  const context = {
    props: { placement: 'top-end' }, nextTick: async () => {},
    trigger: () => ({ getBoundingClientRect: () => rect }),
    menuRef: { value: { offsetWidth: 220, offsetHeight: height } },
    window: { innerWidth: 1280, innerHeight: 800, visualViewport: { offsetTop: viewportTop, height: 800 } },
    menuStyle: { value: {} }, layerZIndex: 3000,
  }
  vm.runInNewContext(code, context)
  await context.positionMenu()
  return context.menuStyle.value
}

test('bottom toolbar menu opens above its trigger and aligns right edges', async () => {
  const style = await position()
  assert.equal(style.top, '362px')
  assert.equal(style.left, '860px')
  assert.equal(parseFloat(style.top) + 320, 682)
  assert.ok(style.transformOrigin.endsWith('100%'))
})

test('tall menu scrolls within space above trigger without covering it', async () => {
  const style = await position({ top: 200, height: 600, viewportTop: 20 })
  assert.equal(style.top, '28px')
  assert.equal(style.maxHeight, '154px')
  assert.equal(style.overflowY, 'auto')
  assert.equal(parseFloat(style.top) + parseFloat(style.maxHeight), 182)
})
