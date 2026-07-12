import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'

import type { APIRequestContext } from '@playwright/test'

import { e2eEnv } from '../../../playwright/e2e-env'
import { waitForTasksToSettle } from '../../../e2e-system/helpers/task-poller'

export type PhotoFixtureBucket = 'smoke' | 'p0'
type FixtureReadySuite = typeof e2eEnv.suite

export interface SkipCapable {
  skip: (condition: boolean, reason: string) => void
}

interface PrepareOptions {
  bucket: PhotoFixtureBucket
  token: string
  testInfo?: SkipCapable
  onUnavailable?: 'skip' | 'throw'
  timeoutMs?: number
}

interface PreparedState {
  ok: boolean
  bucket: PhotoFixtureBucket
  serverDirectory: string
  hostDirectory: string
}

interface CleanupMarker {
  bucket: PhotoFixtureBucket
  serverDirectory: string
  statePath: string
}

interface TaskSchema {
  id: string
}

interface PhotoSummary {
  id: string
}

const MEDIA_EXTENSIONS = new Set([
  '.jpg',
  '.jpeg',
  '.png',
  '.webp',
  '.heic',
  '.heif',
  '.gif',
  '.mp4',
  '.mov',
  '.avi',
])

const repoRoot = path.resolve(process.cwd(), '..', '..')
const hostPathBase = path.join(repoRoot, 'tests', 'docker')
const stateDir = path.join(e2eEnv.runtimeDir, 'photo-fixtures')

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

function isWindowsPath(input: string): boolean {
  return /^[a-zA-Z]:[\\/]/.test(input) || input.includes('\\')
}

function joinPathByStyle(basePath: string, child: string): string {
  if (isWindowsPath(basePath)) {
    return path.win32.join(basePath, child)
  }
  return path.posix.join(basePath, child)
}

function resolveHostPath(rawPath: string): string {
  if (path.isAbsolute(rawPath)) {
    return path.normalize(rawPath)
  }
  return path.resolve(hostPathBase, rawPath)
}

function findAnyMediaFile(rootDir: string): string | null {
  if (!fs.existsSync(rootDir) || !fs.statSync(rootDir).isDirectory()) {
    return null
  }

  const queue = [rootDir]
  while (queue.length > 0) {
    const currentDir = queue.shift()
    if (!currentDir) break

    const entries = fs.readdirSync(currentDir, { withFileTypes: true })
    for (const entry of entries) {
      const fullPath = path.join(currentDir, entry.name)
      if (entry.isDirectory()) {
        queue.push(fullPath)
        continue
      }

      if (MEDIA_EXTENSIONS.has(path.extname(entry.name).toLowerCase())) {
        return fullPath
      }
    }
  }

  return null
}

function getFixtureDirectories(bucket: PhotoFixtureBucket) {
  const hostBaseDirectory = resolveHostPath(e2eEnv.photoHostDirectory)
  const serverBaseDirectory = e2eEnv.photoDirectory

  return {
    hostDirectory: joinPathByStyle(hostBaseDirectory, bucket),
    serverDirectory: joinPathByStyle(serverBaseDirectory, bucket),
  }
}

function getRunId(): string {
  return process.env.TS_E2E_PREP_RUN_ID ?? 'default'
}

function getStatePaths(bucket: PhotoFixtureBucket, serverDirectory: string) {
  fs.mkdirSync(stateDir, { recursive: true })
  const fingerprint = crypto
    .createHash('sha1')
    .update(`${getRunId()}|${e2eEnv.apiBaseUrl}|${bucket}|${serverDirectory}`)
    .digest('hex')
  const statePath = path.join(stateDir, `${fingerprint}.json`)
  return {
    statePath,
    lockPath: `${statePath}.lock`,
    cleanupPath: `${statePath}.cleanup.json`,
  }
}

function readState(statePath: string): PreparedState | null {
  if (!fs.existsSync(statePath)) {
    return null
  }

  return JSON.parse(fs.readFileSync(statePath, 'utf8')) as PreparedState
}

function writeState(statePath: string, state: PreparedState) {
  fs.writeFileSync(statePath, JSON.stringify(state, null, 2), 'utf8')
}

function deleteState(statePath: string) {
  if (fs.existsSync(statePath)) {
    fs.unlinkSync(statePath)
  }
}

function writeCleanupMarker(cleanupPath: string, marker: CleanupMarker) {
  fs.writeFileSync(cleanupPath, JSON.stringify(marker, null, 2), 'utf8')
}

function deleteCleanupMarker(cleanupPath: string) {
  if (fs.existsSync(cleanupPath)) {
    fs.unlinkSync(cleanupPath)
  }
}

