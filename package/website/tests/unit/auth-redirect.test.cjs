const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const vm = require('node:vm');
const source = fs.readFileSync(path.resolve(__dirname, '../../src/router/authRedirect.ts'), 'utf8');
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const mod = { exports: {} };
vm.runInNewContext(`(function(module, exports) { ${code}\n})`, { URL })(mod, mod.exports);
const { safeAuthRedirect, loginLocation } = mod.exports;

test('login preserves the complete footprint destination as one query value', () => {
  const destination = '/footprint?year=2025&demo=1#shanghai';
  assert.equal(safeAuthRedirect(destination), destination);
  const login = loginLocation(destination);
  assert.equal(login.path, '/login');
  assert.equal(login.query.redirect, destination);
  assert.equal(loginLocation(destination, true).query.demo_failed, '1');
});

test('unsafe and recursive login redirects fall back to home', () => {
  for (const redirect of [undefined, null, ['/', '/footprint'], 'https://evil.test', '//evil.test', '/\\evil.test', '/\nevil.test', '/login?redirect=/login', '/register', '/a/../login']) {
    assert.equal(safeAuthRedirect(redirect), '/', String(redirect));
  }
  assert.equal(safeAuthRedirect('/photos?type=image&sort=date#2025'), '/photos?type=image&sort=date#2025');
});
