const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

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
