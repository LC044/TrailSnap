import request from '@/utils/request'
import type { MemoryCreatePayload, MemoryItem, MemoryListResponse, MemoryStatus } from '@/types/memory'

export const memoryApi = {
  async list(status: MemoryStatus, skip = 0, limit = 20) {
    const response = await request.get<MemoryListResponse>('/api/memories', { params: { status, skip, limit } })
    return response.data
  },

  async counts() {
    const response = await request.get<Record<'candidate' | 'confirmed' | 'ignored', number>>('/api/memories/counts')
    return response.data
  },

  async detail(id: string) {
    const response = await request.get<MemoryItem>(`/api/memories/${id}`)
    return response.data
  },

  async create(payload: MemoryCreatePayload) {
    const response = await request.post<MemoryItem>('/api/memories', payload)
    return response.data
  },

  async update(id: string, payload: Partial<MemoryCreatePayload>) {
    const response = await request.patch<MemoryItem>(`/api/memories/${id}`, payload)
    return response.data
  },

  async discover(payload: { start_time?: string; end_time?: string; min_photos?: number; max_candidates?: number } = {}) {
    const response = await request.post<{ created: number; items: MemoryItem[] }>('/api/memories/discover', payload, { timeout: 120000 })
    return response.data
  },

  async confirm(id: string) {
    const response = await request.post<MemoryItem>(`/api/memories/${id}/confirm`)
    return response.data
  },

  async generateStory(id: string, tone = '温暖、克制、真实') {
    const response = await request.post<MemoryItem>(`/api/memories/${id}/story/generate`, { tone }, { timeout: 120000 })
    return response.data
  },

  async ignore(id: string) {
    const response = await request.post<MemoryItem>(`/api/memories/${id}/ignore`)
    return response.data
  },

  async restore(id: string) {
    const response = await request.post<MemoryItem>(`/api/memories/${id}/restore`)
    return response.data
  },

  async archive(id: string) {
    const response = await request.post<MemoryItem>(`/api/memories/${id}/archive`)
    return response.data
  },

  async removePhotos(id: string, photoIds: string[]) {
    const response = await request.post<MemoryItem>(`/api/memories/${id}/photos/remove`, { photo_ids: photoIds })
    return response.data
  },

  async addPhotos(id: string, photoIds: string[]) {
    const response = await request.post<MemoryItem>(`/api/memories/${id}/photos/add`, { photo_ids: photoIds })
    return response.data
  },

  async merge(payload: { memory_ids: string[]; title?: string; story?: string; cover_photo_id?: string }) {
    const response = await request.post<MemoryItem>('/api/memories/merge', payload)
    return response.data
  },

  async split(id: string, parts: Array<{ title: string; photo_ids: string[] }>) {
    const response = await request.post<MemoryItem[]>(`/api/memories/${id}/split`, { parts })
    return response.data
  },

  async remove(id: string) {
    await request.delete(`/api/memories/${id}`)
  },
}
