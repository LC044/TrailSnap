import request from '@/utils/request';
import type { Photo } from '@/types/album';

export interface TagStats {
  id: string
  tag_name: string
  type?: string
  count: number
  cover: Photo | null
}

export interface ClipCategory {
  id: string
  tag_id: string
  name: string
  groups: string[]
  enabled: boolean
  revision: number
  descriptions: string[]
  strictness: 'relaxed' | 'standard' | 'strict'
  thresholds: Record<string, number>
  builtin: boolean
  count: number
  calibration: { status: string; reviewed?: number }
}

export type ClipRuleDraft = Omit<ClipCategory, 'id' | 'tag_id' | 'builtin' | 'count' | 'calibration'> & { apply_history?: boolean }
export interface ClipPreview {
  model: string
  threshold: number
  checked: number
  available: number
  missing: number
  matched_count: number
  matches: { photo: Photo; score: number; matched: boolean }[]
  boundary: { photo: Photo; score: number; matched: boolean }[]
}

export const clipClassificationService = {
  async list() {
    return (await request.get<{ groups: string[]; categories: ClipCategory[] }>('/api/tags/clip/categories')).data
  },
  async save(id: string | undefined, draft: ClipRuleDraft) {
    return (id ? await request.put<ClipCategory>(`/api/tags/clip/categories/${id}`, draft)
      : await request.post<ClipCategory>('/api/tags/clip/categories', draft)).data
  },
  async preview(draft: ClipRuleDraft) {
    return (await request.post<ClipPreview>('/api/tags/clip/preview', draft, { timeout: 180000 })).data
  },
  async rebuild(category_ids?: string[]) {
    return (await request.post<{ task_id: string }>('/api/tags/clip/rebuild', { category_ids })).data
  },
  async enable(category_ids: string[], enabled: boolean) {
    return (await request.post<{ updated: number }>('/api/tags/clip/enable', { category_ids, enabled })).data
  },
  async remove(id: string) { await request.delete(`/api/tags/clip/categories/${id}`) },
}

export const classificationService = {
  async getTags(skip: number = 0, limit: number = 500) {
    const data = await request.get<TagStats[]>('/api/tags', {
      params: { skip, limit }
    });
    return data.data;
  },
  
  async getTagPhotos(name: string, skip: number = 0, limit: number = 50, tagId?: string) {
    const data = await request.get<Photo[]>(`/api/tags/${encodeURIComponent(name)}/photos`, {
      params: { skip, limit, tag_id: tagId }
    });
    return data.data;
  },

  async removePhotosFromTag(tagName: string, photoIds: string[], tagId?: string) {
    const data = await request.post(`/api/tags/${encodeURIComponent(tagName)}/remove-photos`, {
      photo_ids: photoIds
    }, { params: { tag_id: tagId } });
    return data.data;
  },

  async setCover(tagName: string, photoId: string, tagId?: string) {
    const data = await request.post(`/api/tags/${encodeURIComponent(tagName)}/cover`, {
      photo_id: photoId
    }, { params: { tag_id: tagId } });
    return data.data;
  },

  async deleteTag(tagName: string) {
      await request.delete(`/api/tags/${tagName}`);
  },

  async renameTag(oldName: string, newName: string) {
      const data = await request.put(`/api/tags/${oldName}`, { new_name: newName });
      return data.data;
  },

  async mergeTags(targetName: string, sourceNames: string[]) {
      const data = await request.post('/api/tags/merge', {
          target_name: targetName,
          source_names: sourceNames
      });
      return data.data;
  }
};