function listCleanupMarkers(): CleanupMarker[] {
  if (!fs.existsSync(stateDir)) {
    return []
  }

  return fs.readdirSync(stateDir)
    .filter(name => name.endsWith('.cleanup.json'))
    .map((name) => path.join(stateDir, name))
    .map((filePath) => JSON.parse(fs.readFileSync(filePath, 'utf8')) as CleanupMarker)
}

function handleUnavailable(
  reason: string,
  options: PrepareOptions,
  directories: { hostDirectory: string; serverDirectory: string },
): false {
  if (options.onUnavailable === 'skip' && options.testInfo) {
    options.testInfo.skip(true, reason)
    return false
  }

  throw new Error(reason)
}

async function readResponseText(response: { text: () => Promise<string> }) {
  try {
    return await response.text()
  } catch {
    return ''
  }
}

async function ensureDirectoryConfigured(
  request: APIRequestContext,
  token: string,
  serverDirectory: string,
): Promise<boolean> {
  const headers = {
    Authorization: `Bearer ${token}`,
    Accept: 'application/json',
  }

  const listResponse = await request.get(`${e2eEnv.apiBaseUrl}/settings/directories`, {
    headers,
  })
  if (!listResponse.ok()) {
    throw new Error(`获取目录配置失败: ${listResponse.status()} ${await readResponseText(listResponse)}`)
  }

  const directories = await listResponse.json() as { external?: string[] }
  const externalDirectories = directories.external ?? []
  if (externalDirectories.includes(serverDirectory)) {
    return false
  }

  const addResponse = await request.post(`${e2eEnv.apiBaseUrl}/settings/directories`, {
    headers,
    data: {
      path: serverDirectory,
    },
  })
  if (!addResponse.ok()) {
    throw new Error(`添加目录失败: ${addResponse.status()} ${await readResponseText(addResponse)}`)
  }

  return true
}

async function triggerScanAndWait(
  request: APIRequestContext,
  token: string,
  serverDirectory: string,
  waitProgressMs: number,
): Promise<void> {
  const startedAt = new Date().toISOString()
  const headers = {
    Authorization: `Bearer ${token}`,
    Accept: 'application/json',
  }

  const createResponse = await request.post(`${e2eEnv.apiBaseUrl}/tasks/`, {
    headers,
    data: {
      type: 'SCAN_FOLDER',
      payload: {
        scan_roots: [serverDirectory],
      },
    },
  })
  if (!createResponse.ok()) {
    throw new Error(`创建扫描任务失败: ${createResponse.status()} ${await readResponseText(createResponse)}`)
  }

  const task = await createResponse.json() as TaskSchema
  await waitForTasksToSettle(request, token, {
    progressQuietWindowMs: waitProgressMs,
    updatedSince: startedAt,
    taskId: task.id,
    tasksUrl: `${e2eEnv.apiBaseUrl}/tasks/`,
  })
}

async function waitForImportedPhotos(
  request: APIRequestContext,
  token: string,
  timeoutMs: number,
): Promise<void> {
  const startedAt = Date.now()
  const headers = {
    Authorization: `Bearer ${token}`,
    Accept: 'application/json',
  }

  while (Date.now() - startedAt < timeoutMs) {
    const response = await request.get(`${e2eEnv.apiBaseUrl}/photos`, {
      headers,
      params: {
        skip: 0,
        limit: 1,
      },
    })

    if (response.ok()) {
      const body = await response.json() as PhotoSummary[] | { data?: PhotoSummary[] }
      const photos = Array.isArray(body) ? body : (body.data ?? [])
      if (photos.length > 0) {
        return
      }
    }

    await sleep(2_000)
  }

  throw new Error('扫描任务已完成，但照片列表在限定时间内仍为空')
}

async function withPreparationLock<T>(
  bucket: PhotoFixtureBucket,
  serverDirectory: string,
  work: () => Promise<T>,
): Promise<T> {
  const { statePath, lockPath } = getStatePaths(bucket, serverDirectory)

  while (true) {
    const cached = readState(statePath)
    if (cached?.ok) {
      return cached as T
    }

    try {
      const fd = fs.openSync(lockPath, 'wx')
      fs.closeSync(fd)
      break
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'EEXIST') {
        throw error
      }
      await sleep(500)
    }
  }

  try {
    return await work()
  } finally {
    if (fs.existsSync(lockPath)) {
      fs.unlinkSync(lockPath)
    }
  }
}

export function bucketForSuite(suite: typeof e2eEnv.suite): PhotoFixtureBucket | null {
  if (suite === 'smoke') return 'smoke'
  if (suite === 'p0' || suite === 'p1') return 'p0'
  return null
}

