export interface DailyFrameAsset {
  id: string
  photo_time: string | null
  file_type: 'image' | 'video' | 'live_photo'
  duration: number
  available: boolean
  reason: string | null
  has_motion: boolean
  day?: string | null
}

export interface DailyFrameSelection {
  photo_id: string
  mode: 'still' | 'motion'
  start_seconds: number
  caption: string
  version: number
}

export interface DailyFrame extends Omit<DailyFrameSelection, 'photo_id'> {
  day: string
  photo_id?: string | null
  removed: boolean
  available: boolean
  reason?: string | null
  date_changed?: boolean
  photo?: DailyFrameAsset | null
}

export interface DailyFrameDay {
  day: string
  candidate_count: number
  future: boolean
  frame: DailyFrame | null
}

export interface DailyFrameSettings {
  initialized: boolean
  timezone: string | null
  locked: boolean
  revision: number
  today: string | null
  export: { available: boolean; reason: string | null }
}

export interface DailyFrameCalendar {
  timezone: string
  today: string
  revision: number
  days: DailyFrameDay[]
}

export interface DailyFrameSuggestion extends DailyFrameSelection {
  day: string
  photo: DailyFrameAsset
}

export interface DailyFilmSettings {
  start_date: string
  end_date: string
  title: string
  orientation: 'portrait' | 'landscape'
  fit: 'contain' | 'cover'
  show_date: boolean
  show_caption: boolean
  background: string
  skip_invalid: boolean
}

export interface DailyFilmComposition {
  fingerprint: string
  snapshot: { settings: DailyFilmSettings; timezone: string; frames: Array<DailyFrameSelection & { day: string }> }
  invalid: Array<{ day: string; reason: string }>
  empty_days: number
  duration: number
}

export interface DailyFilmWork {
  id: string
  status: 'queued' | 'processing' | 'ready' | 'failed' | 'cancelled' | 'deleted' | 'missing'
  is_preview: boolean
  settings: DailyFilmSettings
  duration: number
  days: string[]
  processed_items: number
  error: string | null
  file_available: boolean
  calendar_changed: boolean
  created_at: string
}
