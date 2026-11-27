import type { ToolPlan } from '@/api/toolboxWorkflows'

export const deletePlanMessage = '删除后将无法查看这份计划或通过它撤销操作。照片和已经执行的操作不会受影响。'

export const labels: Record<string, string> = {
  preview: '待确认', queued: '排队中', running: '处理中', completed: '完成',
  partial: '部分失败', failed: '失败', stopped: '已停止',
  scan_queued: '等待扫描', scanning: '扫描中', scan_stopped: '扫描已停止', scan_failed: '扫描失败',
}

const utcTime = (value: string) => new Date(value.endsWith('Z') ? value : value + 'Z')
export const dateLabel = (value: string) => utcTime(value).toLocaleString()
export const isActive = (plan: ToolPlan) => ['queued', 'running', 'scan_queued', 'scanning'].includes(plan.status)
export const actionLabel = (plan: ToolPlan) => {
  if (isActive(plan)) return '查看进度'
  if (plan.status === 'preview' && utcTime(plan.expires_at).getTime() > Date.now()) {
    if (plan.kind === 'cleanup' && plan.summary.candidate) return '继续清理'
    if (plan.kind !== 'cleanup' && plan.summary.ready) return '查看并运行'
  }
  return '查看'
}
