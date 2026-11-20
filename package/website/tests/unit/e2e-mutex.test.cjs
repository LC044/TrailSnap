const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { execFileSync } = require('node:child_process')
const ts = require('typescript')

const source = fs.readFileSync(path.resolve(__dirname, '../e2e/helpers/mutex.ts'), 'utf8')
const code = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, esModuleInterop: true },
}).outputText

const module_ = { exports: {} }
new Function('require', 'module', 'exports', 'process', code)(require, module_, module_.exports, process)
const { acquireMutex } = module_.exports

const LOCK_DIR = path.join(os.tmpdir(), 'trailsnap-e2e-locks')
const lockFile = name => path.join(LOCK_DIR, `${name}.lock`)

function clearLock(name) {
  try { fs.unlinkSync(lockFile(name)) } catch { /* 不存在即可 */ }
}

test('acquireMutex creates the lock file and release removes it', async () => {
  const name = `unit-mutex-basic-${process.pid}`
  clearLock(name)
  const release = await acquireMutex(name, 2000)
  assert.equal(fs.existsSync(lockFile(name)), true)
  assert.equal(fs.readFileSync(lockFile(name), 'utf8').trim(), String(process.pid))
  await release()
  assert.equal(fs.existsSync(lockFile(name)), false)
  clearLock(name)
})

test('a lock file holding an unreadable pid is reclaimed', async () => {
  // 持锁进程在 open 与 write 之间被 kill 时，锁文件会残留 NUL 字节。
  // 旧实现要求 PID 可解析为真值数字，这类锁永远无法接管，导致后续用例全部超时。
  const name = `unit-mutex-garbage-${process.pid}`
  clearLock(name)
  fs.writeFileSync(lockFile(name), '\u0000\u0000\u0000\u0000')
  const release = await acquireMutex(name, 2000)
  assert.equal(fs.readFileSync(lockFile(name), 'utf8').trim(), String(process.pid))
  await release()
  clearLock(name)
})

test('a lock file holding an empty pid is reclaimed', async () => {
  const name = `unit-mutex-empty-${process.pid}`
  clearLock(name)
  fs.writeFileSync(lockFile(name), '')
  const release = await acquireMutex(name, 2000)
  assert.equal(fs.readFileSync(lockFile(name), 'utf8').trim(), String(process.pid))
  await release()
  clearLock(name)
})

test('a lock held by a dead process is reclaimed', async () => {
  const name = `unit-mutex-dead-${process.pid}`
  clearLock(name)
  const deadPid = execFileSync(process.execPath, ['-e', 'process.stdout.write(String(process.pid))']).toString().trim()
  fs.writeFileSync(lockFile(name), deadPid)
  await new Promise(r => setTimeout(r, 300))
  const release = await acquireMutex(name, 3000)
  assert.equal(fs.readFileSync(lockFile(name), 'utf8').trim(), String(process.pid))
  await release()
  clearLock(name)
})

test('a lock held by a live process is not stolen', async () => {
  const name = `unit-mutex-live-${process.pid}`
  clearLock(name)
  fs.writeFileSync(lockFile(name), String(process.pid))
  await assert.rejects(() => acquireMutex(name, 300), /timed out/)
  clearLock(name)
})