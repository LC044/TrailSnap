import request from '@/utils/request';
import type { FaceIdentity, GroupAlbumItem } from '@/types/album';

export interface PhotoFace {
  id: number;
  photo_id: string;
  face_rect: number[] | null;
  identity_id: string | null;
  identity_name: string | null;
}

export type SimilarFaceScope = 'all' | 'current' | 'current_low' | 'other' | 'unassigned';
export type SimilarFaceMatch = 'strict' | 'balanced' | 'broad';

export interface SimilarFaceCandidate extends PhotoFace {
  photo_time: string | null;
  similarity: number;
  manually_confirmed: boolean;
  review_token: string;
}

export interface SimilarFacesResult {
  reference: SimilarFaceCandidate;
  items: SimilarFaceCandidate[];
  face_count: number;
  photo_count: number;
  has_more: boolean;
}

export interface BatchFaceAssignmentResult {
  face_count: number;
  photo_ids: string[];
  undo_token: string | null;
}

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

export interface FaceClusteringStatus {
  phase: 'initializing' | 'ready' | 'resetting' | 'failed';
  checkpoint?: number;
  error?: string;
}

export const faceApi = {
  async retryClustering(): Promise<FaceClusteringStatus> {
    const response = await request.post('/api/faces/clustering/retry');
    return response.data;
  },

  async clusteringStatus(): Promise<FaceClusteringStatus> {
    const response = await request.get('/api/faces/clustering/status');
    return response.data;
  },

  async resetClustering(requestId: string): Promise<FaceClusteringStatus> {
    const response = await request.post('/api/faces/clustering/reset', { request_id: requestId });
    return response.data;
  },

  async getPhotoFaces(photoId: string) {
    const res = await request.get<PhotoFace[]>(`/api/faces/photos/${photoId}`);
    return res.data;
  },

  async assignPhotoFace(photoId: string, faceId: number, identityId: string | null) {
    const res = await request.put(`/api/faces/photos/${photoId}/${faceId}/identity`, { identity_id: identityId });
    return res.data;
  },

  async searchSimilarFaces(photoId: string, faceId: number, params: {
    scope: SimilarFaceScope; match: SimilarFaceMatch; skip: number; limit: number;
    exclude_identity_id?: string;
    threshold?: number;
    include_confirmed?: boolean;
  }, signal?: AbortSignal) {
    const res = await request.get<SimilarFacesResult>(`/api/faces/photos/${photoId}/${faceId}/similar`, {
      params, signal, silentError: true,
    });
    return res.data;
  },

  async assignSimilarFaces(photoId: string, faceId: number, identityId: string | null, items: SimilarFaceCandidate[]) {
    const res = await request.post<BatchFaceAssignmentResult>(`/api/faces/photos/${photoId}/${faceId}/similar/assign`, {
      identity_id: identityId,
      selections: items.map(item => ({ face_id: item.id, review_token: item.review_token })),
    }, { silentError: true });
    return res.data;
  },

  async undoFaceAssignment(undoToken: string) {
    const res = await request.post<BatchFaceAssignmentResult>('/api/faces/assignments/undo', {
      undo_token: undoToken,
    }, { silentError: true });
    return res.data;
  },

  async listIdentities(page = 1, limit = 20, types?: string[], minPhotos?: number) {
    const data = await request.get<FaceIdentity[]>('/api/faces/identities', {
      params: { skip: (page - 1) * limit, limit, types, min_photos: minPhotos }
    });
    return data.data;
  },

  async getIdentityPhotos(id: string, page = 1, limit = 50) {
    const data = await request.get<any[]>(`/api/faces/identities/${id}/photos`, {
      params: { skip: (page - 1) * limit, limit }
    });
    return data.data;
  },

  async listGroupAlbums() {
    const data = await request.get<GroupAlbumItem[]>('/api/faces/group-albums');
    return data.data;
  },

  async getGroupAlbumPhotos(identityIds: string[], page = 1, limit = 500) {
    const data = await request.get<any[]>('/api/faces/group-albums/photos', {
      params: { identity_ids: identityIds, skip: (page - 1) * limit, limit }
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

  async previewIdentityRescan(id: string, threshold?: number, signal?: AbortSignal) {
    const data = await request.post<FaceRescanPreview>(`/api/faces/identities/${id}/rescan/preview`, undefined, {
      params: { threshold }, signal, silentError: true,
    });
    return data.data;
  },

  async applyIdentityRescan(id: string, selection: { add_face_ids: number[]; remove_face_ids: number[]; threshold?: number }) {
    const data = await request.post(`/api/faces/identities/${id}/rescan/apply`, selection);
    return data.data;
  },

  async mergeIdentities(targetId: string, sourceIds: string[], identityName?: string) {
    const data = await request.post('/api/faces/identities/merge', {
      target_id: targetId,
      source_ids: sourceIds,
      identity_name: identityName
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
