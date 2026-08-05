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

/**
 * 拉取 grouped-status，返回当前后端跟踪的任务分类列表（9 个照片处理分类）。
 * 用于在轮询前后对这批分类统一执行 pause/resume。
 */
async function fetchGroupedCategories(
  request: APIRequestContext,
  token: string,
  tasksUrl: string,
): Promise<string[]> {
  const groupedUrl = tasksUrl.endsWith('/') ? `${tasksUrl}grouped-status` : `${tasksUrl}/grouped-status`
  try {
    const response = await request.get(groupedUrl, {
      headers: { Authorization: `Bearer ${token}` },
      timeout: 10_000,
    })
    if (!response.ok()) return []
    const raw = (await response.json()) as GroupedTask[] | { data?: GroupedTask[] }
    const tasks = Array.isArray(raw) ? raw : (raw.data ?? [])
    return tasks.map(t => t.category).filter(Boolean)
  } catch {
    return []
  }
}

/**
 * 对 grouped-status 跟踪的全部处理分类逐个调用 pause/resume。
 *
 * 必须串行：后端 TaskManager.pause_category / resume_category 是「读 DB → 改内存 set →
 * 写 DB」的非原子 read-modify-write，并发调用会互相覆盖（最后一个写赢，丢分类）。
 *
 * best-effort：任一分类请求失败只记录日志、不抛错，不影响轮询本身的成功/失败。
 */
async function setAllCategoryStates(
  request: APIRequestContext,
  token: string,
  tasksUrl: string,
  action: 'pause' | 'resume',
): Promise<void> {
  const categoriesBase = tasksUrl.endsWith('/') ? `${tasksUrl}categories` : `${tasksUrl}/categories`
  const categories = await fetchGroupedCategories(request, token, tasksUrl)
  if (categories.length === 0) {
    process.stdout.write(`[Task Progress] 未获取到任务分类，跳过 ${action}\n`)
    return
  }

  const failed: string[] = []
  for (const category of categories) {
    try {
      const response = await request.post(`${categoriesBase}/${category}/${action}`, {
        headers: { Authorization: `Bearer ${token}` },
        timeout: 10_000,
      })
      if (!response.ok()) {
        failed.push(`${category}:${response.status()}`)
      }
    } catch {
      failed.push(`${category}:ERR`)
    }
  }

  const verb = action === 'pause' ? '暂停' : '恢复'
  if (failed.length > 0) {
    process.stdout.write(`[Task Progress] ${verb}部分失败: ${failed.join(', ')}\n`)
  } else {
    process.stdout.write(`[Task Progress] 已${verb}全部 ${categories.length} 个处理分类\n`)
  }
}

