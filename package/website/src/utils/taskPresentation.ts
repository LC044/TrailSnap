export interface TaskGroup {
  task_name: string
  category: string
  pending: number
  completed: number
  failed: number
  status: string
  priority: number
  description: string
  waiting_reason?: string
}

export type TaskFilter = 'all' | 'pending' | 'failed' | 'paused'
export type TaskState = 'paused' | 'waiting' | 'pending' | 'failed' | 'idle'

export const taskFilters: Array<{ value: TaskFilter; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'pending', label: '待处理' },
  { value: 'failed', label: '失败' },
  { value: 'paused', label: '已暂停' },
]

export function getTaskState(task: TaskGroup): TaskState {
  if (task.status === 'paused') return 'paused'
  if (task.pending > 0) return task.waiting_reason ? 'waiting' : 'pending'
  return task.failed > 0 ? 'failed' : 'idle'
}

export const taskStateLabels: Record<TaskState, string> = {
  paused: '已暂停',
  waiting: '等待条件',
  pending: '待处理',
  failed: '需处理失败',
  idle: '无待处理',
}

export function summarizeTaskGroups(tasks: TaskGroup[]) {
  return tasks.reduce((summary, task) => ({
    pending: summary.pending + task.pending,
    failed: summary.failed + task.failed,
    paused: summary.paused + (task.status === 'paused' ? 1 : 0),
  }), { pending: 0, failed: 0, paused: 0 })
}

function attentionRank(task: TaskGroup) {
  if (task.failed > 0) return 0
  if (task.pending > 0 && task.status !== 'paused') return 1
  return task.status === 'paused' ? 2 : 3
}

export function filterTaskGroups(tasks: TaskGroup[], filter: TaskFilter): TaskGroup[] {
  return tasks.filter(task => {
    if (filter === 'pending') return task.pending > 0
    if (filter === 'failed') return task.failed > 0
    if (filter === 'paused') return task.status === 'paused'
    return true
  }).sort((a, b) => attentionRank(a) - attentionRank(b) || b.priority - a.priority)
}
