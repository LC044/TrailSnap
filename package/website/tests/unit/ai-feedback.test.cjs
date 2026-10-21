const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const vm = require('node:vm');
const { webcrypto } = require('node:crypto');

function receiptHarness(initial = '[]', failStorage = false) {
  const source = fs.readFileSync(path.resolve(__dirname, '../../../requirement-platform/web/src/stores/anonymousReceipts.ts'), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  let saved = initial;
  const module = { exports: {} };
  vm.runInNewContext(`(function(require, module, exports) { ${code}\n})`, {
    localStorage: { getItem: () => saved, setItem: (_, value) => { if (failStorage) throw Error('blocked'); saved = value; } },
    location: { origin: 'https://feedback.trailsnap.cn' },
    crypto: webcrypto, btoa,
  })(name => name === 'pinia' ? { defineStore: (_, setup) => setup } : { ref: value => ({ value }) }, module, module.exports);
  return { ...module.exports, saved: () => saved };
}

test('anonymous feedback automatically remembers independent edit receipts', () => {
  const h = receiptHarness();
  const store = h.useAnonymousReceipts();
  const token = h.newEditToken();
  assert.match(token, /^[A-Za-z0-9_-]{43}$/);
  assert.notEqual(token, h.newEditToken());
  const requirement = { id: 'one', public_number: 123 };
  assert.equal(store.save(requirement, token), true);
  assert.equal(store.tokenFor('one'), token);
  assert.equal(store.tokenFor('two'), undefined);
  assert.match(store.managementLink(requirement), /REQ-123#edit_token=/);
  const restored = receiptHarness(h.saved()).useAnonymousReceipts();
  assert.equal(restored.tokenFor('one'), token);
});

test('blocked or invalid browser storage does not lose in-session editing', () => {
  const h = receiptHarness('not-json', true);
  const store = h.useAnonymousReceipts();
  const token = h.newEditToken();
  assert.equal(store.save({ id: 'one', public_number: 1 }, token), false);
  assert.equal(store.tokenFor('one'), token);
  assert.equal(receiptHarness('[{"id":"one","number":1,"token":"short"}]').useAnonymousReceipts().receipts.value.length, 0);
});

test('feedback prompt defaults to ordinary-user HTTP without MCP setup', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../../src/views/settings/FeedbackPage.vue'), 'utf8');
  const { parse, compileScript } = require('vue/compiler-sfc');
  const descriptor = parse(source).descriptor;
  const script = compileScript(descriptor, { id: 'feedback-test' });
  assert.ok(script.content);
  assert.match(source, /ref<'feedback' \| 'design' \| 'code'>\('feedback'\)/);
  assert.match(source, /\/api\/agent-guide/);
  assert.match(source, /copyTextToClipboard\(prompt\.value\)/);
  assert.match(source, /无需配置 MCP/);
  assert.match(source, /promptText\.value\?\.select/);
});

test('AI continuation uses public context and never copies requirement secrets', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../../../requirement-platform/web/src/feedbackExperience.ts'), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(`(function(module, exports) { ${code}\n})`)(module, module.exports);
  const { continuationPrompt, nextAction } = module.exports;
  const prompt = continuationPrompt({
    public_number: 123,
    title: 'secret-title', description: 'secret-description', log_text: 'private-log',
    environment: { token: 'private-environment' }, edit_token: 'private-edit-token',
    submitter_contact: 'private@example.com',
  }, 'https://feedback.trailsnap.cn');
  assert.match(prompt, /\/requirements\/REQ-123/);
  assert.match(prompt, /\/api\/agent-guide/);
  assert.match(prompt, /不重复提交/);
  for (const secret of ['secret-title', 'secret-description', 'private-log', 'private-environment', 'private-edit-token', 'private@example.com']) assert.ok(!prompt.includes(secret));
  assert.match(nextAction('needs_information'), /补充信息/);
  assert.match(nextAction('merged'), /等待版本发布/);
  assert.match(nextAction('pending_review'), /暂时无需操作/);
});
