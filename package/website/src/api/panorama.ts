import request from '@/utils/request'
import type { PanoramaGeometry } from '@/utils/panorama'

export interface PanoramaInfo {
  projection: string | null
  geometry: PanoramaGeometry | null
  override: string | null
  width: number
  height: number
}
export const panoramaApi = {
  async info(id: string, signal?: AbortSignal): Promise<PanoramaInfo> {
    return (await request.get(`/api/photos/${id}/panorama`, { signal, silentError: true, timeout: 15000, retry: false })).data
  },
  async image(id: string, high: boolean, signal?: AbortSignal): Promise<Blob> {
    const response = await request.get(`/api/photos/${id}/panorama/image`, {
      params: { high }, responseType: 'blob', signal, silentError: true, timeout: 20000, retry: false,
    })
    const blob = response.data as Blob
    if (!blob.type.startsWith('image/')) throw new Error('全景预览生成失败')
    return blob
  },
}
