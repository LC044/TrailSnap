const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const source = fs.readFileSync(path.resolve(__dirname, '../../src/config/settingsNavigation.ts'), 'utf8')
const moduleResult = { exports: {} }
vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText,
  { module: moduleResult, exports: moduleResult.exports })
const { resolveSettingsTab } = moduleResult.exports

test('saved settings links keep task and mobile backup destinations', () => {
  for (const [oldTab, current] of [['task-management', 'tasks'], ['mobile-backup-settings', 'mobile-backup'], ['captions', 'ai-models']]) {
    assert.equal(resolveSettingsTab(`#${oldTab}`, undefined), current)
    assert.equal(resolveSettingsTab('', oldTab), current)
  }
})
test('hash takes priority and current destinations remain stable', () => {
  for (const tab of ['basic', 'map', 'recognition', 'maintenance', 'tasks', 'external', 'ai-models', 'profile', 'performance']) {
    assert.equal(resolveSettingsTab(`#${tab}`, 'profile'), tab)
    assert.equal(resolveSettingsTab('', tab), tab)
  }
  assert.equal(resolveSettingsTab('', ['tasks']), '')
  assert.equal(resolveSettingsTab('', undefined), '')
})
