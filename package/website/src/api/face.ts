import request from '@/utils/request';
import type { FaceIdentity } from '@/types/album';

export const faceApi = {
  async listIdentities(page = 1, limit = 20, types?: string[]) {
    const data = await request.get<FaceIdentity[]>('/api/faces/identities', {
      params: { skip: (page - 1) * limit, limit, types }
    });
    return data.data;
  },

  async getIdentityPhotos(id: string, page = 1, limit = 50) {
    const data = await request.get<any[]>(`/api/faces/identities/${id}/photos`, {
      params: { skip: (page - 1) * limit, limit }
    });
    return data.data;
  },

  async deleteIdentity(id: string) {
    const data = await request.delete(`/api/faces/identities/${id}`);
    return data.data;
  },

  async updateIdentity(id: string, data: { identity_name?: string; description?: string; tags?: string[]; is_hidden?: boolean }) {
    const res = await request.put<FaceIdentity>(`/api/faces/identities/${id}`, data);
    return res.data;
  },

  async rescanIdentity(id: string) {
    const data = await request.post(`/api/faces/identities/${id}/rescan`);
    return data.data;
  },

  async mergeIdentities(targetId: string, sourceIds: string[]) {
    const data = await request.post('/api/faces/identities/merge', {
      target_id: targetId,
      source_ids: sourceIds
    });
    return data.data;
  },

  async removePhotos(identityId: string, photoIds: string[]) {
    const data = await request.post(`/api/faces/identities/${identityId}/remove-photos`, {
      photo_ids: photoIds
    });
    return data.data;
  },

  async setCover(identityId: string, photoId: string) {
    const data = await request.put(`/api/faces/identities/${identityId}/cover`, {
      photo_id: photoId
    });
    return data.data;
  },

  async createIdentity(data: { identity_name: string; description?: string }) {
    const res = await request.post<FaceIdentity>('/api/faces/identities', data);
    return res.data;
  },

  async addPhotosToIdentity(id: string, photoIds: string[]) {
    const data = await request.post(`/api/faces/identities/${id}/add-photos`, {
      photo_ids: photoIds
    });
    return data.data;
  }
};
