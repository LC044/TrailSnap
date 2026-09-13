export const typeLabels: Record<string, string> = {
  bug: '问题修复',
  improvement: '体验优化',
  feature: '新功能',
}

export const severityLabels: Record<string, string> = {
  low: '低',
  medium: '中',
  high: '高',
  critical: '严重',
}

export const priorityLabels: Record<string, string> = {
  low: '低',
  normal: '普通',
  high: '高',
  urgent: '紧急',
}

export const statusLabels: Record<string, string> = {
  submitted: '待分析',
  triaging: '分析中',
  pending_review: '待审核',
  needs_information: '待补充',
  candidate: '开发候选',
  accepted: '规格已批准',
  rejected: '已拒绝',
  deferred: '已暂缓',
  duplicate: '已合并',
  scheduled: '已规划',
  developing: '开发中',
  testing: '测试中',
  release_ready: '待发布',
  merged: '已合并待发布',
  released: '已发布',
  withdrawn: '已撤回',
  closed: '已关闭',
}

export const requirementStatuses = Object.keys(statusLabels)

export const batchStatusLabels: Record<string, string> = {
  planning: '规划中',
  candidate_selection: '候选确认中',
  scope_locked: '范围已锁定',
  developing: '开发中',
  testing: '测试中',
  release_ready: '待发布',
  published: '已发布',
  completed: '已完成',
  blocked: '已阻塞',
  paused: '已暂停',
  cancelled: '已取消',
}

export const deliveryLabels: Record<string, string> = {
  not_started: '未开始',
  developing: '开发中',
  pr_open: 'PR 已创建',
  testing: '测试中',
  completed: '已完成',
  blocked: '已阻塞',
  removed: '已移出',
}

export const batchTypeLabels: Record<string, string> = {
  fix: '修复',
  feature: '功能',
  major: '重大',
  hotfix: '紧急修复',
}

export const roleLabels: Record<string, string> = {
  viewer: '查看者',
  admin: '管理员',
  owner: '所有者',
}

export const statusLabel = (value: string) => statusLabels[value] || batchStatusLabels[value] || value
export const deliveryLabel = (value: string) => deliveryLabels[value] || value
export const typeLabel = (value: string) => typeLabels[value] || value
export const severityLabel = (value: string) => severityLabels[value] || value
export const priorityLabel = (value: string) => priorityLabels[value] || value
export const roleLabel = (value: string) => roleLabels[value] || value
export const batchTypeLabel = (value: string) => batchTypeLabels[value] || value

export const typeOrder: Record<string, number> = { feature: 0, improvement: 1, bug: 2 }

export const reviewActionLabels: Record<string, string> = {
  candidate: '进入候选池',
  needs_information: '需要补充',
  deferred: '暂缓',
  rejected: '拒绝',
  duplicate: '重复需求',
  close: '关闭',
}

const hashHues = [210, 160, 280, 20, 340, 45, 120, 260, 190, 0]

export function avatarColor(name: string) {
  let hash = 0
  for (const ch of name) hash = (hash * 31 + ch.codePointAt(0)!) >>> 0
  const hue = hashHues[hash % hashHues.length]
  return { background: `hsl(${hue} 72% 92%)`, color: `hsl(${hue} 60% 34%)` }
}

export function formatDate(value: string) {
  const date = parseServerDate(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(date).replace(/\//g, '-')
}

export function parseServerDate(value: string) {
  // SQLite drops timezone information from timezone-aware DateTime columns.
  // Server timestamps are UTC, so restore the missing marker before parsing.
  const hasTimezone = /(?:z|[+-]\d{2}:\d{2})$/i.test(value)
  return new Date(hasTimezone ? value : `${value}Z`)
}

export function formatDateTime(value: string) {
  const date = parseServerDate(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).format(date)
}
