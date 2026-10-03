import request from '@/utils/request'
import { toServerUrl } from '@/config/server'
import type { DailyFrame, DailyFrameAsset, DailyFrameCalendar, DailyFrameSelection, DailyFrameSettings,
  DailyFrameSuggestion, DailyFilmSettings, DailyFilmComposition, DailyFilmWork } from '@/types/dailyFrame'

const root = '/api/daily-frame'
export const dailyFrameApi = {
  async settings() { return (await request.get<DailyFrameSettings>(`${root}/settings`, { silentError: true })).data },
  async initialize(timezone: string) { return (await request.put<DailyFrameSettings>(`${root}/settings`, { timezone })).data },
  async calendar(start: string, end: string) {
    return (await request.get<DailyFrameCalendar>(`${root}/calendar`, { params: { start, end } })).data
  },
  async day(day: string) { return (await request.get<DailyFrame>(`${root}/days/${day}`)).data },
  async candidates(day: string, skip = 0, kind = 'all') {
    return (await request.get<{ items: DailyFrameAsset[]; total: number }>(`${root}/days/${day}/candidates`,
      { params: { skip, kind, limit: 40 } })).data
  },
  async asset(id: string) { return (await request.get<DailyFrameAsset>(`${root}/assets/${id}`)).data },
  async source(id: string, mode: string, signal?: AbortSignal) {
    return (await request.get<Blob>(`${root}/assets/${id}/file`,
      { params: { mode }, responseType: 'blob', timeout: 120000, signal, silentError: true })).data
  },
  async sourceUrl(id: string, mode: string) {
    const data = (await request.get<{ token: string }>(`${root}/assets/${id}/access`, { params: { mode } })).data
    return toServerUrl(`${root}/assets/${id}/file?mode=${mode}&token=${encodeURIComponent(data.token)}`)
  },
  async save(day: string, value: DailyFrameSelection) {
    return (await request.put<DailyFrame>(`${root}/days/${day}`, value, { silentError: true })).data
  },
  async remove(day: string, version: number) {
    return (await request.post<DailyFrame>(`${root}/days/${day}/remove`, { version })).data
  },
  async undo(day: string, version: number) {
    return (await request.post<DailyFrame>(`${root}/days/${day}/undo-remove`, { version })).data
  },
  async suggestions(start: string, end: string) {
    return (await request.get<{ items: DailyFrameSuggestion[]; preserved: number }>(`${root}/fill`,
      { params: { start, end }, timeout: 120000 })).data
  },
  async fill(items: Array<DailyFrameSelection & { day: string }>) {
    return (await request.post<{ items: Array<{ day: string; status: 'saved' | 'skipped' | 'failed'; reason?: string }> }>(
      `${root}/fill`, { items }, { timeout: 120000 })).data
  },
  async composition(value: DailyFilmSettings) {
    return (await request.post<DailyFilmComposition>(`${root}/composition`, value, { silentError: true })).data
  },
  async create(value: DailyFilmSettings, fingerprint: string, isPreview = false) {
    return (await request.post<DailyFilmWork>(`${root}/works`, { ...value, fingerprint, is_preview: isPreview },
      { silentError: true })).data
  },
  async works(skip = 0) {
    return (await request.get<{ items: DailyFilmWork[]; total: number }>(`${root}/works`, { params: { skip } })).data
  },
  async work(id: string) { return (await request.get<DailyFilmWork>(`${root}/works/${id}`)).data },
  async poster(id: string) { return (await request.get<Blob>(`${root}/works/${id}/poster`, { responseType: 'blob', silentError: true })).data },
  async cancel(id: string) { await request.post(`${root}/works/${id}/cancel`) },
  async retry(id: string) { return (await request.post<DailyFilmWork>(`${root}/works/${id}/retry`)).data },
  async delete(id: string) { await request.delete(`${root}/works/${id}`) },
  async file(id: string, download = false, signal?: AbortSignal) {
    return (await request.get<Blob>(`${root}/works/${id}/file`,
      { params: { download }, responseType: 'blob', timeout: 180000, signal })).data
  },
  async playbackUrl(id: string) {
    const data = (await request.get<{ token: string }>(`${root}/works/${id}/access`)).data
    return toServerUrl(`${root}/works/${id}/file?token=${encodeURIComponent(data.token)}`)
  },
}

export function dailyFrameError(error: unknown): string {
  const value = error as { msg?: string; message?: string; response?: { data?: { msg?: string; detail?: string } } }
  return value.response?.data?.msg || value.response?.data?.detail || value.msg || '操作失败，请重试'
}
