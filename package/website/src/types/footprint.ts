export type FootprintMode = '2d' | '3d' | 'globe'

export interface FootprintCity {
  id: string
  name: string
  province: string | null
  country: string | null
  lat: number
  lng: number
  photo_count: number
  visit_count: number
  cover_id: string | null
  first_at: string | null
  last_at: string | null
}

export interface FootprintRoute {
  id: string
  from: [number, number]
  to: [number, number]
  from_name: string
  to_name: string
  start_at: string
  end_at: string
  photo_count: number
}

export interface FootprintData {
  years: number[]
  summary: {
    photo_count: number
    gps_photo_count: number
    province_count: number
    city_count: number
    country_count: number
    visit_count: number
  }
  cities: FootprintCity[]
  routes: FootprintRoute[]
  timeline: { year: number; photo_count: number; city_count: number }[]
  sampled: boolean
}

export interface FootprintLayers {
  photos: boolean
  routes: boolean
  heatmap: boolean
  boundaries: boolean
  terrain: boolean
}
