import type { APIRequestContext } from '@playwright/test'

interface TaskRecord {
  id: string
  type: string
  status: string
  error?: string | null
}

interface WaitOptions {
  timeoutMs?: number
  intervalMs?: number
  stableRounds?: number
}

export async function waitForTasksToSettle(
  request: APIRequestContext,
  token: string,
  options: WaitOptions = {},
) {
  const timeoutMs = options.timeoutMs ?? 8 * 60 * 1000
  const intervalMs = options.intervalMs ?? 3_000
  const stableRounds = options.stableRounds ?? 3
  const startedAt = Date.now()
  let stableCount = 0

  while (Date.now() - startedAt < timeoutMs) {
    const response = await request.get('/tasks/', {
      params: { limit: 200 },
      headers: {
        Authorization: `Bearer ${token}`,
      },
    })

    if (!response.ok()) {
      throw new Error(`查询任务列表失败: ${response.status()} ${response.statusText()}`)
    }

    const tasks = (await response.json()) as TaskRecord[]
    const failedTasks = tasks.filter(task => task.status === 'FAILED')
    const activeTasks = tasks.filter(task => task.status === 'PENDING' || task.status === 'PROCESSING')

    if (failedTasks.length > 0) {
      const summary = failedTasks
        .slice(0, 5)
        .map(task => `${task.type}:${task.error || 'unknown error'}`)
        .join('; ')
      throw new Error(`存在失败任务: ${summary}`)
    }

    if (activeTasks.length === 0) {
      stableCount += 1
      if (stableCount >= stableRounds) {
        return
      }
    } else {
      stableCount = 0
    }

    await new Promise(resolve => setTimeout(resolve, intervalMs))
  }

  throw new Error('等待任务完成超时')
}
