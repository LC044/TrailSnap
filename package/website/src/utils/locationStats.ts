import type { HeatmapItem } from '@/api/location'

export interface TimeBucket {
  label: string
  start: string
  end: string
  photos: number
  days: number
}
export function statsYears(data: HeatmapItem[]): number[] {
  return [...new Set(data.map(d => Number(d.date.slice(0, 4))))].sort((a, b) => b - a)
}
/** Calendar strings stay local; avoid shifting dates through UTC. */
export function timeBuckets(data: HeatmapItem[], grain: 'year' | 'month', year: number): TimeBucket[] {
  const years = statsYears(data)
  if (!years.length) return []
  const first = grain === 'month' ? 1 : years[years.length - 1]
  const last = grain === 'month' ? 12 : years[0]
  const totals = new Map<string, { photos: number; dates: Set<string> }>()
  for (const day of data) {
    if (day.count <= 0) continue
    const key = day.date.slice(0, grain === 'month' ? 7 : 4)
    const value = totals.get(key) ?? { photos: 0, dates: new Set<string>() }
    value.photos += day.count
    value.dates.add(day.date)
    totals.set(key, value)
  }
  return Array.from({ length: last - first + 1 }, (_, index) => {
    const n = first + index
    const key = grain === 'month' ? `${year}-${String(n).padStart(2, '0')}` : String(n)
    const total = totals.get(key)
    return {
      label: grain === 'month' ? `${n}月` : key,
      start: grain === 'month' ? `${key}-01` : `${key}-01-01`,
      end: grain === 'month' ? `${key}-${new Date(year, n, 0).getDate()}` : `${key}-12-31`,
      photos: total?.photos ?? 0,
      days: total?.dates.size ?? 0,
    }
  })
}
export function calendarWeeks(data: HeatmapItem[], year: number) {
  const counts = new Map(data.map(d => [d.date, d.count]))
  const cursor = new Date(year, 0, 1)
  cursor.setDate(cursor.getDate() - cursor.getDay())
  const end = new Date(year, 11, 31)
  const weeks: { key: string; month: string; days: { date: string; count: number; outside: boolean }[] }[] = []
  while (cursor <= end) {
    let month = ''
    const days = Array.from({ length: 7 }, () => {
      const outside = cursor.getFullYear() !== year
      const date = `${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, '0')}-${String(cursor.getDate()).padStart(2, '0')}`
      if (!outside && cursor.getDate() === 1) month = `${cursor.getMonth() + 1}月`
      const day = { date, count: outside ? 0 : counts.get(date) ?? 0, outside }
      cursor.setDate(cursor.getDate() + 1)
      return day
    })
    weeks.push({ key: days[0].date, month, days })
  }
  return weeks
}
