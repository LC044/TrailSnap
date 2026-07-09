import request from '@/utils/request'
import type { AlbumImage,Photo, SimilarPhoto } from '@/types/album'
import type { Task as TaskResponse } from '@/api/tasks'

export const photoApi = {
  // Similar Photo Task API
  async createSimilarTask(threshold: number = 0.9) {
    const data = await request.post<TaskResponse>('/api/toolbox/similar/tasks', null, {
      params: { threshold }
    });
    return data.data;
  },

  async getLatestSimilarTask() {
    const data = await request.get<TaskResponse | null>('/api/toolbox/similar/tasks/latest');
    return data.data;
  },

  async getSimilarTask(taskId: string) {
    const data = await request.get<TaskResponse>(`/api/toolbox/similar/tasks/${taskId}`);
    return data.data;
  },

  async getSimilarTaskResult(taskId: string, skip: number = 0, limit: number = 20) {
    const data = await request.get<Photo[][]>(`/api/toolbox/similar/tasks/${taskId}/result`, {
      params: { skip, limit }
    });
    return data.data;
  },

  async cancelSimilarTask(taskId: string) {
    await request.delete(`/api/toolbox/similar/tasks/${taskId}`);
  },

  async transferPhotos(photoIds: string[], targetPath: string, action: 'move' | 'copy') {
    const { data } = await request.post('/api/photos/batch/transfer', {
      photo_ids: photoIds,
      target_path: targetPath,
      action
    });
    return data;
  },

  // Legacy (Deprecated)
  async getSimilarPhotos(threshold: number = 0.9) {
    const data = await request.get<SimilarPhoto[][]>('/api/toolbox/similar', {
      params: { threshold },
      timeout: 120000
    });
    return data.data;
  },

  async getCleanupPhotos(params: { skip: number; limit: number; sort_by: 'asc' | 'desc' }) {
    const data = await request.get<Photo[]>('/api/toolbox/cleanup', {
      params
    });
    return data.data;
  },

  async getOnThisDayPhotos(params?: { year?: number; month?: number; day?: number; limit?: number }) {
    const data = await request.get<Photo[]>('/api/photos/on-this-day', {
      params
    });
    return data.data;
  },

  async getPhotoDescription(photoId: string) {
    const data = await request.get<any>(`/api/photos/${photoId}/description`);
    return data.data;
  },

  async getRandomPhotos(limit: number = 10): Promise<Photo[]> {
    const data: any = await request.get('/api/photos/random', {
      params: { limit }
    });
    return data.data;
  },

  async batchDownload(photoIds: string[]) {
    const res = await request.post('/api/photos/batch-download', 
      { photo_ids: photoIds }, 
      { responseType: 'blob', timeout: 0 } // timeout: 0 禁用超时，防止大文件打包下载被 30s 中断
    );
    const url = window.URL.createObjectURL(new Blob([res.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `trailsnap_export.zip`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  }
}
