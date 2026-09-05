import request from '@/utils/request';

export interface AgentToken {
  id: string
  user_id: string
  name: string
  token: string
  created_at: string
  expires_at: string
  scopes: AgentTokenScope[]
  is_deleted: boolean
}

export type AgentTokenScope = 'photos:read' | 'albums:read' | 'people:read'

export interface CreateTokenData {
  name: string
  expires_at: string
  password: string
  scopes: AgentTokenScope[]
}

export function getTokens() {
  return request<AgentToken[]>({
    url: '/api/tokens',
    method: 'get'
  })
}

export function createToken(data: CreateTokenData) {
  return request<AgentToken>({
    url: '/api/tokens',
    method: 'post',
    data
  })
}

export function deleteToken(id: string) {
  return request({
    url: `/api/tokens/${id}`,
    method: 'delete'
  })
}
