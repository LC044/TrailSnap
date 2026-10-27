import type { AlbumImage, TimelineMonth } from '@/types/album'

export type TimeField = 'photo_time' | 'upload_time'
export type TimeGranularity = 'year' | 'month' | 'day'

export const timelineParts = (timestamp: number) => {
  if (!Number.isFinite(timestamp)) return { year: 0, month: 0, day: 0, dayKey: 'all' }
  const date = new Date(timestamp)
  const year = date.getFullYear(), month = date.getMonth() + 1, day = date.getDate()
  return { year, month, day, dayKey: `${year}-${month}-${day}` }
}

export function overviewBuckets(months: TimelineMonth[], granularity: 'year' | 'month') {
  const buckets = new Map<string, TimelineMonth>()
  for (const month of months) {
    const key = granularity === 'year' ? String(month.year) : `${month.year}-${month.month}`
    const previous = buckets.get(key)
    if (previous) previous.count += month.count
    else buckets.set(key, { ...month })
  }
  return [...buckets.entries()].map(([key, bucket]) => ({ ...bucket, key }))
}

export function timelineTimestamp(photo: AlbumImage, field: TimeField) {
  const raw = field === 'upload_time' ? photo.uploadTime : photo.photoTime
  return raw ? new Date(raw).getTime() : NaN
}

export function nearestTimelinePhoto(photos: AlbumImage[], anchor: AlbumImage) {
  const unknown = photos.filter(photo => !Number.isFinite(photo.timestamp))
  const candidates = !Number.isFinite(anchor.timestamp) && unknown.length ? unknown : photos
  const distance = (photo: AlbumImage) => Number.isFinite(anchor.timestamp) && Number.isFinite(photo.timestamp)
    ? Math.abs(photo.timestamp - anchor.timestamp) : Infinity
  return [...candidates].sort((a, b) => distance(a) - distance(b) || (a.id < b.id ? 1 : a.id > b.id ? -1 : 0))[0] ?? null
}