export async function waitForTasksToSettle(
  request: APIRequestContext,
  token: string,
  options: WaitOptions = {},
) {
  const intervalMs = options.intervalMs ?? 5_000
  // CI runner（4 vCPU）性能差，后端任务（face/OCR/embedding 等）处理慢，轮询状态可能
  // 在任务仍在排队/处理时出现短暂空窗。本地 5 轮即可，CI 放宽到 12 轮（5s×12=60s 无变化）
  // 才认为稳定，避免任务还没跑完就提前退出导致后续用例拿不到数据。
  const stableRounds = options.stableRounds ?? (process.env.CI ? 18 : 5)
  const tasksUrl = options.tasksUrl ?? '/tasks/'
  const groupedUrl = tasksUrl.endsWith('/') ? `${tasksUrl}grouped-status` : `${tasksUrl}/grouped-status`
  
  let stableCount = 0
  let lastSignature = ''
  let errorCount = 0
  let lastLine = ''

  const renderProgress = (line: string) => {
    // 用回车符覆盖当前行，实现单行进度条，避免刷屏
    const pad = line.length < lastLine.length ? ' '.repeat(lastLine.length - line.length) : ''
    process.stdout.write(`\r${line}${pad}`)
    lastLine = line
  }

  // 轮询开始前先 resume 全部分类，清除上一轮（dev 模式跨轮）残留的 paused_categories，
  // 否则残留的暂停状态会让本轮 setup 的处理任务被跳过、拿不到数据。
  await setAllCategoryStates(request, token, tasksUrl, 'resume')

  while (true) {
    try {
      const response = await request.get(groupedUrl, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })

      if (!response.ok()) {
        errorCount++
        if (errorCount > 5) {
          renderProgress('')
          throw new Error(`查询任务状态连续失败 5 次: ${response.status()} ${response.statusText()}`)
        }
        renderProgress(`[Task Progress] 获取状态异常 (${response.status()})，重试中...`)
        await new Promise(resolve => setTimeout(resolve, intervalMs))
        continue
      }
      
      errorCount = 0 // 重置错误计数

      // /tasks/grouped-status 已包裹 BaseResponse，兼容旧版直接返回数组的情况
      const groupedRaw = (await response.json()) as GroupedTask[] | { data?: GroupedTask[] }
      const groupedTasks = Array.isArray(groupedRaw) ? groupedRaw : (groupedRaw.data ?? [])
    
    // 过滤出有剩余或失败任务的分类
    const activeGroups = groupedTasks.filter(t => t.pending > 0 || t.failed > 0)
    
    const progressSignature = groupedTasks
      .map(t => `${t.category}:${t.pending}:${t.failed}`)
      .join('|')

    if (progressSignature !== lastSignature) {
      if (activeGroups.length > 0) {
        const totalPending = activeGroups.reduce((s, t) => s + t.pending, 0)
        const totalCompleted = activeGroups.reduce((s, t) => s + t.completed, 0)
        const totalFailed = activeGroups.reduce((s, t) => s + t.failed, 0)
        const total = totalPending + totalCompleted + totalFailed
        const ratio = total > 0 ? totalCompleted / total : 0
        const barWidth = 20
        const filled = Math.round(ratio * barWidth)
        const bar = '█'.repeat(filled) + '░'.repeat(barWidth - filled)
        const percent = Math.round(ratio * 100)
        const detail = activeGroups
          .map(t => `[${t.category}] 剩余${t.pending} 失败${t.failed}`)
          .join('  ')
        renderProgress(
          `[Task Progress] ${bar} ${percent}% | 剩余 ${totalPending} 完成 ${totalCompleted} 失败 ${totalFailed}  ${detail}`,
        )
      } else if (lastSignature !== '') {
        renderProgress(`[Task Progress] ████████████████████ 100% | 所有任务已完成`)
        process.stdout.write('\n')
        lastLine = ''
      }

      lastSignature = progressSignature
      stableCount = 1
    } else {
      stableCount += 1
    }

    // 连续 stableRounds 轮（本地 5 / CI 12）没有变化就认为已经结束
    if (stableCount >= stableRounds) {
      // 结束前换行，避免后续日志覆盖进度条
      if (lastLine !== '') {
        process.stdout.write('\n')
        lastLine = ''
      }
      // 稳定后暂停全部分类，冻结仍处于 pending/processing 的任务，避免它们在后续测试中
      // 被调度执行、改动数据导致用例异常。best-effort：失败只打日志，不影响轮询结果。
      await setAllCategoryStates(request, token, tasksUrl, 'pause')
      return
    }

    await new Promise(resolve => setTimeout(resolve, intervalMs))
    } catch (e: any) {
      errorCount++
      if (errorCount > 5) {
        if (lastLine !== '') {
          process.stdout.write('\n')
          lastLine = ''
        }
        throw new Error(`查询任务状态发生网络错误并重试失败 5 次: ${e.message}`)
      }
      renderProgress(`[Task Progress] 网络请求异常 (${e.message})，可能服务正在重启，重试中...`)
      await new Promise(resolve => setTimeout(resolve, intervalMs * 2)) // 发生网络错误时，等待更长时间再重试
    }
  }
}

