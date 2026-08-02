import type { AlbumImage } from '@/types/album'

export type MoonPhase =
  | 'new_moon'
  | 'waxing_crescent'
  | 'first_quarter'
  | 'waxing_gibbous'
  | 'full_moon'
  | 'waning_gibbous'
  | 'last_quarter'
  | 'waning_crescent'

export type MoonPhaseGroup = 'waxing' | 'full' | 'waning'
export type MoonView = 'phase' | 'calendar' | 'all'

export interface MoonPhaseInfo {
  phase: MoonPhase
  group: MoonPhaseGroup
  label: string
  shortLabel: string
  moonAge: number
  illumination: number
  lunarDate: string
  lunarYear: number
  lunarMonth: string
  lunarDay: number
}

export interface MoonObservation extends MoonPhaseInfo {
  photo: AlbumImage
  takenAt: Date
}

export interface MoonPhaseOption {
  phase: MoonPhase
  group: MoonPhaseGroup
  label: string
  shortLabel: string
}
