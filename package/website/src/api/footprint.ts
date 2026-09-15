import request from '@/utils/request'
import type { FootprintData } from '@/types/footprint'
import type { Photo } from '@/types/album'

export const footprintApi = {
  async overview(year: number | null, signal?: AbortSignal, bbox?: string) {
    const response = await request.get<FootprintData>('/api/locations/footprint', {
      params: { year: year ?? undefined, max_points: 800, bbox }, signal,
    })
    return response.data
  },
  async photos(cityId: string, year: number | null, skip = 0, signal?: AbortSignal) {
    const response = await request.get<Photo[]>('/api/locations/footprint/photos', {
      params: { city_id: cityId, year: year ?? undefined, skip, limit: 24 }, signal,
    })
    return response.data
  },
}
