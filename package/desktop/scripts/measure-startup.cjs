// Windows desktop benchmark, using WebView2's local DevTools endpoint.
// No access logs, credentials, or changes to the user's normal library are needed.
const { spawn, execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const net = require('node:net');
const { performance } = require('node:perf_hooks');

const [executable, output, dataRootArg, trialsArg = '5', serverBinary] = process.argv.slice(2);
if (!executable || !output) throw new Error('Usage: node measure-startup.cjs EXE OUTPUT [DATA_ROOT] [TRIALS] [SERVER_EXE]');
const dataRoot = path.resolve(dataRootArg || fs.mkdtempSync(path.join(os.tmpdir(), 'trailsnap-startup-')));
fs.mkdirSync(dataRoot, { recursive: true });
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function freePort() {
  const listener = net.createServer();
  await new Promise(resolve => listener.listen(0, '127.0.0.1', resolve));
  const port = listener.address().port;
  await new Promise(resolve => listener.close(resolve));
  return port;
}

async function connect(port, child) {
  const deadline = performance.now() + 60000;
  while (performance.now() < deadline) {
    if (child.exitCode !== null) throw new Error(`Desktop exited: ${child.exitCode}`);
    try {
      const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`, { signal: AbortSignal.timeout(500) })).json();
      const page = targets.find(target => target.type === 'page' && target.webSocketDebuggerUrl);
      if (page) {
        const ws = new WebSocket(page.webSocketDebuggerUrl);
        await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
        let id = 0;
        const pending = new Map();
        ws.onmessage = event => {
          const message = JSON.parse(event.data);
          if (pending.has(message.id)) {
            const { resolve, reject } = pending.get(message.id);
            pending.delete(message.id);
            message.error ? reject(new Error(message.error.message)) : resolve(message.result);
          }
        };
        return {
          send(method, params = {}) {
            return new Promise((resolve, reject) => {
              const next = ++id;
              pending.set(next, { resolve, reject });
              ws.send(JSON.stringify({ id: next, method, params }));
            });
          },
          close() { ws.close(); },
        };
      }
    } catch { /* WebView2 has not published its target yet. */ }
    await delay(25);
  }
  throw new Error('WebView2 DevTools target did not appear');
}

async function measure(index) {
  const debugPort = await freePort();
  const started = performance.now();
  const child = spawn(path.resolve(executable), [], {
    windowsHide: true,
    env: {
      ...process.env,
      LOCALAPPDATA: dataRoot,
      WEBVIEW2_USER_DATA_FOLDER: path.join(dataRoot, 'webview'),
      WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS: `--remote-debugging-port=${debugPort}`,
      ...(serverBinary ? { TS_DESKTOP_SERVER_BINARY: path.resolve(serverBinary) } : {}),
    },
    stdio: 'ignore',
  });
  let cdp;
  let healthMs;
  let finished = false;
  const healthProbe = (async () => {
    while (!finished && performance.now() - started < 60000) {
      try {
        const config = JSON.parse(fs.readFileSync(path.join(dataRoot, 'TrailSnap-desktop.json'), 'utf8'));
        const response = await fetch(`http://127.0.0.1:${config.serverPort}/health-check`, { signal: AbortSignal.timeout(100) });
        if (response.ok) { healthMs = performance.now() - started; return; }
      } catch { /* The server has not bound the saved port yet. */ }
      await delay(25);
    }
  })();
  const result = { run: index };
  try {
    cdp = await connect(debugPort, child);
    result.devToolsMs = performance.now() - started;
    const deadline = started + 60000;
    while (performance.now() < deadline) {
      const response = await cdp.send('Runtime.evaluate', {
        expression: `(async () => { const runtime = window.__TAURI_INTERNALS__ ? await window.__TAURI_INTERNALS__.invoke('desktop_runtime_status') : null; return JSON.stringify({
          runtimeReady: !!runtime?.ready,
          splash: !!document.querySelector('.boot-splash'),
          home: [...document.querySelectorAll('h1')].some(el => el.textContent.trim() === '首页'),
          loading: !!document.querySelector('[class*="min-h-[400px]"]'),
          content: !!document.querySelector('.ts-browse-page > .space-y-4'),
          entries: performance.getEntriesByType('resource').filter(e => /\\/api\\/(auth\\/desktop-session|users\\/me|stats\\/dashboard)/.test(e.name)).map(e => ({url: new URL(e.name).pathname, endMs: e.responseEnd})),
          marks: performance.getEntriesByType('mark').map(e => ({name: e.name, atMs: e.startTime}))
        }); })()`,
        returnByValue: true,
        awaitPromise: true,
      });
      if (!response.result.value) { await delay(25); continue; }
      const state = JSON.parse(response.result.value);
      const now = performance.now() - started;
      if (state.runtimeReady && result.runtimeReadyMs === undefined) result.runtimeReadyMs = now;
      if (!state.splash && state.home && result.homeShellMs === undefined) result.homeShellMs = now;
      if (!state.splash && state.home && !state.loading && state.content) {
        result.homeDataMs = now;
        result.pageResourceTimings = state.entries;
        result.pageMarks = state.marks;
        if (index === Number(trialsArg)) {
          const screenshot = await cdp.send('Page.captureScreenshot', { format: 'png' });
          fs.writeFileSync(output.replace(/\.json$/i, '.png'), Buffer.from(screenshot.data, 'base64'));
        }
        break;
      }
      await delay(25);
    }
    if (result.homeDataMs === undefined) throw new Error('Home data did not render within 60 seconds');
    finished = true;
    await healthProbe;
    result.backendReadyMs = healthMs;
    return result;
  } finally {
    finished = true;
    cdp?.close();
    // Terminate only the process tree launched by this benchmark.
    try { execFileSync('taskkill', ['/pid', String(child.pid), '/t', '/f'], { windowsHide: true, stdio: 'ignore' }); } catch {}
    await healthProbe;
    await delay(300);
  }
}

(async () => {
  fs.mkdirSync(path.dirname(path.resolve(output)), { recursive: true });
  const results = [];
  const firstRun = process.env.TS_STARTUP_SKIP_WARMUP === '1' ? 1 : 0;
  for (let index = firstRun; index <= Number(trialsArg); index++) {
    const result = await measure(index);
    results.push(result);
    fs.writeFileSync(output, JSON.stringify({ executable: path.resolve(executable), serverBinary, dataRoot, note: 'Run 0 is warmup; repeated process launches, OS disk cache retained; empty isolated library; WebView2 debugging enabled equally for both builds.', results }, null, 2));
    console.log(JSON.stringify(result));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
