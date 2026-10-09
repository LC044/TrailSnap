const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const vm = require('node:vm');

function harness(fetchStatus) {
  let cleanup, scheduled, callback;
  const source = fs.readFileSync(path.resolve(__dirname, '../../src/composables/useAuthStatus.ts'), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(`(function(require, module, exports) { ${code}\n})`, {
    AbortController,
    setTimeout(fn) { scheduled = true; callback = fn; return 1; },
    clearTimeout() { scheduled = false; },
  })(name => name === 'vue'
    ? { ref: value => ({ value }), onBeforeUnmount: fn => cleanup = fn }
    : { authService: { getAuthStatus: fetchStatus } }, module, module.exports);
  return {
    use: module.exports.useAuthStatus,
    cleanup: () => cleanup(),
    retry: () => callback(),
    scheduled: () => scheduled,
  };
}

test('authentication recovers automatically after the API becomes available', async () => {
  let calls = 0, redirected = false;
  const h = harness(async options => {
    assert.equal(options.silentError, true);
    if (++calls === 1) throw Error('API not listening yet');
    return { has_users: false, allow_registration: false };
  });
  const auth = h.use(status => redirected = !status.has_users);
  await auth.check();
  assert.equal(auth.state.value, 'unavailable');
  assert.equal(h.scheduled(), true);
  h.retry();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(auth.state.value, 'ready');
  assert.equal(redirected, true);
  assert.equal(h.scheduled(), false);
  h.cleanup();
});

test('leaving onboarding cancels requests and prevents stale redirects or retries', async () => {
  let resolveRequest, signal, ready = false;
  const h = harness(options => {
    signal = options.signal;
    return new Promise(resolve => resolveRequest = resolve);
  });
  const auth = h.use(() => ready = true);
  const pending = auth.check();
  h.cleanup();
  resolveRequest({ has_users: false });
  await pending;
  assert.equal(signal.aborted, true);
  assert.equal(ready, false);
  assert.equal(h.scheduled(), false);
});
