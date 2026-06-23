import request from '@/utils/request';
import type { Photo } from '@/types/album';

export interface SearchResult {
  photo: Photo;
  score: number;
}

export interface SearchSuggestion {
  type: string;
  value: string;
  label: string;
}

export interface TextSearchRequest {
  text: string;
  limit?: number;
  skip?: number;
  threshold?: number;
  type?: string;
  start_time?: string;
  end_time?: string;
}

const searchService = {
  /**
   * Search photos by text
   */
  async searchByText(data: TextSearchRequest) {
    const res = await request.post<SearchResult[]>('/api/search/text', data, {
      timeout: 60000
    });
    return res.data;
  },

  /**
   * Get search suggestions
   */
  async getSuggestions(q: string) {
    const res = await request.get<SearchSuggestion[]>('/api/search/suggestions', {
      params: { q },
      timeout: 60000
    });
    return res.data;
  },
  
  /**
   * Search photos by image
   */
  async searchByImage(file: File, limit: number = 20, threshold: number = 0.0) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('limit', limit.toString());
    formData.append('threshold', threshold.toString());

    const res = await request.post<SearchResult[]>('/api/search/image', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      },
      timeout: 60000
    });
    return res.data;
  }
};

export default searchService;
