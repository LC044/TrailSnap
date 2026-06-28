import type { APIRequestContext } from '@playwright/test'

interface GroupedTask {
  task_name: string
  category: string
  pending: number
  completed: number
  failed: number
  status: string
  priority: number
  description: string
}

interface WaitOptions {
  progressQuietWindowMs?: number
  intervalMs?: number
  stableRounds?: number
  updatedSince?: string
  taskId?: string
  taskTypes?: string[]
  tasksUrl?: string
}

export async function waitForTasksToSettle(
  request: APIRequestContext,
  token: string,
  options: WaitOptions = {},
) {
  const intervalMs = options.intervalMs ?? 5_000
  const stableRounds = options.stableRounds ?? 3
  const tasksUrl = options.tasksUrl ?? '/tasks/'
  const groupedUrl = tasksUrl.endsWith('/') ? `${tasksUrl}grouped-status` : `${tasksUrl}/grouped-status`
  
  let stableCount = 0
  let lastSignature = ''

  while (true) {
    const response = await request.get(groupedUrl, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    })

    if (!response.ok()) {
      throw new Error(`查询任务状态失败: ${response.status()} ${response.statusText()}`)
    }

    const groupedTasks = (await response.json()) as GroupedTask[]
    
    // 过滤出有剩余或失败任务的分类
    const activeGroups = groupedTasks.filter(t => t.pending > 0 || t.failed > 0)
    
    const progressSignature = groupedTasks
      .map(t => `${t.category}:${t.pending}:${t.failed}`)
      .join('|')

    if (progressSignature !== lastSignature) {
      if (activeGroups.length > 0) {
        console.log(`[Task Progress]`)
        activeGroups.forEach(t => {
          console.log(`  - [${t.category}] 剩余: ${t.pending}, 失败: ${t.failed}`)
        })
      } else if (lastSignature !== '') {
        console.log(`[Task Progress] 所有任务已完成`)
      }
      
      lastSignature = progressSignature
      stableCount = 1
    } else {
      stableCount += 1
    }

    // 连续三次没有变化就认为已经结束了
    if (stableCount >= stableRounds) {
      return
    }

    await new Promise(resolve => setTimeout(resolve, intervalMs))
  }
}

