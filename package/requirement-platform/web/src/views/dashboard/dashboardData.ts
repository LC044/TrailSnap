import type { Dashboard } from '../../api'
import { priorityLabels, severityLabels, statusLabels, typeLabels } from '../../labels'

export const palette = {
  blue: '#2563eb',
  indigo: '#6366f1',
  violet: '#8b5cf6',
  cyan: '#0891b2',
  teal: '#0f9f95',
  green: '#16a36a',
  amber: '#f59e0b',
  orange: '#ea580c',
  red: '#ef4444',
  slate: '#94a3b8',
}

export const typeMeta: Record<string, { label: string; color: string }> = {
  feature: { label: typeLabels.feature!, color: palette.blue },
  improvement: { label: typeLabels.improvement!, color: palette.violet },
  bug: { label: typeLabels.bug!, color: palette.orange },
  other: { label: '其他', color: palette.slate },
}
export const priorityMeta: Record<string, { label: string; color: string }> = {
  urgent: { label: priorityLabels.urgent!, color: palette.red },
  high: { label: priorityLabels.high!, color: palette.orange },
  normal: { label: priorityLabels.normal!, color: palette.blue },
  medium: { label: priorityLabels.normal!, color: palette.blue },
  low: { label: priorityLabels.low!, color: palette.slate },
}
export const severityMeta: Record<string, { label: string; color: string }> = {
  critical: { label: severityLabels.critical!, color: palette.red },
  high: { label: severityLabels.high!, color: palette.orange },
  medium: { label: severityLabels.medium!, color: palette.blue },
  low: { label: severityLabels.low!, color: palette.teal },
}
export const sourceMeta: Record<string, { label: string; color: string }> = {
  platform: { label: '平台提交', color: palette.blue },
  github: { label: 'GitHub 同步', color: palette.violet },
}
export const visibilityMeta: Record<string, { label: string; color: string }> = {
  public: { label: '公开', color: palette.teal },
  private: { label: '仅本人可见', color: palette.amber },
}

export type StatusGroup = { key: string; label: string; color: string; statuses: string[] }

export const statusGroups: StatusGroup[] = [
  { key: 'pending', label: '待处理', color: palette.amber, statuses: ['submitted', 'triaging', 'pending_review', 'needs_information'] },
  { key: 'planned', label: '已规划', color: palette.indigo, statuses: ['candidate', 'accepted', 'scheduled', 'planning', 'candidate_selection', 'scope_locked'] },
  { key: 'developing', label: '开发中', color: palette.blue, statuses: ['developing', 'testing', 'release_ready', 'pr_open', 'merged', 'paused', 'blocked'] },
  { key: 'done', label: '已完成', color: palette.green, statuses: ['released', 'published', 'completed'] },
  { key: 'closed', label: '已关闭', color: palette.slate, statuses: ['closed', 'rejected', 'duplicate', 'withdrawn', 'deferred', 'cancelled'] },
]

const groupByStatus = new Map<string, StatusGroup>()
for (const group of statusGroups) {
  for (const status of group.statuses) groupByStatus.set(status, group)
}
export const statusMeta = (key: string) => {
  const group = groupByStatus.get(key)
  return { label: statusLabels[key] ?? key, color: group?.color ?? palette.slate }
}

export type BreakdownRow = { key: string; label: string; count: number; color: string; pct: number }

export function toRows(source: Record<string, number> | undefined, meta: (key: string) => { label: string; color: string }): BreakdownRow[] {
  const entries = Object.entries(source ?? {}).filter(([, count]) => count > 0)
  const total = entries.reduce((sum, [, count]) => sum + count, 0)
  return entries
    .map(([key, count]) => ({ key, count, ...meta(key), pct: total ? (count / total) * 100 : 0 }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
}

export function groupRows(data: Dashboard) {
  const counts = new Map(statusGroups.map(group => [group.key, 0]))
  for (const [status, count] of Object.entries(data.by_status ?? {})) {
    const key = groupByStatus.get(status)?.key ?? 'closed'
    counts.set(key, (counts.get(key) ?? 0) + count)
  }
  const total = [...counts.values()].reduce((sum, count) => sum + count, 0)
  return statusGroups.map(group => ({
    ...group,
    count: counts.get(group.key) ?? 0,
    pct: total ? ((counts.get(group.key) ?? 0) / total) * 100 : 0,
  }))
}

export type TrendPoint = {
  date: string; count: number
  feature?: number; improvement?: number; bug?: number; other?: number
}

/** 旧版后端只返回 30 天数据，缺失的按类型拆分会自动降级。 */
export function trendPoints(data: Dashboard): TrendPoint[] {
  const daily = data.daily_new_90d?.length ? data.daily_new_90d : data.daily_new_30d ?? []
  const byType = new Map((data.daily_new_by_type_90d ?? []).map(point => [point.date, point]))
  return daily.map(point => {
    const split = byType.get(point.date)
    if (!split) return { date: point.date, count: point.count }
    return {
      date: point.date, count: point.count,
      feature: split.feature, improvement: split.improvement, bug: split.bug, other: split.other,
    }
  })
}

export const formatNumber = (value: number) => value.toLocaleString('zh-CN')
export const formatPct = (value: number) => `${value.toFixed(value < 10 ? 1 : 0)}%`
export const shortDate = (value: string) => value.slice(5).replace('-', '/')

export function formatUpdatedAt(value?: string) {
  if (!value) return '刚刚'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '刚刚'
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

export function downloadCsv(filename: string, rows: Array<Array<string | number>>) {
  const content = rows.map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(',')).join('\r\n')
  const blob = new Blob([`\ufeff${content}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}
