import request from '@/utils/request';
import type { Task as TaskResponse } from './tasks';
import type { Photo } from '@/types/album';

export interface DuplicatePhotoGroup {
  md5: string;
  photos: Photo[];
}

export const toolboxApi = {
  // Trigger duplicate photo scan task
  async scanDuplicatePhotos() {
    const data = await request.post<TaskResponse>('/api/toolbox/duplicate-photos/scan');
    return data.data;
  },

  // Get grouped duplicate photos
  async getDuplicatePhotos() {
    const data = await request.get<DuplicatePhotoGroup[]>('/api/toolbox/duplicate-photos')
    return data.data
  },

  async createOrganizeTask(payload: any) {
    const data = await request.post<TaskResponse>('/api/toolbox/organize/tasks', payload)
    return data.data
  },

  async getOrganizePreviewOptions(payload: { strategy: string, location_granularity?: string, location_format?: string }) {
    const data = await request.post<{ options: string[] }>('/api/toolbox/organize/preview-options', payload)
    return data.data
  },

  async getLatestOrganizeTask() {
    const data = await request.get<TaskResponse | null>('/api/toolbox/organize/tasks/latest')
    return data.data
  },

  async createRenameTask(payload: { target_root_path: string, prefix?: string, suffix?: string }) {
    const data = await request.post<TaskResponse>('/api/toolbox/rename/tasks', payload)
    return data.data
  },

  async getLatestRenameTask() {
    const data = await request.get<TaskResponse | null>('/api/toolbox/rename/tasks/latest')
    return data.data
  },

  async createTimeFromFilenameTask(payload: { target_root_path: string }) {
    const data = await request.post<TaskResponse>('/api/toolbox/time-from-filename/tasks', payload)
    return data.data
  },

  async getLatestTimeFromFilenameTask() {
    const data = await request.get<TaskResponse | null>('/api/toolbox/time-from-filename/tasks/latest')
    return data.data
  }
};
