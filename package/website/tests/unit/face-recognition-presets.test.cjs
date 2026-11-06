const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')

const source = fs.readFileSync(path.resolve(__dirname, '../../src/composables/settings/faceRecognitionPresets.ts'), 'utf8')
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
const loaded = { exports: {} }
vm.runInNewContext(`(function(module, exports) { ${code}\n})`)(loaded, loaded.exports)
const { faceRecognitionPresets, detectFaceRecognitionPreset } = loaded.exports

test('all three face presets survive saving and loading numeric parameters', () => {
  assert.deepEqual(Object.keys(faceRecognitionPresets), ['loose', 'normal', 'strict'])
  for (const [key, preset] of Object.entries(faceRecognitionPresets)) {
    const saved = JSON.parse(JSON.stringify(preset.parameters))
    assert.equal(detectFaceRecognitionPreset(saved), key)
    assert.ok(saved.face_cluster_merge_threshold <= saved.face_cluster_threshold)
    assert.ok(saved.face_identity_merge_threshold <= saved.face_identity_match_threshold)
    assert.ok(saved.face_rescan_auto_match_threshold <= saved.face_rescan_candidate_threshold)
    assert.ok(saved.face_rescan_candidate_threshold <= saved.face_rescan_removal_threshold)
  }
})

test('normal matches backend defaults and manual edits become custom', () => {
  const parameters = JSON.parse(JSON.stringify(faceRecognitionPresets.normal.parameters))
  assert.equal(parameters.face_cluster_threshold, .5)
  assert.equal(parameters.face_cluster_merge_threshold, .25)
  assert.equal(parameters.face_identity_match_threshold, .425)
  assert.equal(parameters.face_identity_merge_threshold, .2)
  parameters.face_identity_match_threshold = .41
  assert.equal(detectFaceRecognitionPreset(parameters), 'custom')
  assert.equal(faceRecognitionPresets.normal.parameters.face_identity_match_threshold, .425)
})

test('loose increases matching distances and strict raises display minimum', () => {
  const loose = faceRecognitionPresets.loose.parameters
  const normal = faceRecognitionPresets.normal.parameters
  const strict = faceRecognitionPresets.strict.parameters
  for (const field of ['face_cluster_threshold', 'face_cluster_merge_threshold', 'face_identity_match_threshold', 'face_identity_merge_threshold']) {
    assert.ok(loose[field] > normal[field] && normal[field] > strict[field])
  }
  assert.ok(loose.face_recognition_min_photos < normal.face_recognition_min_photos)
  assert.ok(strict.face_recognition_min_photos > normal.face_recognition_min_photos)
})
