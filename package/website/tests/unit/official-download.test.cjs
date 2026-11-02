const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const { computed } = require('vue')

const source = fs.readFileSync(path.resolve(__dirname, '../../../official-site/.vitepress/theme/components/DownloadPage.vue'), 'utf8')
const matcherSource = source.slice(source.indexOf('function matchesPlatform('), source.indexOf('async function fetchAssets('))
const matcherCode = ts.transpileModule(matcherSource, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText

function harness(items = []) {
  const context = { assets: { value: items }, releaseUrl: 'release-fallback', computed }
  vm.createContext(context)
  vm.runInContext(matcherCode, context)
  return context
}

test('portable download accepts old and unified full ZIPs only', () => {
  const { matchesPlatform } = harness()
  for (const name of [
    'TrailSnap-0.18.0-windows-x86_64-portable.zip',
    'TrailSnap-0.19.0-desktop-windows-x64-portable.zip',
  ]) assert.equal(matchesPlatform(name, 'windows', 'portable'), true)
  for (const name of [
    'TrailSnap-0.19.0-desktop-windows-x64-portable-update.zip',
    'TrailSnap-0.19.0-desktop-windows-x64-portable-update.zip.sig',
    'TrailSnap-0.19.0-ai-core-windows-x64.tar.gz',
    'TrailSnap-0.19.0-desktop-windows-arm64-portable.zip',
    'pr-345-TrailSnap-0.19.0-desktop-windows-x64-portable.zip',
  ]) assert.equal(matchesPlatform(name, 'windows', 'portable'), false)
})

test('installer matching accepts both release naming conventions', () => {
  const { matchesPlatform } = harness()
  for (const [platform, oldName, newName] of [
    ['windows', 'TrailSnap_0.18.0_x64-setup.exe', 'TrailSnap-0.19.0-desktop-windows-x64-setup.exe'],
    ['macos', 'TrailSnap_0.18.0_aarch64.dmg', 'TrailSnap-0.19.0-desktop-macos-arm64.dmg'],
    ['linux', 'TrailSnap_0.18.0_amd64.AppImage', 'TrailSnap-0.19.0-desktop-linux-x64.AppImage'],
    ['linux', 'TrailSnap_0.18.0_amd64.deb', 'TrailSnap-0.19.0-desktop-linux-x64.deb'],
  ]) {
    assert.equal(matchesPlatform(oldName, platform), true)
    assert.equal(matchesPlatform(newName, platform), true)
  }
  assert.equal(matchesPlatform('TrailSnap-0.19.0-cli-windows-x64.exe', 'windows'), false)
})

test('ZIP button resolves the full asset or falls back to the release page', () => {
  const name = 'TrailSnap-0.19.0-desktop-windows-x64-portable.zip'
  const { assetUrl } = harness([
    { name: name.replace('-portable.zip', '-portable-update.zip'), browser_download_url: 'update-url' },
    { name, browser_download_url: 'full-url' },
  ])
  assert.equal(assetUrl('windows', 'portable'), 'full-url')
  assert.equal(harness().assetUrl('windows', 'portable'), 'release-fallback')
  assert.match(source, /copy\.downloadZip/)
})

test('npm CLI downloader uses unified names and falls back for old releases', () => {
  const installer = fs.readFileSync(path.resolve(__dirname, '../../../trailsnap-cli/scripts/install.js'), 'utf8')
  assert.match(installer, /TrailSnap-\$\{version\}-cli-\$\{platform\}-\$\{arch\}/)
  assert.match(installer, /response\.statusCode === 404 && fallbackUrl/)
  assert.match(installer, /downloadBinary\(response\.headers\.location, dest, fallbackUrl\)/)
})


test('Linux format choices resolve the selected asset regardless of release order', () => {
  const { assetUrl, matchesPlatform } = harness([
    { name: 'TrailSnap-0.19.0-desktop-linux-x64.deb', browser_download_url: 'deb-url' },
    { name: 'TrailSnap-0.19.0-desktop-linux-x64.AppImage', browser_download_url: 'appimage-url' },
  ])
  assert.equal(assetUrl('linux', 'appimage'), 'appimage-url')
  assert.equal(assetUrl('linux', 'deb'), 'deb-url')
  assert.equal(matchesPlatform('TrailSnap-0.19.0-desktop-linux-x64.deb', 'windows', 'deb'), false)
  assert.equal(harness().assetUrl('linux', 'deb'), 'release-fallback')
})

test('fnOS download selects the x86 package and falls back without assets', () => {
  const name = 'TrailSnap-0.20.0-fnos-x86.fpk'
  const { fnosAssetUrl } = harness([
    { name: `${name}.sha256`, browser_download_url: 'checksum' },
    { name: name.replace('x86', 'arm64'), browser_download_url: 'unsupported' },
    { name: `pr-123-${name}`, browser_download_url: 'preview' },
    { name, browser_download_url: 'fnos-package' },
  ])
  assert.equal(fnosAssetUrl(), 'fnos-package')
  assert.equal(harness().fnosAssetUrl(), 'release-fallback')
})

const fetchCode = ts.transpileModule(
  source.slice(source.indexOf('async function fetchAssets('), source.indexOf('async function onDownload(')),
  { compilerOptions: { target: ts.ScriptTarget.ES2022 } },
).outputText

function fetchHarness(fetch) {
  const context = harness()
  context.fetch = fetch
  context.releaseName = { value: '' }
  vm.runInContext(fetchCode, context)
  return context
}

test('static version manifest generates installer, portable, fnOS and accelerated links', async () => {
  const context = fetchHarness(async (url, options) => {
    assert.equal(url, '/version.json')
    assert.equal(options.cache, 'no-cache')
    return { ok: true, json: async () => [{ version: '0.19.0' }, { version: '0.20.1' }] }
  })
  assert.equal(await context.fetchAssets(), true)
  assert.equal(context.releaseName.value, 'v0.20.1')
  const base = 'https://github.com/LC044/TrailSnap/releases/download/v0.20.1/TrailSnap-0.20.1-'
  for (const [platform, kind, suffix] of [
    ['windows', 'installer', 'desktop-windows-x64-setup.exe'],
    ['windows', 'portable', 'desktop-windows-x64-portable.zip'],
    ['macos', 'installer', 'desktop-macos-arm64.dmg'],
    ['linux', 'appimage', 'desktop-linux-x64.AppImage'],
    ['linux', 'deb', 'desktop-linux-x64.deb'],
  ]) {
    assert.equal(context.assetUrl(platform, kind), base + suffix)
    assert.equal(context.accelLink(platform, kind), 'https://gh-proxy.com/' + base + suffix)
  }
  assert.equal(context.fnosAssetUrl(), base + 'fnos-x86.fpk')
  assert.doesNotMatch(source, /api\.github\.com/)
})

test('unavailable or invalid version manifests preserve release-page fallback', async () => {
  const responses = [
    { ok: false },
    { ok: true, json: async () => { throw new Error('invalid JSON') } },
    ...[null, {}, [], [null], [{ version: 123 }], [{ version: '0.20.1/invalid' }],
      [{ version: '0.20.1' }, { version: '' }]].map(payload => ({ ok: true, json: async () => payload })),
  ]
  for (const response of responses) {
    const context = fetchHarness(async () => response)
    assert.equal(await context.fetchAssets(), false)
    assert.equal(context.assetUrl('windows'), 'release-fallback')
    assert.equal(context.fnosAssetUrl(), 'release-fallback')
    assert.equal(context.accelLink('windows'), '')
  }
  assert.equal(await fetchHarness(async () => { throw new Error('offline') }).fetchAssets(), false)
})
