import type {
  MoonObservation,
  MoonPhase,
  MoonPhaseGroup,
  MoonPhaseInfo,
  MoonPhaseOption,
} from '@/types/moon'
import type { AlbumImage } from '@/types/album'

const SYNODIC_MONTH = 29.530588853
const DAY_MS = 86_400_000
// 2000-01-06 18:14 UTC 是常用的已知朔时近似基准。
const KNOWN_NEW_MOON_UTC = Date.UTC(2000, 0, 6, 18, 14)

export const MOON_PHASES: MoonPhaseOption[] = [
  { phase: 'new_moon', group: 'waxing', label: '新月', shortLabel: '初一' },
  { phase: 'waxing_crescent', group: 'waxing', label: '蛾眉月', shortLabel: '渐盈' },
  { phase: 'first_quarter', group: 'waxing', label: '上弦月', shortLabel: '上弦' },
  { phase: 'waxing_gibbous', group: 'waxing', label: '盈凸月', shortLabel: '渐盈' },
  { phase: 'full_moon', group: 'full', label: '满月', shortLabel: '十五' },
  { phase: 'waning_gibbous', group: 'waning', label: '亏凸月', shortLabel: '渐亏' },
  { phase: 'last_quarter', group: 'waning', label: '下弦月', shortLabel: '下弦' },
  { phase: 'waning_crescent', group: 'waning', label: '残月', shortLabel: '月末' },
]

const PHASE_BY_NAME = new Map(MOON_PHASES.map((item) => [item.phase, item]))

export const formatChineseLunarDay = (value: string | number) => {
  const day = Number.parseInt(value, 10)
  if (!Number.isFinite(day) || day < 1 || day > 30) return value
  const digits = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
  if (day <= 10) return day === 10 ? '初十' : `初${digits[day - 1]}`
  if (day < 20) return `十${digits[day - 11] ?? ''}`
  if (day === 20) return '二十'
  if (day < 30) return `廿${digits[day - 21]}`
  return '三十'
}

export const getChineseLunarDateParts = (date: Date) => {
  try {
    const parts = new Intl.DateTimeFormat('zh-CN-u-ca-chinese', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    }).formatToParts(date)
    const values = Object.fromEntries(parts.map((part) => [part.type, part.value])) as Record<string, string>
    const lunarDay = Number.parseInt(values.day ?? '', 10)
    return {
      year: Number.parseInt(values.relatedYear ?? values.year ?? String(date.getFullYear()), 10),
      month: values.month ?? '农历月份',
      day: Number.isFinite(lunarDay) ? lunarDay : 1,
    }
  } catch {
    return { year: date.getFullYear(), month: '农历月份', day: 1 }
  }
}

const getPhase = (age: number): MoonPhase => {
  if (age < 1.84566 || age >= 27.68493) return 'new_moon'
  if (age < 5.53699) return 'waxing_crescent'
  if (age < 9.22831) return 'first_quarter'
  if (age < 12.91963) return 'waxing_gibbous'
  if (age < 16.61096) return 'full_moon'
  if (age < 20.30228) return 'waning_gibbous'
  if (age < 23.99361) return 'last_quarter'
  return 'waning_crescent'
}

const formatLunarDate = (date: Date) => {
  const lunar = getChineseLunarDateParts(date)
  return `${lunar.month}${formatChineseLunarDay(lunar.day)}`
}

export const calculateMoonPhase = (input: Date | string | number): MoonPhaseInfo => {
  const date = input instanceof Date ? input : new Date(input)
  const daysSinceKnownNewMoon = (date.getTime() - KNOWN_NEW_MOON_UTC) / DAY_MS
  const moonAge = ((daysSinceKnownNewMoon % SYNODIC_MONTH) + SYNODIC_MONTH) % SYNODIC_MONTH
  const phase = getPhase(moonAge)
  const option = PHASE_BY_NAME.get(phase)!
  const illumination = (1 - Math.cos((2 * Math.PI * moonAge) / SYNODIC_MONTH)) / 2
  const lunar = getChineseLunarDateParts(date)

  return {
    phase,
    group: option.group as MoonPhaseGroup,
    label: option.label,
    shortLabel: option.shortLabel,
    moonAge,
    illumination,
    lunarDate: formatLunarDate(date),
    lunarYear: lunar.year,
    lunarMonth: lunar.month,
    lunarDay: lunar.day,
  }
}

export const createMoonObservation = (photo: AlbumImage): MoonObservation | null => {
  if (!photo.hasPhotoTime || !Number.isFinite(photo.timestamp)) return null
  const takenAt = new Date(photo.timestamp)
  if (Number.isNaN(takenAt.getTime())) return null

  return {
    photo,
    takenAt,
    ...calculateMoonPhase(takenAt),
  }
}

export const getMoonPhaseForLunarDay = (day: number): MoonPhase => {
  if (day === 1) return 'new_moon'
  if (day <= 6) return 'waxing_crescent'
  if (day <= 9) return 'first_quarter'
  if (day <= 13) return 'waxing_gibbous'
  if (day <= 17) return 'full_moon'
  if (day <= 21) return 'waning_gibbous'
  if (day <= 24) return 'last_quarter'
  return 'waning_crescent'
}

export const findNextChineseLunarDay = (lunarDay: number, from: Date = new Date()) => {
  if (lunarDay < 1 || lunarDay > 30) return null
  const cursor = new Date(from)
  cursor.setHours(12, 0, 0, 0)
  // 农历三十并非每个月都有，扫描三个月可以覆盖下一个大月。
  for (let offset = 0; offset <= 90; offset += 1) {
    if (getChineseLunarDateParts(cursor).day === lunarDay) return new Date(cursor)
    cursor.setDate(cursor.getDate() + 1)
  }
  return null
}

export const formatIllumination = (illumination: number) => `${Math.round(illumination * 100)}%`
