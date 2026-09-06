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
