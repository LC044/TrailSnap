import request from '@/utils/request';
import type { Location, Scene, SceneCreate, SceneUpdate, LocationStatistics, TimelineResponse, TrajectoryResponse } from '@/types/location';
import type { Photo } from '@/types/album';

export interface OverviewStats {
  total_distance_km: number;
  province_count: number;
  city_count: number;
  scene_count: number;
  travel_days: number;
  farthest_place: string | null;
  farthest_distance_km: number;
  has_location: boolean;
}

export interface AnnualTrendItem {
  year: number;
  photo_count: number;
  distance_km: number;
}

export interface MonthlyRadarItem {
  month: number;
  photo_count: number;
  activity_score: number;
}

export interface PlaceStats {
  name: string;
  level: string;
  photo_count: number;
  first_date: string | null;
  last_date: string | null;
  visit_count: number;
  visit_dates: string[];
}

export interface PlacesResponse {
  top_places: PlaceStats[];
  revisits: PlaceStats[];
}

export interface HeatmapItem {
  date: string;
  count: number;
}

export interface HeatmapRangeResponse {
  total_photos: number;
  total_days: number;
  data: HeatmapItem[];
}

export const locationService = {
  async getYears() {
    const data = await request.get<number[]>('/api/locations/years');
    return data.data;
  },

  async searchLocations(q: string) {
    const data = await request.get<{ label: string, value: { province?: string, city?: string, district?: string } }[]>('/api/locations/search', {
      params: { q }
    });
    return data.data;
  },

  async getLocations(level: 'city' | 'province' | 'district' | 'scene' = 'city', skip: number = 0, limit: number = 100, startDate?: string, endDate?: string) {
    const data = await request.get<Location[]>('/api/locations', {
      params: { level, skip, limit, start_date: startDate || undefined, end_date: endDate || undefined }
    });
    return data.data;
  },

  async getStatistics() {
    const data = await request.get<LocationStatistics>('/api/locations/statistics');
    return data.data;
  },

  async getDistribution(level: 'city' | 'province' | 'district' | 'scene' = 'city', startDate?: string, endDate?: string) {
    const data = await request.get<{name: string, count: number, level: string}[]>('/api/locations/distribution', {
      params: { level, start_date: startDate || undefined, end_date: endDate || undefined }
    });
    return data.data;
  },
  
  async getLocationPhotos(name: string, level: 'city' | 'province' | 'district' | 'scene' = 'city', skip: number = 0, limit: number = 50, startDate?: string, endDate?: string) {
    const data = await request.get<Photo[]>(`/api/locations/${name}/photos`, {
      params: { level, skip, limit, start_date: startDate || undefined, end_date: endDate || undefined }
    });
    return data.data;
  },

  async getTimelineNodes(skip: number = 0, limit: number = 100, startDate?: string, endDate?: string, level: string = 'city') {
    const data = await request.get<TimelineResponse>('/api/locations/timeline', {
      params: { skip, limit, start_date: startDate || undefined, end_date: endDate || undefined, level }
    });
    return data.data;
  },

  async getTrajectory(startDate: string, endDate: string, maxPoints: number = 360) {
    const response = await request.get<TrajectoryResponse>('/api/locations/trajectory', {
      params: { start_date: startDate, end_date: endDate, max_points: maxPoints }
    });
    return response.data;
  },

  async getMapMarkers(startDate?: string, endDate?: string) {
    const data = await request.get<{id: string, lat: number, lng: number}[]>('/api/locations/markers', {
      params: { start_date: startDate || undefined, end_date: endDate || undefined }
    });
    return data.data;
  },

  async getScene(id: string) {
    const data = await request.get<Scene>(`/api/locations/scenes/${id}`);
    return data.data;
  },

  async createScene(scene: SceneCreate) {
    const data = await request.post<Scene>('/api/locations/scenes', scene);
    return data.data;
  },

  async updateScene(id: string, scene: SceneUpdate) {
    const data = await request.put<Scene>(`/api/locations/scenes/${id}`, scene);
    return data.data;
  },

  async getScenesList(skip: number = 0, limit: number = 100, startDate?: string, endDate?: string) {
    const data = await request.get<Scene[]>('/api/locations/scenes/list', {
      params: { skip, limit, start_date: startDate || undefined, end_date: endDate || undefined }
    });
    return data.data;
  },

  async deleteScene(id: string) {
    const data = await request.delete(`/api/locations/scenes/${id}`);
    return data.data;
  },

  async getOverview(startDate?: string, endDate?: string) {
    const data = await request.get<OverviewStats>('/api/location-stats/overview', {
      params: { start_date: startDate || undefined, end_date: endDate || undefined }
    });
    return data.data;
  },

  async getAnnualTrend(startDate?: string, endDate?: string) {
    const data = await request.get<AnnualTrendItem[]>('/api/location-stats/annual-trend', {
      params: { start_date: startDate || undefined, end_date: endDate || undefined }
    });
    return data.data;
  },

  async getMonthlyRadar(startDate?: string, endDate?: string) {
    const data = await request.get<MonthlyRadarItem[]>('/api/location-stats/monthly-radar', {
      params: { start_date: startDate || undefined, end_date: endDate || undefined }
    });
    return data.data;
  },

  async getPlaces(level: string = 'city', startDate?: string, endDate?: string, parentRegion?: string, limit: number = 10) {
    const data = await request.get<PlacesResponse>('/api/location-stats/places', {
      params: { level, start_date: startDate || undefined, end_date: endDate || undefined, parent_region: parentRegion || undefined, limit }
    });
    return data.data;
  },

  async getHeatmapRange(startDate?: string, endDate?: string) {
    const data = await request.get<HeatmapRangeResponse>('/api/location-stats/heatmap', {
      params: { start_date: startDate || undefined, end_date: endDate || undefined }
    });
    return data.data;
  }
};
