import request from '@/utils/request'
import type { ChapterDay } from '@/types/chapter'
import type { ChapterDefinition, ChapterDetail, ChapterDiaryDraft, ChapterDiscoveryTask, ChapterEvent, ChapterItem, ChapterPage, ChapterPhoto, ChapterStatus } from '@/types/chapter'

export const chapterApi = {
  async days(id: string, skip = 0, year?: number, month?: number) {
    const response = await request.get<ChapterPage<ChapterDay>>(`/api/chapters/${id}/diary/days`, { params: { skip, limit: 6, year, month } })
    return response.data
  },
  async generateDay(id: string, day: string) {
    const response = await request.post<{ caption: string; source: 'ai' | 'manual' }>(`/api/chapters/${id}/diary/days/${day}/generate`, {}, { timeout: 120000, silentError: true })
    return response.data
  },
  async dayPhotos(id: string, day: string, skip = 0) {
    const response = await request.get<ChapterPage<ChapterPhoto>>(`/api/chapters/${id}/diary/days/${day}/photos`, { params: { skip, limit: 30 } })
    return response.data
  },
  async saveDay(id: string, day: string, caption: string) {
    const response = await request.put<{ caption: string; source: 'ai' | 'manual' }>(`/api/chapters/${id}/diary/days/${day}`, { caption }, { timeout: 120000 })
    return response.data
  },
  async list(status: ChapterStatus = 'confirmed', hidden = false, skip = 0, limit = 20, reveal = false) {
    const response = await request.get<ChapterPage<ChapterItem>>('/api/chapters', { params: { status, hidden, reveal, skip, limit } })
    return response.data
  },
  async detail(id: string, manage = false) {
    const response = await request.get<ChapterDetail>(`/api/chapters/${id}`, { params: { manage } })
    return response.data
  },
  async photos(id: string, year?: number, skip = 0, limit = 30, manage = false) {
    const response = await request.get<ChapterPage<ChapterPhoto> & { featured?: ChapterPhoto; representatives?: ChapterPhoto[] }>(`/api/chapters/${id}/photos`, { params: { year, skip, limit, manage } })
    return response.data
  },
  async events(id: string, skip = 0, limit = 20, year?: number, manage = false) {
    const response = await request.get<ChapterPage<ChapterEvent>>(`/api/chapters/${id}/events`, { params: { skip, limit, year, manage } })
    return response.data
  },
  async preview(start_date: string, end_date: string | null, chapter_id?: string) {
    const response = await request.post<{ photo_count: number; previous_photo_count?: number; added_photo_count?: number; removed_photo_count?: number; month_counts: Array<{ month: string; count: number }>; preview_photo_ids: string[] }>('/api/chapters/preview', { start_date, end_date, chapter_id })
    return response.data
  },
  async coverOptions(start_date: string, end_date: string | null, skip = 0, limit = 30) {
    const response = await request.post<{ items: Array<{ id: string; photo_time: string }>; total: number }>('/api/chapters/cover-options', { start_date, end_date }, { params: { skip, limit } })
    return response.data
  },
  async discover() {
    const response = await request.post<ChapterDiscoveryTask>('/api/chapters/discover', {})
    return response.data
  },
  async latestDiscovery() {
    const response = await request.get<ChapterDiscoveryTask | null>('/api/chapters/discover/tasks/latest')
    return response.data
  },
  async discoveryTask(id: string) {
    const response = await request.get<ChapterDiscoveryTask>(`/api/chapters/discover/tasks/${id}`)
    return response.data
  },
  async create(payload: ChapterDefinition) {
    const response = await request.post<ChapterItem>('/api/chapters', payload)
    return response.data
  },
  async generateDiary(id: string, payload: { scope: 'introduction' | 'year'; year?: number; version: number; notes?: string }) {
    const response = await request.post<ChapterDiaryDraft>(`/api/chapters/${id}/diary/generate`, payload, { timeout: 120000 })
    return response.data
  },
  async update(id: string, payload: ChapterDefinition & { version: number }) {
    const response = await request.patch<ChapterItem>(`/api/chapters/${id}`, payload)
    return response.data
  },
  async action(id: string, action: 'confirm' | 'ignore' | 'restore' | 'hide' | 'unhide', version: number) {
    const response = await request.post<ChapterItem>(`/api/chapters/${id}/${action}`, { version })
    return response.data
  },
  async merge(payload: ChapterDefinition & { chapter_ids: string[]; versions: Record<string, number> }) {
    const response = await request.post<ChapterItem>('/api/chapters/merge', payload)
    return response.data
  },
  async split(id: string, payload: { split_date: string; first_title: string; second_title: string; version: number }) {
    const response = await request.post<ChapterItem[]>(`/api/chapters/${id}/split`, payload)
    return response.data
  },
  async remove(id: string, version: number) {
    await request.delete(`/api/chapters/${id}`, { params: { version } })
  },
  async yearLinks(years: number[]) {
    const chunks: number[][] = []
    for (let index = 0; index < years.length; index += 30) chunks.push(years.slice(index, index + 30))
    const pages = await Promise.all(chunks.map(async chunk => {
      const params = new URLSearchParams()
      chunk.forEach(year => params.append('years', String(year)))
      const response = await request.get<Record<string, Array<{ id: string; title: string }>>>('/api/chapters/year-links', { params })
      return response.data
    }))
    return Object.assign({}, ...pages) as Record<string, Array<{ id: string; title: string }>>
  },
}