export function bucketsForSuite(suite: FixtureReadySuite): PhotoFixtureBucket[] {
  if (suite === 'smoke') return ['smoke']
  if (suite === 'p0' || suite === 'p1') return ['p0']
  if (suite === 'scan' || suite === 'dev' || suite === 'all' || suite === 'full' || suite === 'light') return ['smoke', 'p0']
  return []
}

export async function preparePhotoFixtures(
  request: APIRequestContext,
  options: PrepareOptions,
): Promise<boolean> {
  if (!e2eEnv.enableFixtureScan) {
    return true
  }

  const mode = options.onUnavailable ?? 'skip'
  const directories = getFixtureDirectories(options.bucket)
  const { statePath, cleanupPath } = getStatePaths(options.bucket, directories.serverDirectory)
  const cached = readState(statePath)

  if (cached?.ok) {
    return true
  }
  if (cached && !cached.ok) {
    deleteState(statePath)
  }

  const mediaFile = findAnyMediaFile(directories.hostDirectory)
  if (!mediaFile) {
    return handleUnavailable(
      `测试图片目录不可用: ${directories.hostDirectory}。请在该目录下放入 ${options.bucket} 套件需要的真实图片后再运行测试。`,
      { ...options, onUnavailable: mode },
      directories,
    )
  }

  try {
    await withPreparationLock(options.bucket, directories.serverDirectory, async () => {
      const latestState = readState(statePath)
      if (latestState?.ok) {
        return latestState
      }
      if (latestState && !latestState.ok) {
        deleteState(statePath)
      }

      // 记录加目录前的时间戳：POST /settings/directories 会在添加目录时自动触发一次
      // SCAN_FOLDER（扫描所有 external 目录）。我们只能等这次扫描，不能再额外建第二个
      // 扫描任务——两个 scope 重叠的 SCAN_FOLDER 会被 IO consumer 并发执行，而扫描去重
      // 仅靠查库内已有 file_path，并发时双方都查到「不存在」→ 同一文件各插一条 Photo →
      // 相册里同一张照片出现两份。
      const scanStartedAt = new Date().toISOString()
      const addedByTest = await ensureDirectoryConfigured(request, options.token, directories.serverDirectory)
      if (addedByTest) {
        writeCleanupMarker(cleanupPath, {
          bucket: options.bucket,
          serverDirectory: directories.serverDirectory,
          statePath,
        })
      }

      const waitMs = options.timeoutMs ?? 15_000
      if (addedByTest) {
        // 目录是本次新增的：POST 已经排了一个 SCAN_FOLDER，只等任务跑完，不再重复触发。
        await waitForTasksToSettle(request, options.token, {
          progressQuietWindowMs: waitMs,
          updatedSince: scanStartedAt,
          tasksUrl: `${e2eEnv.apiBaseUrl}/tasks/`,
        })
      } else {
        // 目录此前已配置（POST 不会触发扫描）：需要主动触发一次，确保照片入库。
        await triggerScanAndWait(request, options.token, directories.serverDirectory, waitMs)
      }
      await waitForImportedPhotos(
        request,
        options.token,
        Math.min(waitMs, 2 * 60 * 1000),
      )

      const successState = {
        ok: true,
        bucket: options.bucket,
        hostDirectory: directories.hostDirectory,
        serverDirectory: directories.serverDirectory,
      } satisfies PreparedState

      writeState(statePath, successState)
      return successState
    })

    return true
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error)
    return handleUnavailable(reason, { ...options, onUnavailable: mode }, directories)
  }
}

export async function preparePhotoFixturesForSuite(
  request: APIRequestContext,
  token: string,
  suite: FixtureReadySuite,
  options: Omit<PrepareOptions, 'bucket' | 'token'> = {},
): Promise<boolean> {
  for (const bucket of bucketsForSuite(suite)) {
    const prepared = await preparePhotoFixtures(request, {
      ...options,
      bucket,
      token,
    })
    if (!prepared) {
      return false
    }
  }

  return true
}

export async function cleanupPreparedPhotoFixtures(
  request: APIRequestContext,
  token: string,
): Promise<void> {
  const headers = {
    Authorization: `Bearer ${token}`,
    Accept: 'application/json',
  }

  for (const marker of listCleanupMarkers()) {
    const { cleanupPath } = getStatePaths(marker.bucket, marker.serverDirectory)
    try {
      const response = await request.delete(`${e2eEnv.apiBaseUrl}/settings/directories`, {
        headers,
        data: {
          path: marker.serverDirectory,
        },
      })
      if (!response.ok()) {
        throw new Error(`删除测试目录失败: ${response.status()} ${await readResponseText(response)}`)
      }
    } finally {
      deleteState(marker.statePath)
      deleteCleanupMarker(cleanupPath)
    }
  }
}
