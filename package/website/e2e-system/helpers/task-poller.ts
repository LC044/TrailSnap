import type { APIRequestContext } from '@playwright/test'

interface GroupedTask {
  category: string
  pending: number
  failed: number
}

interface ScanTask {
  id: string
  status: string
  error?: string
}

interface WaitOptions {
  timeoutMs?: number
  intervalMs?: number
  stableRounds?: number
  taskId?: string
  tasksUrl?: string
}

function unwrap<T>(body: T | { code: number; data: T }): T {
  if (body && typeof body === 'object' && 'code' in body) {
    if (body.code !== 0) throw new Error(`任务 API 返回错误: ${JSON.stringify(body)}`)
    return body.data
  }
  return body as T
}

function deferredTypes(): Set<string> {
  return new Set((process.env.TS_E2E_PREP_DEFERRED_TYPES ?? '').split(',').map(s => s.trim()).filter(Boolean))
}

/** Configure prerequisites before adding directories, so optional jobs never start. */
export async function configurePreparationTasks(request: APIRequestContext, token: string, tasksUrl: string) {
  const base = tasksUrl.replace(/\/$/, '')
  const headers = { Authorization: `Bearer ${token}` }
  const response = await request.get(`${base}/grouped-status`, { headers, timeout: 10_000 })
  if (!response.ok()) throw new Error(`读取处理分类失败: ${response.status()}`)
  const groups = unwrap<GroupedTask[]>(await response.json())
  if (!groups.length) throw new Error('处理分类为空，不能确认准备状态')
  const deferred = deferredTypes()
  // Sequential: the server updates a shared read-modify-write set.
  // Pause optional jobs first so resumed prerequisites cannot dispatch them.
  for (const group of [...groups].sort((a, b) => Number(deferred.has(b.category)) - Number(deferred.has(a.category)))) {
    const action = deferred.has(group.category) ? 'pause' : 'resume'
    const result = await request.post(`${base}/categories/${group.category}/${action}`, { headers, timeout: 10_000 })
    if (!result.ok()) throw new Error(`${action} ${group.category} 失败: ${result.status()}`)
  }
}

export async function waitForTasksToSettle(request: APIRequestContext, token: string, options: WaitOptions = {}) {
  const base = (options.tasksUrl ?? '/tasks/').replace(/\/$/, '')
  const headers = { Authorization: `Bearer ${token}` }
  const deadline = Date.now() + (options.timeoutMs ?? 5 * 60_000)
  const intervalMs = options.intervalMs ?? 2_000
  const deferred = deferredTypes()
  let readyRounds = 0
  let lastProgress = ''
  let lastError = ''
  const startedAt = Date.now()

  while (Date.now() < deadline) {
    // SCAN_FOLDER is absent from grouped-status. It must finish first: it may
    // still be generating child jobs while the processing queue appears empty.
    let scans: ScanTask[]
    let groups: GroupedTask[]
    try {
      const scanResponse = await request.get(options.taskId ? `${base}/${options.taskId}` : `${base}/`, {
        headers, timeout: 10_000,
        params: options.taskId ? undefined : { type: 'SCAN_FOLDER', limit: 100 },
      })
      if (!scanResponse.ok()) throw new Error(`扫描状态 HTTP ${scanResponse.status()}`)
      scans = options.taskId ? [unwrap<ScanTask>(await scanResponse.json())] : unwrap<ScanTask[]>(await scanResponse.json())
      const response = await request.get(`${base}/grouped-status`, { headers, timeout: 10_000 })
      if (!response.ok()) throw new Error(`处理状态 HTTP ${response.status()}`)
      groups = unwrap<GroupedTask[]>(await response.json())
      if (!groups.length) throw new Error('处理分类为空')
      lastError = ''
    } catch (error) {
      readyRounds = 0
      lastError = String(error)
      await new Promise(resolve => setTimeout(resolve, intervalMs))
      continue
    }

    const failedScan = scans.find(task => task.status === 'failed' || task.status === 'cancelled')
    if (failedScan) throw new Error(`扫描未成功: ${JSON.stringify(failedScan)}`)
    const required = groups.filter(group => !deferred.has(group.category))
    const failures = required.filter(group => group.failed > 0)
    if (failures.length) throw new Error(`必需照片处理失败: ${JSON.stringify(failures)}`)
    const pending = required.filter(group => group.pending > 0)
    // The backend deletes completed task rows. Callers enter only after a
    // successful synchronous enqueue, so an empty scan list means drained.
    const scanReady = scans.length < 100 && scans.every(task => task.status === 'completed')
    const progress = `scan=${scanReady ? 'completed' : 'pending'} ${pending.map(group => `${group.category}=${group.pending}`).join(' ')}`
    if (progress !== lastProgress) {
      console.log(`[Task Progress] ${progress}`)
      lastProgress = progress
    }
    // Consecutive EMPTY rounds, never consecutive unchanged pending counts.
    readyRounds = scanReady && pending.length === 0 ? readyRounds + 1 : 0
    if (readyRounds >= (options.stableRounds ?? 3)) {
      for (const group of groups) {
        const response = await request.post(`${base}/categories/${group.category}/pause`, { headers, timeout: 10_000 })
        if (!response.ok()) throw new Error(`暂停 ${group.category} 失败: ${response.status()}`)
      }
      console.log(`[Timing] fixture processing: ${((Date.now() - startedAt) / 1000).toFixed(1)}s`)
      return
    }
    await new Promise(resolve => setTimeout(resolve, intervalMs))
  }
  throw new Error(`照片准备超时: ${lastProgress}; ${lastError}`)
}
