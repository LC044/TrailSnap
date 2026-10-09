const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const axios = require('axios');

// Execute the real interceptor and Axios pipeline with only HTTP/UI boundaries replaced.
function harness(outcomes, { holdBackoff = false } = {}) {
  const messages = [], requests = [], delays = [], timers = new Map();
  let timerId = 0, resetCount = 0;
  const user = { token: 'saved-token', resetState() { resetCount++; } };
  const source = fs.readFileSync(path.resolve(__dirname, '../../src/utils/request.ts'), 'utf8')
    .replace('import.meta.env.VITE_API_BASE_URL', "''");
  const code = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const module = { exports: {} };
  const dependencies = {
    axios,
    'element-plus': { ElMessage: { error: message => messages.push(message) } },
    '@/router': {},
    '@/stores/user': { useUserStore: () => user },
    '@/config/server': {
      getServerUrl: () => '', hasConfiguredServer: () => false,
      isNativeApp: () => false, isTauriApp: () => false,
    },
  };
  vm.runInNewContext(`(function(require, module, exports) { ${code}\n})`, {
    Blob, URLSearchParams, window: { location: { pathname: '/home' } },
    setTimeout(fn, delay) {
      delays.push(delay);
      const id = ++timerId;
      timers.set(id, holdBackoff ? fn : setTimeout(fn, 0));
      return id;
    },
    clearTimeout(id) {
      if (!holdBackoff) clearTimeout(timers.get(id));
      timers.delete(id);
    },
  })(name => {
    assert.ok(name in dependencies, `Unexpected dependency: ${name}`);
    return dependencies[name];
  }, module, module.exports);
  const service = module.exports.default;
  service.defaults.adapter = async config => {
    requests.push(config);
    const outcome = outcomes.shift();
    assert.notEqual(outcome, undefined, 'Unexpected extra request');
    if (outcome === 'ok') return { config, status: 200, data: { code: 0, data: ['loaded'] }, headers: {} };
    const response = typeof outcome === 'number'
      ? { config, status: outcome, data: {}, headers: {} } : undefined;
    throw new axios.AxiosError('failed', response ? 'ERR_BAD_RESPONSE' : outcome, config, {}, response);
  };
  return { service, messages, requests, delays, timers, user, resets: () => resetCount };
}

test('transient read failures recover silently and preserve request options and session', async () => {
  for (const outcome of ['ERR_NETWORK', 'ECONNABORTED', 'ETIMEDOUT', 502, 503, 504]) {
    const h = harness([outcome, outcome, 'ok']);
    const result = await h.service.get('/storage', { params: { page: 2 }, timeout: 1234 });
    assert.deepEqual(Array.from(result.data), ['loaded']);
    assert.equal(h.requests.length, 3);
    assert.deepEqual(h.delays, [500, 1000]);
    assert.equal(h.messages.length, 0);
    assert.equal(h.resets(), 0);
    for (const config of h.requests) {
      assert.equal(config.params.page, 2);
      assert.equal(config.timeout, 1234);
      assert.equal(config.headers.Authorization, 'Bearer saved-token');
    }
  }
});

test('retry exhaustion rejects and shows a single accurate timeout message', async () => {
  const h = harness(Array(3).fill('ECONNABORTED'));
  await assert.rejects(h.service.get('/storage'), error => error.code === 'ECONNABORTED');
  assert.equal(h.requests.length, 3);
  assert.equal(h.messages.length, 1);
  assert.match(h.messages[0], /请求超时/);
  assert.equal(h.user.token, 'saved-token');
});

test('HEAD retries, while genuine 401 still expires the session immediately', async () => {
  const head = harness([503, 'ok']);
  await head.service.head('/health');
  assert.equal(head.requests.length, 2);
  const unauthorized = harness([401]);
  await assert.rejects(unauthorized.service.get('/storage'));
  assert.equal(unauthorized.requests.length, 1);
  assert.equal(unauthorized.resets(), 1);
  assert.deepEqual(unauthorized.messages, ['登录已过期，请重新登录']);
});

test('writes, explicit opt-out, non-transient HTTP errors and business errors are not retried', async () => {
  for (const method of ['post', 'put', 'patch', 'delete']) {
    const h = harness(['ERR_NETWORK']);
    await assert.rejects(h.service.request({ url: '/storage', method }));
    assert.equal(h.requests.length, 1);
  }
  for (const status of [403, 404, 422, 500]) {
    const h = harness([status]);
    await assert.rejects(h.service.get('/storage'));
    assert.equal(h.requests.length, 1);
  }
  const h = harness(['ERR_NETWORK']);
  await assert.rejects(h.service.get('/storage', { retry: false }));
  assert.equal(h.requests.length, 1);
  const business = harness([]);
  business.service.defaults.adapter = async config => ({ config, status: 200, data: { code: 400, msg: 'invalid' } });
  await assert.rejects(business.service.get('/storage'));
  assert.deepEqual(business.delays, []);
  assert.deepEqual(business.messages, ['invalid']);
});

test('concurrent final connection errors share a toast; silentError stays silent', async () => {
  const h = harness(Array(6).fill('ERR_NETWORK'));
  const results = await Promise.allSettled([h.service.get('/a'), h.service.get('/b')]);
  assert.ok(results.every(result => result.status === 'rejected'));
  assert.equal(h.messages.length, 1);
  const silent = harness(Array(3).fill(503));
  await assert.rejects(silent.service.get('/storage', { silentError: true }));
  assert.equal(silent.requests.length, 3);
  assert.equal(silent.messages.length, 0);
});

test('aborting during backoff cancels immediately without retry or toast', async () => {
  const h = harness(['ERR_NETWORK'], { holdBackoff: true });
  const controller = new AbortController();
  const pending = h.service.get('/storage', { signal: controller.signal });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.timers.size, 1);
  controller.abort();
  await assert.rejects(pending, error => axios.isCancel(error));
  assert.equal(h.timers.size, 0);
  assert.equal(h.requests.length, 1);
  assert.equal(h.messages.length, 0);
});

test('legacy cancel tokens also cancel backoff; canceled requests never display errors', async () => {
  const h = harness(['ERR_NETWORK'], { holdBackoff: true });
  const cancel = axios.CancelToken.source();
  const pending = h.service.get('/storage', { cancelToken: cancel.token });
  await new Promise(resolve => setImmediate(resolve));
  cancel.cancel();
  await assert.rejects(pending, error => axios.isCancel(error));
  assert.equal(h.timers.size, 0);
  assert.equal(h.requests.length, 1);
  assert.equal(h.messages.length, 0);
  const canceled = harness(['ERR_CANCELED']);
  await assert.rejects(canceled.service.get('/storage'));
  assert.equal(canceled.messages.length, 0);
});
