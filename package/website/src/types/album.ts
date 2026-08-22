// src/types/album.ts
// 定义相册相关的类型

export enum FileType {
  Image = 'image',
  Video = 'video',
  LivePhoto = 'live_photo'
}

export interface Tag {
  id: string;
  tag_name: string;
  confidence: number;
}

export interface PhotoMetadata {
  photo_id: string;
  file_path?: string;
  exif_info?: string;
  location?: any;
  address?: string;
  albums?: Album[];
  faces_identities?: FaceIdentity[];
  country?: string;
  province?: string;
  city?: string;
  district?: string;
  latitude?: number;
  longitude?: number;
  tags?: Tag[];
  make?: string;
  model?: string;
  shooting_params?: {
    f_number?: string;
    exposure_time?: string;
    iso?: string;
    [key: string]: any;
  };
}

export interface ImageDescription {
  id: string;
  photo_id: string;
  narrative?: string;
  caption?: string;
  [key: string]: any;
}

// 从后端返回的照片数据
export interface Photo {
  id: string;
  album_ids?: string[];
  filename?: string;
  photo_time: string;
  file_path?: string;
  url: string;
  thumbnail_url: string;
  file_type: FileType;
  upload_time: string;
  size: number;
  width?: number;
  height?: number;
  duration?: number;
  metadata_info?: PhotoMetadata;
  image_description?: ImageDescription;
  is_deleted?: boolean;
  deleted_at?: string;
}

export interface PhotoGroup {
  date: string;
  items: Photo[];
}

export interface TimelineItem {
  year: number;
  month: number;
  day: number;
  count: number;
}

export interface TimelineStats {
  total_photos: number;
  time_range: {
    start: string | null;
    end: string | null;
  };
  timeline: TimelineItem[];
}

// 前端使用的照片数据，包含了更多信息
export interface AlbumImage {
  id: string
  url: string
  thumbnail: string
  preview: string
  srcset: string
  timestamp: number
  /**
   * 该照片是否具有真实的 EXIF/拍摄时间。
   * true  → timestamp 来源于 photo_time（可作为「拍摄这一天」的可靠证据）
   * false → timestamp 来自 upload_time 或 Date.now() 兜底
   *          （不能用于依赖拍摄时间的后端任务，例如朋友圈 AI 文案）
   * 未提供时默认按 true 处理，保持向后兼容。
   */
  hasPhotoTime?: boolean
  albumIds: string[]
  width?: number
  height?: number
  size?: number
  filename?: string
  file_type: 'image' | 'video' | 'live_photo'
  file_path?: string
  duration?: string
  live_photo_video_url?: string
  has_live_video?: boolean
  deleted_at?: string
}

export interface AlbumCondition {
  time_range?: {
    start?: string;
    end?: string;
  };
  locations?: {
    province?: string;
    city?: string;
    district?: string;
  }[];
  people?: string[]; // Face Identity IDs
  folders?: string[]; // Relative folder paths; descendants are included
}

export interface ApiAlbum {
  id: string;
  name: string;
  create_time: string;
  description?: string;
  cover?: Photo;
  type: string;
  num_photos: number;
  photos?: Photo[];
  condition?: AlbumCondition;
  threshold?: number;
}

export interface Album {
  id: string
  title: string
  name: string
  type: string
  condition?: AlbumCondition
  threshold?: number
  cover: AlbumImage
  count: number
  description?: string
  createdAt: number
}

export interface CreateAlbumDto {
  name: string;
  description?: string;
  type?: string;
  condition?: AlbumCondition;
  threshold?: number;
}

export interface CoverPhotoInfo {
  photo_id: string
  face_rect: number[] | null,
  face_confidence: number | null,
  recognize_confidence: number | null,
}

export interface FaceIdentity {
  id: string
  identity_name: string
  description?: string
  tags?: string[]
  default_face_id: number | null
  face_count: number
  cover_photo: CoverPhotoInfo | null
  cover: Photo | null
  is_hidden?: boolean
}

export interface FilterOptions {
  years: number[];
  cities: string[];
  makes: string[];
  models: string[];
  image_types: string[];
  file_types: string[];
  uploaded_after?: string;
  uploaded_before?: string;
}

export interface SimilarPhoto {
  id: string;
  filename: string;
  photo_time: string;
  score: number;
  thumbnail_path: string;
  src: string;
}

export interface FilterState {
  years: number[];
  cities: string[];
  makes: string[];
  models: string[];
  image_types: string[];
  file_types: string[];
}
