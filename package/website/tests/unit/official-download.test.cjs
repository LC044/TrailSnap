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
