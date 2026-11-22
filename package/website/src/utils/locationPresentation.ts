import type { Photo } from '@/types/album'

export type LocationLevel = 'province' | 'city' | 'district' | 'scene' | 'photo-map'

interface LevelMeta {
  /** 量词 + 名词，例如「座城市」。 */
  unit: string
  /** 独立名词，用于标题/筛选文案。 */
  noun: string
  /** 英语短标签，只用于抬头的小字。 */
  latin: string
}

const LEVEL_META: Record<string, LevelMeta> = {
  province: { unit: '个省份', noun: '省份', latin: 'PROVINCES' },
  city: { unit: '座城市', noun: '城市', latin: 'CITIES' },
  district: { unit: '个区县', noun: '区县', latin: 'DISTRICTS' },
  scene: { unit: '处景区', noun: '景区', latin: 'PLACES' },
  'photo-map': { unit: '处地点', noun: '地点', latin: 'PLACES' },
}

export function locationLevelMeta(level: string): LevelMeta {
  return LEVEL_META[level] ?? LEVEL_META['photo-map']
}

const countFormatter = new Intl.NumberFormat('zh-CN')

/** 1832 → 1,832 */
export function formatCount(value: number | null | undefined): string {
  return countFormatter.format(Math.max(0, Math.round(Number(value) || 0)))
}

/** 1832 → 1,832；18320 → 1.8万，卡片角标里更克制。 */
export function formatCompactCount(value: number | null | undefined): string {
  const count = Math.max(0, Math.round(Number(value) || 0))
  if (count >= 10000) {
    const wan = count / 10000
    return `${wan >= 10 ? Math.round(wan) : wan.toFixed(1).replace(/\.0$/, '')}万`
  }
  return countFormatter.format(count)
}

function parsePhotoDate(photo: Photo | null | undefined): Date | null {
  if (!photo) return null
  const raw = photo.photo_time || photo.time || photo.upload_time
  if (!raw) return null
  const date = new Date(raw)
  return Number.isNaN(date.getTime()) ? null : date
}

/**
 * 封面照片的最近时间，用于卡片副标题。
 * 只展示到月份：地点卡片表达的是「最近一次到访」，精确到日没有意义。
 */
export function formatCoverMonth(photo: Photo | null | undefined): string {
  const date = parsePhotoDate(photo)
  if (!date) return ''
  return `${date.getFullYear()}.${String(date.getMonth() + 1).padStart(2, '0')}`
}

export function coverTimestamp(photo: Photo | null | undefined): number {
  return parsePhotoDate(photo)?.getTime() ?? 0
}

/** 01 / 02 … 给卡片一个轻量的图鉴编号。 */
export function formatIndex(index: number): string {
  return String(index + 1).padStart(2, '0')
}