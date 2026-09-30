export type ChapterStatus = 'candidate' | 'confirmed' | 'ignored' | 'superseded' | 'deleted'

export interface ChapterEvidence { type: string; summary: string; photo_ids?: string[]; [key: string]: unknown }
export interface ChapterItem {
  id: string
  status: ChapterStatus
  origin: 'auto' | 'manual'
  is_hidden: boolean
  title: string
  summary: string | null
  start_date: string
  end_date: string | null
  cover_photo_id: string | null
  evidence: ChapterEvidence[]
  photo_count: number
  event_count: number
  version: number
  source_ids: string[]
}
export interface ChapterPhoto { id: string; filename: string; photo_time: string; file_type: string; width: number | null; height: number | null }
export interface ChapterDay {
  day: string
  photo_count: number
  photos: ChapterPhoto[]
  caption: string
  source: 'ai' | 'manual' | null
  needs_generation: boolean
  people: Array<{ id: string; name: string; photo_count: number }>
  places: string[]
  tags: string[]
  events: ChapterEvent[]
}
export interface ChapterEvent { id: string; title: string; start_time: string | null; cover_photo_id: string | null }
export interface ChapterDetail extends ChapterItem {
  summary_source?: 'user' | 'ai'
  diary_entries?: Record<string, ChapterDiaryEntry>
  years: number[]
  people: Array<{ id: string; name: string; photo_count: number }>
  places: Array<{ name: string; photo_count: number }>
  events: ChapterEvent[]
}
export interface ChapterDiaryEntry { title: string; body: string; source: 'user' | 'ai'; source_photo_ids?: string[]; source_memory_ids?: string[] }
export interface ChapterDiaryDraft extends ChapterDiaryEntry { scope: 'introduction' | 'year'; year: number | null; version: number; photo_count: number }
export interface ChapterDefinition { title: string; summary?: string | null; summary_source?: 'user' | 'ai'; diary_entries?: Record<string, ChapterDiaryEntry>; start_date: string; end_date?: string | null; cover_photo_id?: string | null }
export interface ChapterPage<T> { items: T[]; total: number; skip?: number; limit?: number }
export interface ChapterDiscoveryTask { id: string; status: 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled'; created: number; error: string | null }
