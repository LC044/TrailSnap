const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')

function loadBackup(onNotification = async () => {}) {
  const saved = new Map()
  const transferModule = { exports: {} }
  const transferSource = fs.readFileSync(path.resolve(__dirname, '../../src/utils/backupTransfer.ts'), 'utf8')
  const transferCode = ts.transpileModule(transferSource, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  vm.runInThisContext(`(function(module,exports){${transferCode}\n})`)(transferModule, transferModule.exports)
  const chunkModule = { exports: {} }
  const chunkCode = ts.transpileModule(fs.readFileSync(path.resolve(__dirname, '../../src/utils/uploadTransfer.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  vm.runInThisContext(`(function(module,exports){${chunkCode}\n})`)(chunkModule, chunkModule.exports)
  const native = {
    addListener: async () => {}, consumeNotificationAction: async () => ({ action: '' }),
    getNetworkStatus: async () => ({ connected: true, unmetered: true }),
    requestGalleryPermission: async () => ({ granted: true }), requestNotificationPermission: async () => {},
    countAssets: async () => ({ count: 1, bytes: 10 }),
    listAssets: async () => ({ assets: [], imageModified: 0, imageId: 0, videoModified: 0, videoId: 0, companionVideoId: 0, hasMore: false }),
    updateBackupNotification: onNotification, cancelBackupNotification: async () => {},
  }
  const deps = {
    '@capacitor/core': { Capacitor: { convertFileSrc: value => value } },
    '@capacitor/preferences': { Preferences: {
      get: async ({ key }) => ({ value: saved.get(key) || null }),
      set: async ({ key, value }) => { saved.set(key, value) },
      remove: async ({ key }) => { saved.delete(key) },
    } },
    '@/api/album': { albumService: {} }, '@/utils/uploadTransfer': chunkModule.exports,
    '@/config/server': { getServerUrl: () => 'http://test' },
    '@/stores/user': { useUserStore: () => ({ token: 'test', userInfo: { id: 'user' } }) },
    '@/router': { default: { push: async () => {} } },
    '@/native/galleryBackup': { galleryBackupNative: native, supportsGalleryBackup: () => true },
    '@/utils/backupTransfer': transferModule.exports,
  }
  const source = fs.readFileSync(path.resolve(__dirname, '../../src/composables/useGalleryBackup.ts'), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const module = { exports: {} }
  vm.runInThisContext(`(function(require,module,exports){${code}\n})`)(
    name => deps[name] || require(name), module, module.exports,
  )
  return { backup: module.exports.useGalleryBackup(), saved, native, album: deps['@/api/album'].albumService }
}

test('individual failure does not stop following pages or advance the durable cursor past the failure', async () => {
  const { backup, native, album, saved } = loadBackup()
  const assets = [1, 2, 3].map(id => ({ kind: 'image', name: `${id}.jpg`, uri: String(id), backupKey: `key-${id}`, size: 5, modifiedMs: id, takenMs: 0, relativePath: '' }))
  native.countAssets = async () => ({ count: 3, bytes: 15 })
  native.listAssets = async cursor => ({ assets: cursor.imageId ? [assets[2]] : assets.slice(0, 2), imageModified: cursor.imageId ? 3 : 2, imageId: cursor.imageId ? 3 : 2, videoModified: 0, videoId: 0, companionVideoId: 0, hasMore: !cursor.imageId })
  native.calculateAssetMd5 = async ({ uri }) => ({ md5: uri.repeat(32) })
  native.exportAsset = async () => ({ path: 'data:application/octet-stream;base64,YWJjZGU=' })
  native.releaseAsset = async () => {}
  album.checkBackupKeys = async () => ({ existing: new Set(), complete: new Set(), livePhotos: new Set(), hashes: new Set() })
  const uploaded = []
  album.uploadPhoto = async file => {
    if (file.name === '1.jpg') throw Object.assign(new Error('bad file'), { response: { status: 400 } })
    uploaded.push(file.name)
  }
  await backup.runBackup({ manual: true })
  assert.deepEqual(uploaded.sort(), ['2.jpg', '3.jpg'])
  assert.equal(backup.failedItems.value, 1)
  assert.equal(backup.backedUp.value, 2)
  assert.equal(backup.status.value, 'error')
  assert.equal([...saved.values()].some(value => { try { return JSON.parse(value).imageId > 0 } catch { return false } }), false)
})

test('retry resumes committed chunks and sends size and count to final verification', async () => {
  const { backup, native, album } = loadBackup()
  const MB = 1024 * 1024
  const asset = { kind: 'video', name: 'phone.mp4', uri: 'video', backupKey: 'video-key', size: 6 * MB, modifiedMs: 1, takenMs: 0, relativePath: '' }
  native.countAssets = async () => ({ count: 1, bytes: asset.size })
  native.listAssets = async () => ({ assets: [asset], imageModified: 0, imageId: 0, videoModified: 1, videoId: 1, companionVideoId: 0, hasMore: false })
  native.calculateAssetMd5 = async () => ({ md5: '1'.repeat(32) })
  native.exportAsset = async () => ({ path: 'data:application/octet-stream;base64,' + Buffer.alloc(asset.size).toString('base64') })
  native.releaseAsset = async () => {}
  album.checkBackupKeys = async () => ({ existing: new Set(), complete: new Set(), livePhotos: new Set(), hashes: new Set() })
  let initialized = 0, fail = true
  album.initUpload = async () => { initialized++; return 'session' }
  const committed = new Map()
  const sent = []
  album.uploadChunk = async (id, index, chunk) => {
    sent.push(index)
    if (index === 1 && fail) throw Object.assign(new Error('interrupted'), { response: { status: 400 } })
    committed.set(String(index), chunk.size)
  }
  album.getUploadStatus = async () => ({ chunks: Object.fromEntries(committed) })
  album.finishUpload = async (...args) => {
    assert.equal(args[8].expectedSize, asset.size)
    assert.equal(args[8].expectedChunks, 3)
  }
  await backup.runBackup({ manual: true })
  assert.equal(backup.status.value, 'error')
  assert.equal(committed.has('0'), true)
  sent.length = 0; fail = false
  await backup.runBackup({ manual: true })
  assert.equal(backup.status.value, 'idle')
  assert.equal(initialized, 1)
  assert.equal(sent.includes(0), false)
  assert.equal(sent.includes(1), true)
})

test('reset clears an idle pause and returns to a fresh runnable state', async () => {
  const { backup, saved } = loadBackup()
  backup.pauseBackup()
  assert.equal(backup.status.value, 'paused')
  await backup.resetCursor()
  assert.equal(backup.status.value, 'idle')
  assert.equal(backup.pauseRequested.value, false)
  assert.equal(backup.pauseReason.value, null)
  assert.equal(backup.lastRunAt.value, null)
  assert.equal([...saved.values()].some(value => JSON.parse(value).imageId === 0), true)
})

test('resume during a pending paused notification does not strand the backup', async () => {
  let releaseNotification, reportPaused
  const paused = new Promise(resolve => { reportPaused = resolve })
  const { backup } = loadBackup(async payload => {
    if (payload.state === 'paused') {
      reportPaused()
      await new Promise(resolve => { releaseNotification = resolve })
    }
  })
  backup.pauseBackup()
  const run = backup.runBackup({ manual: true })
  await paused
  assert.equal(backup.running.value, true)
  await assert.rejects(backup.resetCursor(), /备份仍在运行/)
  backup.resumeBackup()
  releaseNotification()
  let timeout
  try {
    await Promise.race([run, new Promise((_, reject) => { timeout = setTimeout(() => reject(new Error('Backup remained paused')), 1000) })])
  } finally { clearTimeout(timeout) }
  assert.equal(backup.running.value, false)
  assert.equal(backup.status.value, 'idle')
})

test('a provider repeating the same page stops with a retryable error', async () => {
  const { backup, native } = loadBackup()
  const original = native.listAssets
  let calls = 0
  native.listAssets = async () => { calls++; return { ...await original(), hasMore: true } }
  await backup.runBackup({ manual: true })
  assert.equal(calls, 1)
  assert.equal(backup.running.value, false)
  assert.equal(backup.status.value, 'error')
  assert.match(backup.lastError.value, /图库扫描未能进入下一批/)
})

for (const part of ['complete', 'image', 'video', 'both']) {
  test(`live preflight ${part} sends only missing parts`, async () => {
    const { backup, native, album } = loadBackup()
    const image = { kind: 'image', name: 'phone.jpg', uri: 'image', backupKey: 'new-image-key', size: 5, modifiedMs: 1, takenMs: 0, relativePath: '' }
    const video = { kind: 'video', name: 'phone.mp4', uri: 'video', backupKey: 'new-video-key', size: 5, modifiedMs: 1, takenMs: 0, relativePath: '' }
    image.liveCompanion = video
    native.listAssets = async () => ({ assets: [image], imageModified: 1, imageId: 1, videoModified: 0, videoId: 0, companionVideoId: 1, hasMore: false })
    native.calculateAssetMd5 = async ({ uri }) => ({ md5: uri === 'image' ? '1'.repeat(32) : '2'.repeat(32) })
    const exports = [], forms = []
    native.exportAsset = async ({ uri }) => { exports.push(uri); return { path: 'data:application/octet-stream;base64,YWJjZGU=' } }
    native.releaseAsset = async () => {}
    album.checkBackupKeys = async () => ({ existing: new Set(), complete: new Set(), livePhotos: new Set(), hashes: new Set(['1'.repeat(32)]) })
    album.checkLiveBackupContent = async manifests => {
      assert.equal(manifests[0].video_md5, '2'.repeat(32))
      return { 'new-image-key': { image_exists: part === 'complete' || part === 'video', video_exists: part === 'complete' || part === 'image', complete: part === 'complete' } }
    }
    album.uploadMissingLiveContent = async form => { forms.push(form); return { file_type: 'live_photo' } }
    await backup.runBackup({ manual: true })
    assert.equal(backup.status.value, 'idle')
    assert.deepEqual(exports, part === 'complete' ? [] : part === 'image' ? ['image'] : part === 'video' ? ['video'] : ['image', 'video'])
    assert.equal(forms.length, part === 'complete' ? 0 : 1)
    if (forms.length) {
      assert.equal(forms[0].has('image'), part === 'image' || part === 'both')
      assert.equal(forms[0].has('video'), part === 'video' || part === 'both')
    }
  })
}
