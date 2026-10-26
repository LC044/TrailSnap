const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const vue = require('vue')
const compiler = require('vue/compiler-sfc')

const source = fs.readFileSync(path.resolve(__dirname, '../../src/components/PhotoLightbox.vue'), 'utf8')
const { descriptor } = compiler.parse(source)
const script = ts.createSourceFile('lightbox.ts', descriptor.scriptSetup.content, ts.ScriptTarget.Latest, true)
const names = [
  'photoProcessingOperations', 'photoProcessingTrackers', 'processingMenuVisible',
  'processingTrackerKey', 'currentPhotoProcessingTracker', 'isPhotoProcessingActive',
  'photoProcessingOperationLabel', 'startPhotoProcessing', 'refreshPhotoProcessingResult',
  'refreshedPanorama', 'panoramaRevision', 'isPanoramaPhoto',
]
const declarations = script.statements.filter(node => ts.isVariableStatement(node) &&
  node.declarationList.declarations.some(declaration => names.includes(declaration.name.getText(script))))
assert.equal(declarations.length, names.length)
const code = ts.transpileModule(declarations.map(node => node.getText(script)).join('\n') +
  `\nglobalThis.subject = { ${names.join(', ')} }`, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText

function setup(overrides = {}) {
  const calls = []
  const context = {
    ref: vue.ref, computed: vue.computed,
    props: { image: { id: 'photo-1', file_type: 'image', panorama_projection: null } },
    FileText: 'file', Sparkles: 'sparkles', ScanFace: 'face', ScanText: 'text', Tags: 'tags', Binary: 'binary',
    tasksApi: { createPhotoProcessingTask: async (...args) => {
      calls.push(['create', ...args])
      return { task: { id: 'task-1', status: 'pending' }, reused: false }
    } },
    albumService: { getPhotosByIds: async () => [{ id: 'photo-1', panorama_projection: 'equirectangular' }] },
    fetchMetadata: async id => calls.push(['metadata', id]),
    fetchOCR: async () => {}, fetchDescription: async () => {},
    ensurePhotoProcessingPolling: () => calls.push(['poll']),
    ElMessage: { success() {}, error() {}, info() {} },
    emit: (...args) => calls.push(['emit', ...args]),
    console,
    ...overrides,
  }
  vm.runInNewContext(code, context)
  return { subject: context.subject, context, calls }
}

test('metadata action queues a forced task for the current photo and prevents duplicate clicks', async () => {
  const { subject, calls } = setup()
  assert.equal(subject.photoProcessingOperations.filter(item => item.operation === 'EXTRACT_METADATA').length, 1)
  await subject.startPhotoProcessing('EXTRACT_METADATA')
  await subject.startPhotoProcessing('EXTRACT_METADATA')
  assert.deepEqual(calls.filter(call => call[0] === 'create'), [['create', 'photo-1', 'EXTRACT_METADATA', true]])
  assert.equal(subject.currentPhotoProcessingTracker('EXTRACT_METADATA').status, 'pending')
})

test('metadata completion refreshes details and activates newly detected panorama', async () => {
  const { subject, calls } = setup()
  assert.equal(subject.isPanoramaPhoto.value, false)
  await subject.refreshPhotoProcessingResult({ photoId: 'photo-1', operation: 'EXTRACT_METADATA' })
  assert.deepEqual(calls[0], ['metadata', 'photo-1'])
  assert.equal(subject.isPanoramaPhoto.value, true)
  assert.equal(subject.panoramaRevision.value, 1)
  assert.equal(calls[1][0], 'emit')
  assert.equal(calls[1][2].taskType, 'EXTRACT_METADATA')
})

test('metadata refresh does not replace panorama state after navigating to another photo', async () => {
  const { subject, context, calls } = setup()
  context.albumService.getPhotosByIds = async () => {
    context.props.image = { id: 'photo-2', file_type: 'image' }
    return [{ id: 'photo-1', panorama_projection: 'equirectangular' }]
  }
  await subject.refreshPhotoProcessingResult({ photoId: 'photo-1', operation: 'EXTRACT_METADATA' })
  assert.equal(subject.refreshedPanorama.value, null)
  assert.equal(subject.isPanoramaPhoto.value, false)
  assert.equal(calls.some(call => call[0] === 'emit'), false)
})
