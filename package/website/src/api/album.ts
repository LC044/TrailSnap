import request from '@/utils/request';
import type { ApiAlbum, Album, CreateAlbumDto, Photo, PhotoMetadata, TimelineStats, PhotoGroup, FilterOptions } from '@/types/album';

export const albumService = {
  // Albums
  async getAlbums() {
    const data = await request.get<ApiAlbum[]>('/api/albums');
    return data.data;
  },
  async getAlbum(id: string) {
    const data = await request.get<ApiAlbum>(`/api/albums/${id}`);
    return data.data;
  },
  async createAlbum(album: CreateAlbumDto) {
    const data = await request.post<ApiAlbum>('/api/albums', album);
    return data.data;
  },
  async updateAlbum(id: string, album: CreateAlbumDto) {
    const data = await request.put<ApiAlbum>(`/api/albums/${id}`, album);
    return data.data;
  },
  async setAlbumCover(id: string, photoId: string) {
    const data = await request.put<ApiAlbum>(`/api/albums/${id}/cover`, { photo_id: photoId })
    return data.data
  },
  async deleteAlbum(id: string) {
    await request.delete(`/api/albums/${id}`);
  },

  // Stats
  async getTimelineStats(albumId?: string, filters?: any) {
    const data = await request.get<TimelineStats>('/api/stats/timeline', {
      params: { album_id: albumId, ...filters }
    });
    return data.data;
  },

  async getFilterOptions() {
      const data = await request.get<FilterOptions>('/api/stats/filters');
      return data.data;
  },

  // Folders（按层级浏览，Issue #78）：parent 为相对父路径，空字符串为根层
  async getFolders(parent: string = '') {
    const data = await request.get<{
      parent: string
      breadcrumb: { name: string; path: string }[]
      own_count: number
      children: { name: string; path: string; count: number; has_children: boolean }[]
    }>('/api/photos/folders', { params: { parent } });
    return data.data;
  },

  // Photos
  async getAllPhotos(skip: number = 0, limit: number = 100, filters?: any) {
    const data = await request.get<Photo[]>('/api/photos', {
      params: { skip, limit, ...filters }
    });
    return data.data;
  },

  async getPhotosByIds(ids: string[]) {
    // Chunk requests to avoid URL length limits
    const chunks = [];
    const chunkSize = 40; // Conservative chunk size
    for (let i = 0; i < ids.length; i += chunkSize) {
        chunks.push(ids.slice(i, i + chunkSize));
    }
    
    const results = await Promise.all(chunks.map(async chunk => {
        // paramsSerializer is handled by default request configuration
        const data = await request.get<Photo[]>('/api/photos', {
          params: { ids: chunk }
        });
        return data.data;
    }));
    return results.flat();
  },

  async getPhotos(albumId: string, skip: number = 0, limit: number = 100, filters?: { start_time?: string, end_time?: string }) {
    const data = await request.get<Photo[]>(`/api/albums/${albumId}/photos`, {
      params: { skip, limit, ...filters }
    });
    return data.data;
  },

  // Remove photo from specific album (Association)
  async removePhotoFromAlbum(albumId: string, photoId: string) {
    await request.delete(`/api/albums/${albumId}/photos/${photoId}`);
  },

  // Delete photo globally
  async deletePhoto(photoId: string) {
    await request.delete(`/api/photos/${photoId}`);
  },

  async updatePhoto(photoId: string, photo: Partial<Photo> & { modify_original_file?: boolean }) {
    const data = await request.put<Photo>(`/api/photos/${photoId}`, photo);
    return data.data;
  },

  // Batch Update
  async batchUpdatePhotos(data: { photo_ids: string[], action: 'add_tags' | 'remove_tags' | 'add_to_album' | 'remove_from_album' | 'delete', album_id?: string }) {
      const res = await request.post<{count: number}>('/api/photos/batch', data);
      return res;
  },

  // Upload (Simple)
  async uploadPhoto(file: File, albumId?: string) {
    const formData = new FormData();
    formData.append('file', file);
    if (albumId) {
        formData.append('album_id', albumId);
    }
    const data = await request.post<Photo>('/api/medias', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
    });
    return data.data;
  },

  // Replace photo file
  async replacePhotoFile(photoId: string, file: File, filename: string) {
    const formData = new FormData();
    formData.append('file', file, filename);
    const data = await request.put<Photo>(`/api/photos/${photoId}/file`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
    });
    return data.data;
  },

  // Chunk Upload
  async initUpload() {
      const data = await request.post<{upload_id: string}>('/api/medias/upload/init');
      return data.data.upload_id;
  },

  async uploadChunk(uploadId: string, chunkIndex: number, chunk: Blob) {
      const formData = new FormData();
      formData.append('upload_id', uploadId);
      formData.append('chunk_index', chunkIndex.toString());
      formData.append('file', chunk);
      await request.post('/api/medias/upload/chunk', formData);
  },

  async finishUpload(uploadId: string, fileName: string, albumId?: string) {
      const formData = new FormData();
      formData.append('upload_id', uploadId);
      formData.append('file_name', fileName);
      if (albumId) {
          formData.append('album_id', albumId);
      }
      const data = await request.post<Photo>('/api/medias/upload/finish', formData);
      return data.data;
  },

  // Metadata
  // Note: Using the generic endpoint if available or falling back to album-specific
  // Ideally backend should provide /api/photos/{id}/metadata
  async getMetadata(photoId: string) {
      const url = `/api/metadata?photo_id=${photoId}`; // Assuming this exists or will exist
      const data = await request.get<PhotoMetadata>(url);
      return data.data;
  },
  
  async updateMetadata(photoId: string, metadata: Partial<PhotoMetadata>) {
      const url = `/api/metadata?photo_id=${photoId}`;
      const data = await request.put<PhotoMetadata>(url, metadata);
      return data.data;
  },

  async batchUpdateLocation(photoIds: string[], lat: number, lng: number, formattedAddress?: string, locationDetail?: { province?: string; city?: string; district?: string; country?: string }) {
      const data = await request.post<{message: string, count: number}>('/api/metadata/batch-location', {
          photo_ids: photoIds,
          latitude: lat,
          longitude: lng,
          formatted_address: formattedAddress,
          province: locationDetail?.province,
          city: locationDetail?.city,
          district: locationDetail?.district,
          country: locationDetail?.country
      });
      return data.data;
  },

  async getThumbnail(photoId: string) {
    const data = await request.get<{ thumbnail: string }>(`/api/medias/${photoId}/thumbnail`);
  },

  // Tags
  async getPhotoTags(photoId: string) {
    const data = await request.get<{id: string, tag_name: string, confidence: number}[]>(`/api/photos/${photoId}/tags`);
    return data.data;
  },

  async addPhotoTag(photoId: string, tagName: string, confidence: number = 1.0) {
    const data = await request.post<{id: string, tag_name: string, confidence: number}>(`/api/photos/${photoId}/tags`, {
      tag_name: tagName,
      confidence
    });
    return data.data;
  },

  async deletePhotoTag(photoId: string, tagId: string) {
    await request.delete(`/api/photos/${photoId}/tags/${tagId}`);
  },

  async getImageDescription(photoId: string) {
      const data = await request.get<any>(`/api/photos/${photoId}/description`);
      return data.data;
  }
  
};
