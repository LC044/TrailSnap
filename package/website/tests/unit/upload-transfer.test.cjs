const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const crypto = require('node:crypto')

function load(name, dependencies = {}) {
  const source = fs.readFileSync(path.resolve(__dirname, '../../src/utils', name + '.ts'), 'utf8').replaceAll('import.meta.url', '"file:///upload-test"')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const module = { exports: {} }
  vm.runInThisContext(`(function(require,module,exports){${code}\n})`) (
    name => dependencies[name] || require(name), module, module.exports)
  return module.exports
}
const transfer = load('uploadTransfer')
const manual = load('manualUpload', { './uploadTransfer': transfer })
const { hashFileChunks } = load('fileIntegrity')
const backup = load('backupTransfer')

test('pipeline starts transfer before a slow hash finishes and immediately fills free slots', async () => {
  let releaseHash, releaseTransfer, reportThird
  const hashBlocked = new Promise(resolve => { releaseHash = resolve })
  const transferBlocked = new Promise(resolve => { releaseTransfer = resolve })
  const thirdStarted = new Promise(resolve => { reportThird = resolve })
  const events = []
  const run = backup.transferPipeline([0, 1, 2, 3], 2, () => ({ mediaConcurrency: 2, maxInFlightBytes: 20 }),
    async id => { if (id === 1) await hashBlocked; return { id, size: 5 } },
    async item => { events.push(item.id); if (item.id === 0) await transferBlocked; if (item.id === 3) reportThird() })
  await thirdStarted
  assert.deepEqual(events, [0, 2, 3])
  releaseHash(); releaseTransfer()
  await run
  assert.ok(events.includes(1))
})

test('pipeline obeys byte budget and drains all active jobs on preparation failure', async () => {
  let bytes = 0, peak = 0
  await backup.transferPipeline([9, 9, 30, 9], 2, () => ({ mediaConcurrency: 3, maxInFlightBytes: 18 }),
    async size => ({ size }), async item => {
      bytes += item.size; peak = Math.max(peak, bytes)
      assert.ok(bytes <= 18 || bytes === item.size)
      await new Promise(resolve => setTimeout(resolve, 2)); bytes -= item.size
    })
  assert.equal(peak, 30)
  let finished = false
  await assert.rejects(backup.transferPipeline([0, 1], 1, () => ({ mediaConcurrency: 2, maxInFlightBytes: 10 }),
    async id => { if (id) { await new Promise(resolve => setTimeout(resolve, 1)); throw new Error('hash failed') }; return { size: 1 } },
    async () => { await new Promise(resolve => setTimeout(resolve, 5)); finished = true }), /hash failed/)
  assert.equal(finished, true)
})

test('streaming worker overlaps hashing and transfer with bounded credits and exact integrity', async () => {
  const originalWorker = global.Worker
  const source = fs.readFileSync(path.resolve(__dirname, '../../src/workers/uploadHash.worker.ts'), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  global.Worker = class {
    constructor() {
      this.self = { postMessage: data => setImmediate(() => { if (!this.stopped) this.onmessage?.({ data }) }) }
      vm.runInNewContext(code, { self: this.self, exports: {}, require: () => ({ hashFileChunks }) })
    }
    postMessage(data) { setImmediate(() => { if (!this.stopped) this.self.onmessage({ data }).catch(error => this.onerror?.(error)) }) }
    terminate() { this.stopped = true }
  }
  try {
    const bytes = crypto.randomBytes(15001)
    const file = new Blob([bytes])
    const received = []
    let active = 0, peak = 0
    const result = await manual.uploadStreamingChunks(file, 4096, 2, new AbortController().signal,
      async (index, chunk, hash, report) => {
        active++; peak = Math.max(peak, active)
        const data = Buffer.from(await chunk.arrayBuffer())
        assert.equal(hash, crypto.createHash('sha256').update(data).digest('hex'))
        await new Promise(resolve => setTimeout(resolve, 2))
        received[index] = data; report(chunk.size); active--
      }, () => {})
    assert.equal(peak, 2)
    assert.deepEqual(Buffer.concat(received), bytes)
    assert.equal(result.sha256, crypto.createHash('sha256').update(bytes).digest('hex'))
    await assert.rejects(manual.uploadStreamingChunks(file, 4096, 2, new AbortController().signal,
      async () => { throw new Error('send failed') }, () => {}), /send failed/)
  } finally { global.Worker = originalWorker }
})

test('HEIC/HEIF with empty or generic MIME and large videos are accepted', () => {
  assert.equal(manual.isSupportedMedia({ name: 'IMG.HEIC', type: '' }), true)
  assert.equal(manual.isSupportedMedia({ name: 'IMG.heif', type: 'application/octet-stream' }), true)
  assert.equal(manual.isSupportedMedia({ name: 'large.MOV', type: '', size: 8 * 1024 ** 3 }), true)
  assert.equal(manual.isSupportedMedia({ name: 'fake.exe', type: 'image/jpeg' }), false)
})

test('streamed whole-file and chunk hashes match Node crypto', async () => {
  const bytes = crypto.randomBytes(15001)
  const reads = []
  const blob = new Blob([bytes])
  const file = { size: blob.size, slice(start, end) { reads.push(end - start); return blob.slice(start, end) } }
  const manifest = await hashFileChunks(file, 4096)
  assert.equal(manifest.sha256, crypto.createHash('sha256').update(bytes).digest('hex'))
  assert.ok(reads.every(size => size <= 4096))
  for (let i = 0; i < manifest.chunks.length; i++) {
    assert.equal(manifest.chunks[i], crypto.createHash('sha256').update(bytes.subarray(i * 4096, (i + 1) * 4096)).digest('hex'))
  }
})

test('parallel upload preserves bytes despite reversed completion order', async () => {
  const bytes = crypto.randomBytes(19001)
  const file = new Blob([bytes])
  const manifest = await hashFileChunks(file, 4096)
  let active = 0, maxActive = 0, progress = 0
  const received = new Map()
  const result = await manual.uploadOriginalChunks(file, 4096, 2, manifest, async (index, chunk, hash, report) => {
    active++; maxActive = Math.max(maxActive, active)
    const data = Buffer.from(await chunk.arrayBuffer())
    assert.equal(hash, crypto.createHash('sha256').update(data).digest('hex'))
    report(chunk.size / 2)
    report(0) // Retrying a chunk must not double count progress.
    await new Promise(resolve => setTimeout(resolve, index % 2 ? 1 : 5))
    received.set(index, data)
    active--
  }, loaded => { progress = loaded; assert.ok(loaded <= file.size) })
  assert.equal(maxActive, 2)
  assert.equal(progress, file.size)
  assert.deepEqual(Buffer.concat([...received].sort((a,b) => a[0] - b[0]).map(([,data]) => data)), bytes)
  assert.equal(result.sha256, manifest.sha256)
})

test('failed transfer waits for in-flight chunks and does not finalize', async () => {
  let inFlightDone = false
  await assert.rejects(transfer.transferChunks(new Blob(['0123456789']), 2, 2, async index => {
    if (index === 0) throw new Error('network disconnected')
    await new Promise(resolve => setTimeout(resolve, 5))
    inFlightDone = true
  }, () => {}), /network disconnected/)
  assert.equal(inFlightDone, true)
})

test('ten thousand queue entries render a bounded window including the last file', () => {
  for (const top of [0, 20000, 879616]) {
    const range = manual.uploadWindow(10000, top)
    assert.ok(range.end - range.start <= 12)
  }
  assert.equal(manual.uploadWindow(10000, 879616).end, 10000)
})
