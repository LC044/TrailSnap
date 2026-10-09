const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const vue = require('vue')
const compiler = require('vue/compiler-sfc')

function load(file, dependencies = {}) {
  let source = fs.readFileSync(path.resolve(__dirname, '../../src', file), 'utf8')
  if (file.endsWith('.vue')) source = compiler.compileScript(compiler.parse(source).descriptor, { id: file }).content
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const module = { exports: {} }
  vm.runInThisContext(`(function(require,module,exports){${code}\n})`, { filename: file })(name => {
    if (name === 'vue') return vue
    if (name in dependencies) return dependencies[name]
    throw Error(`Unexpected import: ${name}`)
  }, module, module.exports)
  return module.exports
}
const dates = load('utils/pickerDate.ts')
const Picker = load('components/ui/UnifiedDatePicker.vue', {
  'lucide-vue-next': { X: {} }, 'element-plus': { useFormItem: () => ({}) },
  '@vueuse/core': { useMediaQuery: () => vue.ref(true) },
  './DateWheelColumn.vue': {}, './ResponsiveDialog.vue': {}, '@/utils/pickerDate': dates,
}).default
const renderer = vue.createRenderer({
  insert() {}, remove() {}, createElement: () => ({}), createText: () => ({}), createComment: () => ({}),
  setText() {}, setElementText() {}, parentNode: () => null, nextSibling: () => null, patchProp() {},
})
function mountPicker(initial) {
  const props = vue.reactive({ type: 'date', placeholder: '选择日期', clearable: true, disabled: false, shortcuts: [], ...initial })
  const events = []
  let picker
  const app = renderer.createApp({ setup() {
    picker = Picker.setup(props, { expose() {}, emit(name, value) { events.push([name, value]); if (name === 'update:modelValue') props.modelValue = value } })
    return () => null
  } })
  app.mount({})
  return { picker, props, events, unmount: () => app.unmount() }
}

test('local date round trip preserves the calendar day and seconds', () => {
  const value = '2024-02-29T23:59:58'
  assert.equal(dates.formatPickerDate(dates.parsePickerDate(value), 'YYYY-MM-DDTHH:mm:ss'), value)
  assert.equal(dates.daysInMonth(2024, 2), 29)
  assert.equal(dates.daysInMonth(2023, 2), 28)
})

test('date and time edits preserve the other half, and cancellation leaves the model untouched', () => {
  const { picker: p, props, events, unmount } = mountPicker({ modelValue: '2024-02-29T23:59:58', type: 'datetime', valueFormat: 'YYYY-MM-DDTHH:mm:ss' })
  p.open(0, 'date'); p.year.value = 2023
  assert.equal(p.day.value, 28)
  p.confirm()
  assert.equal(props.modelValue, '2023-02-28T23:59:58')
  p.open(0, 'time'); p.hour.value = 12; p.confirm()
  assert.equal(props.modelValue, '2023-02-28T12:59:58')
  p.open(); p.day.value = 3; p.visible.value = false
  assert.equal(props.modelValue, '2023-02-28T12:59:58')
  assert.equal(events.filter(([name]) => name === 'change').length, 2)
  unmount()
})

test('range picker keeps two valid endpoints and rejects reversed ranges', () => {
  const { picker: p, props, unmount } = mountPicker({ modelValue: null, type: 'daterange', valueFormat: 'YYYY-MM-DD' })
  p.open(0); p.fill(new Date(2024, 0, 10)); p.confirm()
  assert.deepEqual(props.modelValue, ['2024-01-10', '2024-01-10'])
  p.open(1); p.fill(new Date(2024, 0, 9)); assert.ok(p.validationMessage.value); p.confirm()
  assert.deepEqual(props.modelValue, ['2024-01-10', '2024-01-10'])
  p.fill(new Date(2024, 0, 20)); p.confirm()
  assert.deepEqual(props.modelValue, ['2024-01-10', '2024-01-20'])
  unmount()
})

test('date limits, disabled days and default Date-valued fields keep their contracts', () => {
  const { picker: p, props, unmount } = mountPicker({ modelValue: new Date(2024, 0, 10), min: '2024-01-05', max: '2024-01-20', disabledDate: date => date.getDate() === 12 })
  p.open(); p.day.value = 4; assert.ok(p.validationMessage.value)
  p.day.value = 21; assert.ok(p.validationMessage.value)
  p.day.value = 12; assert.ok(p.validationMessage.value)
  p.day.value = 15; p.confirm()
  assert.ok(props.modelValue instanceof Date)
  assert.equal(props.modelValue.getDate(), 15)
  unmount()
})

test('time-only schedule picker preserves minute step and upper bound', () => {
  const { picker: p, props, unmount } = mountPicker({ modelValue: '02:30', type: 'time', start: '00:00', end: '23:30', step: '00:30' })
  p.open(); assert.deepEqual(p.minutes.value, [0, 30])
  p.hour.value = 3; p.confirm(); assert.equal(props.modelValue, '03:30')
  p.open(); p.hour.value = 23; p.minute.value = 59; assert.ok(p.validationMessage.value)
  unmount()
})

test('desktop uses the calendar and preserves inclusive bounds and model formats', () => {
  const { picker: p, props, unmount } = mountPicker({ modelValue: '2024-01-10', valueFormat: 'YYYY-MM-DD', min: '2024-01-05', max: '2024-01-20', disabledDate: date => date.getDate() === 12 })
  p.isMobile.value = false
  let opened = 0
  p.desktopPicker.value = { handleOpen() { opened++ } }
  p.open()
  assert.equal(opened, 1)
  assert.equal(p.visible.value, false)
  assert.equal(p.disabledDesktopDate(new Date(2024, 0, 4)), true)
  assert.equal(p.disabledDesktopDate(new Date(2024, 0, 5)), false)
  assert.equal(p.disabledDesktopDate(new Date(2024, 0, 20)), false)
  assert.equal(p.disabledDesktopDate(new Date(2024, 0, 21)), true)
  assert.equal(p.disabledDesktopDate(new Date(2024, 0, 12)), true)
  p.publish('2024-01-15')
  assert.equal(props.modelValue, '2024-01-15')
  unmount()
})

test('new dialog layers clear existing fullscreen and Element Plus panels', () => {
  const oldDocument = global.document, oldStyle = global.getComputedStyle
  const parent = { parentElement: null, z: '9999' }
  const panel = { parentElement: parent, z: 'auto', getClientRects: () => [1] }
  global.document = { querySelectorAll: () => [panel] }
  global.getComputedStyle = element => ({ zIndex: element.z })
  try {
    let next = 2000
    const first = dates.nextDialogZIndex(() => ++next)
    assert.equal(first, 10000)
    assert.equal(dates.nextDialogZIndex(() => ++next), 10001)
  } finally { global.document = oldDocument; global.getComputedStyle = oldStyle }
})
