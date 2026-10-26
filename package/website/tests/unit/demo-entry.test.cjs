const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const vm = require('node:vm');
const source = fs.readFileSync(path.resolve(__dirname, '../../src/composables/demoEntry.ts'), 'utf8');
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const exported = { exports: {} };
vm.runInNewContext(`(function(module, exports) { ${code}\n})`)(exported, exported.exports);
const { createDemoEntry } = exported.exports;

test('normal and uninitialized servers never use the demo account', async () => {
  let calls = 0;
  const enter = createDemoEntry(async () => { calls++; }, async () => { calls++; });
  assert.equal(await enter({ demo_mode: false, has_users: true }), false);
  assert.equal(await enter({ demo_mode: true, has_users: false }), false);
  assert.equal(calls, 0);
});

test('demo enters the requested route after login, once per page visit', async () => {
  const actions = [];
  const enter = createDemoEntry(async () => actions.push('login'), async () => actions.push('/footprint'));
  assert.equal(await enter({ demo_mode: true, has_users: true }), true);
  assert.equal(await enter({ demo_mode: true, has_users: true }), false);
  assert.deepEqual(actions, ['login', '/footprint']);
});

test('failed demo login does not navigate or start an automatic retry loop', async () => {
  let calls = 0, navigated = false;
  const enter = createDemoEntry(async () => { calls++; throw Error('offline'); }, async () => { navigated = true; });
  await assert.rejects(enter({ demo_mode: true, has_users: true }), /offline/);
  assert.equal(await enter({ demo_mode: true, has_users: true }), false);
  assert.equal(calls, 1);
  assert.equal(navigated, false);
});
