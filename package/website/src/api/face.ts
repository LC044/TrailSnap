import request from '@/utils/request';
import type { FaceIdentity } from '@/types/album';

export interface FaceRescanCandidate {
  face_id: number;
  photo_id: string;
  face_rect?: number[] | null;
  distance: number;
  confidence: number;
  recommended: boolean;
  current_identity_id?: string | null;
  current_identity_name?: string | null;
  assignment_type: 'unassigned' | 'reassign' | 'remove';
}

export interface FaceRescanPreview {
  status: string;
  reason?: string | null;
  reference_count: number;
  threshold: number;
  candidate_threshold: number;
  removal_threshold: number;
  add_candidates: FaceRescanCandidate[];
  remove_candidates: FaceRescanCandidate[];
  summary: { add_count: number; remove_count: number; reassign_count: number };
}

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

  async previewIdentityRescan(id: string) {
    const data = await request.post<FaceRescanPreview>(`/api/faces/identities/${id}/rescan/preview`);
    return data.data;
  },

  async applyIdentityRescan(id: string, selection: { add_face_ids: number[]; remove_face_ids: number[] }) {
    const data = await request.post(`/api/faces/identities/${id}/rescan/apply`, selection);
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
