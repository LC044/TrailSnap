import request from '@/utils/request';
import type { BaseResponse } from '@/types/railway';

export interface StorageDistribution {
  name: string;
  size: number;
  count: number;
}

export interface StorageRecoverable {
  similar: { size: number; count: number };
  duplicate: { size: number; count: number };
  screenshot: { size: number; count: number };
  video: { size: number; count: number };
}

export interface StorageOverview {
  total_size: number;
  total_files: number;
  disk_total_size?: number;
  disk_free_size?: number;
  scan_date: string | null;
}

export interface LargeFile {
  id: string;
  path: string;
  size: number;
  type: string;
  filename: string;
}

export const storageApi = {
  getOverview: () => {
    return request.get<any, BaseResponse<StorageOverview>>('/api/storage/overview');
  },
  getStatsByType: () => {
    return request.get<any, BaseResponse<StorageDistribution[]>>('/api/storage/stats/type');
  },
  getStatsByDevice: () => {
    return request.get<any, BaseResponse<StorageDistribution[]>>('/api/storage/stats/device');
  },
  getStatsByFolder: () => {
    return request.get<any, BaseResponse<StorageDistribution[]>>('/api/storage/stats/folder');
  },
  getStatsRecoverable: () => {
    return request.get<any, BaseResponse<StorageRecoverable>>('/api/storage/stats/recoverable');
  },
  getTimeDistribution: (groupBy: 'day' | 'month' | 'year' = 'month', startDate?: string, endDate?: string) => {
    return request.get<any, BaseResponse<StorageDistribution[]>>('/api/storage/time-distribution', { 
      params: { 
        group_by: groupBy,
        start_date: startDate,
        end_date: endDate
      } 
    });
  },
  getTopLargeFiles: () => {
    return request.get<any, BaseResponse<LargeFile[]>>('/api/storage/top-large-files');
  },
  getScreenshots: (skip = 0, limit = 50) => {
    return request.get<any, BaseResponse<any[]>>('/api/storage/screenshots', { params: { skip, limit } });
  },
  moveToNonArchive: (photoIds: string[]) => {
    return request.post<any, BaseResponse<any>>('/api/storage/screenshots/move-to-non-archive', photoIds);
  }
};