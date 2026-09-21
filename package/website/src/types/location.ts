import type { Photo } from './album'

export interface Location {
  id?: string
  is_custom?: boolean
  name: string
  level: 'city' | 'province' | 'district' | 'scene'
  count: number
  cover: Photo | null
}

export interface LocationStatistics {
  province_count: number
  city_count: number
  district_count: number
  country_count: number
}

export interface Scene {
  id: string
  is_custom: boolean
  name: string
  description?: string
  level?: number
  address?: string
  latitude?: number
  longitude?: number
  radius?: number
  polygon?: number[][]
  photo_count?: number
  cover?: Photo | null
}

export interface SceneCreate {
  name: string
  description?: string
  level?: number
  address?: string
  latitude?: number
  longitude?: number
  radius?: number
  polygon?: number[][]
}

export interface SceneUpdate extends SceneCreate {}

export interface TimelineNode {
  type: string;
  startDate: string; // YYYY-MM-DD
  endDate: string; // YYYY-MM-DD
  locationName: string;
  level?: string; // Added level
  lat?: number;
  lng?: number;
  photoCount: number;
  coverId?: string;
  startTime?: string;
  endTime?: string;
}

export interface TimelineResponse {
  nodes: TimelineNode[];
  total: number;
}

export interface TimeCompareYear {
  year: number
  photo_count: number
  first_date: string
  last_date: string
  cover: Photo
}

export interface TimeCompareVisit {
  date: string
  photo_count: number
  first_time: string
  last_time: string
  cover: Photo
}

export interface TimeCompareSummary {
  eligible: boolean
  reason?: 'precise_location_required' | 'multiple_years_required' | string
  match_type?: 'scene' | 'nearby_gps' | string
  radius_m?: number
  visual_similarity?: number
  scene_id?: string
  location_name?: string
  location_address?: string
  city?: string
  source_photo_id?: string
  source_photo_year?: number
  years: TimeCompareYear[]
  visits: TimeCompareVisit[]
  first_photo?: Photo
  latest_photo?: Photo
}

export interface TrajectoryPoint {
  photoId: string;
  capturedAt: string;
  endAt?: string;
  lat: number;
  lng: number;
  photoCount: number;
  coverId?: string;
  locationName: string;
  level: string;
}

export interface TrajectoryResponse {
  points: TrajectoryPoint[];
  totalPhotos: number;
  sampled: boolean;
}
