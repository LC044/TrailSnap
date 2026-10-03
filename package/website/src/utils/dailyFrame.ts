export function monthRange(month: string): [string, string] {
  const [year, number] = month.split('-').map(Number)
  const last = new Date(Date.UTC(year, number, 0)).getUTCDate()
  return [`${month}-01`, `${month}-${String(last).padStart(2, '0')}`]
}

export function monthPadding(month: string): number {
  return (new Date(`${month}-01T12:00:00Z`).getUTCDay() + 6) % 7
}

export function shiftMonth(month: string, delta: number): string {
  const [year, number] = month.split('-').map(Number)
  const result = new Date(Date.UTC(year, number - 1 + delta, 1))
  return `${result.getUTCFullYear()}-${String(result.getUTCMonth() + 1).padStart(2, '0')}`
}

export function workStatus(status: string): string {
  return ({ queued: '排队中', processing: '生成中', ready: '已完成', failed: '生成失败', cancelled: '已取消',
    missing: '作品文件不可用', deleted: '已删除' } as Record<string, string>)[status] || status
}

export function filmFilename(start: string, duration: number, title = '一日一帧'): string {
  const safeTitle = title.replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_').replace(/[. ]+$/, '').trim() || '一日一帧'
  return `${safeTitle}_${start}_${duration}天.mp4`
}
