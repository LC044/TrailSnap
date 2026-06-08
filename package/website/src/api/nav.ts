import request from '@/utils/request'

export type NavEntityType = 'album' | 'person' | 'location' | 'classification'

export interface NavItemRef {
  entity_type: NavEntityType
  entity_id: string
}

export interface ResolvedNavItem {
  entity_type: string
  entity_id: string
  name: string
  cover_photo_id: string | null
  cover_photo_face_rect: number[] | null
  route_path: string
  photo_count: number
}

export interface NavItemsResponse {
  items: ResolvedNavItem[]
}

export const navApi = {
  async getItems(): Promise<NavItemsResponse> {
    const data = await request.get('/api/nav/items')
    return data.data
  },

  async updateItems(items: NavItemRef[]): Promise<NavItemsResponse> {
    const data = await request.put('/api/nav/items', { items })
    return data.data
  },

  async deleteItem(entityType: string, entityId: string): Promise<NavItemsResponse> {
    const data = await request.delete(`/api/nav/items/${entityType}/${encodeURIComponent(entityId)}`)
    return data.data
  }
}
