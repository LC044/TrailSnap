export type MemoryStatus = 'candidate' | 'confirmed' | 'ignored' | 'superseded' | 'archived' | 'deleted'
export type MemoryOrigin = 'auto' | 'manual' | 'album' | 'agent'

export interface MemoryPhoto {
  id: string
  filename: string
  photo_time: string | null
  file_type: string | null
  width: number | null
  height: number | null
  city: string | null
  province: string | null
}

export interface MemoryEvidence {
  id: number
  type: 'time' | 'place' | 'people' | 'semantic' | 'ticket' | 'ocr' | string
  summary: string
  score: number | null
}

export interface MemoryPerson {
  id: string
  name: string
  default_face_id: number | null
  confirmed: boolean
}

export interface MemoryPlace {
  id: number
  name: string
  level: string
  confirmed: boolean
}

export interface MemoryTicket {
  type: 'train' | 'flight'
  id: string
  code?: string
  from?: string
  to?: string
  date_time?: string
  confirmed?: boolean
}

export interface MemoryItem {
  id: string
  status: MemoryStatus
  origin: MemoryOrigin
  title: string
  title_source: 'system' | 'user'
  story: string | null
  story_source: 'system' | 'user'
  story_generation_status: 'idle' | 'generating' | 'failed'
  story_generation_started_at: string | null
  story_generation_error: string | null
  cover_photo_id: string | null
  start_time: string | null
  end_time: string | null
  time_source: 'inferred' | 'confirmed'
  confidence_level: 'strong' | 'review'
  photo_count: number
  places: MemoryPlace[]
  people: MemoryPerson[]
  evidence: MemoryEvidence[]
  preview_photo_ids?: string[]
  photos?: MemoryPhoto[]
  tickets?: MemoryTicket[]
  created_at: string
  updated_at: string
  confirmed_at: string | null
  ignored_at: string | null
  version: number
}

export interface MemoryListResponse {
  items: MemoryItem[]
  total: number
  skip: number
  limit: number
}

export interface MemoryCreatePayload {
  title: string
  story?: string
  photo_ids: string[]
  cover_photo_id?: string
  start_time?: string
  end_time?: string
  place_names?: string[]
  person_ids?: string[]
  ticket_refs?: Array<{ type: 'train' | 'flight'; id: string }>
  origin?: 'manual' | 'album' | 'agent'
}
