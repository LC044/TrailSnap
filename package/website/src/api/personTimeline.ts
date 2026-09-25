import request from '@/utils/request'

export interface TimelinePhoto { id: string; photo_time: string; thumbnail_url: string; filename?: string }
export interface TimelineMemory { id: string; title: string; start_time: string | null; photo_ids: string[]; source: string; kind: 'memory' | 'holiday' | 'travel' }
export interface TimelineYear { year: number; photo_count: number; representative_event: { start_at: string; end_at: string; photo_count: number }; representative_photos: Pick<TimelinePhoto, 'id' | 'thumbnail_url' | 'photo_time'>[]; memories: TimelineMemory[] }
export interface PersonTimeline {
  people: { id: string; name: string; avatar_url: string | null; tags: string[] }[]
  mode: 'solo' | 'pair'
  photo_count: number
  year_count: number
  years: TimelineYear[]
  first_photo: { id: string; photo_time: string } | null
  latest_photo: { id: string; photo_time: string } | null
  peak_month: { month: string; count: number } | null
}
export interface TimelineYearDetail { year: number; total: number; photos: TimelinePhoto[]; memories: TimelineMemory[]; next_skip: number | null }
export interface TimelineHiddenRule { id: string; start_at: string; end_at: string; photo_count: number }

const params = (withId?: string) => withId ? { with_id: withId } : {}
export const personTimelineApi = {
  async get(id: string, withId?: string) {
    return (await request.get<PersonTimeline>(`/api/faces/identities/${id}/timeline`, { params: params(withId) })).data
  },
  async year(id: string, year: number, withId?: string, skip = 0) {
    return (await request.get<TimelineYearDetail>(`/api/faces/identities/${id}/timeline/years/${year}`, { params: { ...params(withId), skip } })).data
  },
  async hidden(id: string, withId?: string) {
    return (await request.get<TimelineHiddenRule[]>(`/api/faces/identities/${id}/timeline/hidden`, { params: params(withId) })).data
  },
  async hide(id: string, startAt: string, endAt: string, withId?: string, dryRun = false) {
    return (await request.post<{ id?: string; photo_count: number; photos?: TimelinePhoto[] }>(`/api/faces/identities/${id}/timeline/hidden`,
      { start_at: startAt, end_at: endAt }, { params: { ...params(withId), dry_run: dryRun } })).data
  },
  async restore(id: string, ruleId: string, withId?: string) {
    return (await request.delete(`/api/faces/identities/${id}/timeline/hidden/${ruleId}`, { params: params(withId) })).data
  },
}
