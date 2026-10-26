const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const vm = require('node:vm');
const vueRouter = require('vue-router');
function load(file, overrides = {}) {
  const source = fs.readFileSync(path.resolve(__dirname, '../../src', file), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const mod = { exports: {} };
  vm.runInNewContext(`(function(require,module,exports){${code}\n})`, { URL, document: { title: '' } })(name => overrides[name] || require(name), mod, mod.exports);
  return mod.exports;
}
function fixture({ token = null, demo = true, fails = false } = {}) {
  const calls = [];
  const user = { token, async login() { calls.push('login'); if (fails) throw Error('offline'); user.token = 'demo-token'; return true; }, clearSession() { user.token = null; } };
  const page = { render: () => null };
  const router = load('router/index.ts', {
    'vue-router': { ...vueRouter, createWebHistory: vueRouter.createMemoryHistory, createRouter(options) {
      function flatten(routes) { return routes.map(r => ({ ...r, component: page, ...(r.children ? { children: flatten(r.children) } : {}) })); }
      return vueRouter.createRouter({ ...options, routes: flatten(options.routes) });
    } },
    '@/config/server': { isNativeApp: () => false },
    './navigationFeedback': { installNavigationFeedback() {} },
    './commonPages': { HomePage: page, PhotosPage: page, AlbumList: page, TicketPage: page },
    './authRedirect': load('router/authRedirect.ts'),
    '@/composables/demoEntry': load('composables/demoEntry.ts'),
    '@/api/auth': { authService: { async getAuthStatus() { calls.push('status'); return { has_users: true, demo_mode: demo }; } } },
    '@/stores/user': { useUserStore: () => user },
  }).default;
  return { router, calls, user };
}
test('explicit demo entry authenticates directly into footprint without visiting login', async () => {
  const { router, calls } = fixture();
  const visited = [];
  router.afterEach(to => visited.push(to.path));
  await router.push('/footprint?demo=1&year=2025#shanghai');
  assert.equal(router.currentRoute.value.fullPath, '/footprint?demo=1&year=2025#shanghai');
  assert.deepEqual(visited, ['/footprint']);
  assert.deepEqual(calls, ['status', 'login']);
});
test('normal instances and ordinary protected navigation never auto-login', async () => {
  const normal = fixture({ demo: false });
  await normal.router.push('/footprint?demo=1');
  assert.equal(normal.router.currentRoute.value.path, '/login');
  assert.deepEqual(normal.calls, ['status']);
  const ordinary = fixture();
  await ordinary.router.push('/footprint?year=2025&mode=route#city');
  assert.equal(ordinary.router.currentRoute.value.query.redirect, '/footprint?year=2025&mode=route#city');
  assert.deepEqual(ordinary.calls, []);
});
test('existing login session follows redirect including query and hash', async () => {
  const { router, calls } = fixture({ token: 'existing' });
  await router.push({ path: '/login', query: { redirect: '/footprint?year=2025&mode=route#city' } });
  assert.equal(router.currentRoute.value.fullPath, '/footprint?year=2025&mode=route#city');
  assert.deepEqual(calls, []);
});
test('failed direct demo entry retains destination and falls back without retry loop', async () => {
  const { router, calls, user } = fixture({ fails: true });
  await router.push('/footprint?demo=1#city');
  assert.equal(router.currentRoute.value.path, '/login');
  assert.equal(router.currentRoute.value.query.redirect, '/footprint?demo=1#city');
  assert.equal(router.currentRoute.value.query.demo_failed, '1');
  assert.equal(user.token, null);
  assert.deepEqual(calls, ['status', 'login']);
});
