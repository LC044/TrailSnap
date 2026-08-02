import { copyFileSync, existsSync, mkdirSync, readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const androidRoot = join(packageRoot, 'android')
const packageJson = JSON.parse(readFileSync(join(packageRoot, 'package.json'), 'utf8'))

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: packageRoot,
    stdio: 'inherit',
    env: process.env,
    ...options,
  })
  if (result.error) throw result.error
  if (result.status !== 0) process.exit(result.status || 1)
}

const sdkCandidates = [
  process.env.ANDROID_HOME,
  process.env.ANDROID_SDK_ROOT,
  process.env.LOCALAPPDATA && join(process.env.LOCALAPPDATA, 'Android', 'Sdk'),
  join(homedir(), 'Library', 'Android', 'sdk'),
  join(homedir(), 'Android', 'Sdk'),
].filter(Boolean)

const sdkRoot = sdkCandidates.find((candidate) => existsSync(candidate))
if (!sdkRoot) {
  console.error('Android SDK not found. Install Android Studio or set ANDROID_HOME.')
  process.exit(1)
}

process.env.ANDROID_HOME = sdkRoot
process.env.ANDROID_SDK_ROOT = sdkRoot

run(process.execPath, [join(packageRoot, 'node_modules', 'vite', 'bin', 'vite.js'), 'build'])
run(process.execPath, [join(packageRoot, 'node_modules', '@capacitor', 'cli', 'bin', 'capacitor'), 'sync'])

const gradleWrapper = join(androidRoot, process.platform === 'win32' ? 'gradlew.bat' : 'gradlew')
run(gradleWrapper, ['assembleDebug'], {
  cwd: androidRoot,
  shell: process.platform === 'win32',
})

const sourceApk = join(androidRoot, 'app', 'build', 'outputs', 'apk', 'debug', 'app-debug.apk')
const artifactDir = join(packageRoot, 'artifacts')
const artifactApk = join(artifactDir, `TrailSnap-${packageJson.version}-debug.apk`)
mkdirSync(artifactDir, { recursive: true })
copyFileSync(sourceApk, artifactApk)
console.log(`APK: ${artifactApk}`)
