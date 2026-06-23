import request from '@/utils/request';
import type { FaceIdentity, CoverPhotoInfo } from '@/types/album'

export interface DashboardCard {
  total_media: number;
  today_new: number;
  storage_used: string;
}

export interface DashboardFaceItem {
  id: string;
  name: string;
  count: number;
  avatar_url?: string;
}

export interface DashboardFace {
  total_identified: number;
  top_faces: FaceIdentity[];
  pending_faces_count: number;
  unidentified_photos_count: number;
}

export interface ContentDetail {
  total: number;
  sub_1_label: string;
  sub_1_count: number;
  sub_2_label: string;
  sub_2_count: number;
}

export interface DashboardContentStats {
  photos: ContentDetail;
  videos: ContentDetail;
  scenery_count: number;
  food_count: number;
}

export interface DashboardTimeChartItem {
  year: number;
  count: number;
  percentage: number;
  color: string;
}

export interface DashboardTime {
  current_year_percentage: number;
  chart_data: DashboardTimeChartItem[];
  monthly_peak: string;
}

export interface DashboardResponse {
  card: DashboardCard;
  face: DashboardFace;
  content: DashboardContentStats;
  time: DashboardTime;
}

export interface HeatmapItem {
  date: string;
  count: number;
}

export interface HeatmapResponse {
  total_photos: number;
  total_days: number;
  max_consecutive_days: number;
  data: HeatmapItem[];
  available_years: number[];
}

export interface EmotionCalendarItem {
  date: string;
  photo_count: number;
  dominant_color: string | null;
  brightness: number | null;
  saturation: number | null;
  top_categories: string[];
  emotion_hint: string | null;
}

export interface EmotionCalendarResponse {
  total_photos: number;
  total_days: number;
  data: EmotionCalendarItem[];
  available_years: number[];
}

export const dashboardApi = {
  async getOverview() {
    const data = await request.get<DashboardResponse>('/api/stats/dashboard');
    return data.data;
  },

  async getHeatmap(year?: number) {
    const data = await request.get<HeatmapResponse>('/api/stats/heatmap', { params: { year } });
    return data.data;
  },

  async getEmotionCalendar(year?: number) {
    const data = await request.get<EmotionCalendarResponse>('/api/stats/emotion-calendar', { params: { year } });
    return data.data;
  }
};
