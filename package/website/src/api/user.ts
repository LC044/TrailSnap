import request from '@/utils/request';

export interface User {
  id: string
  username: string
  email: string
  nickname?: string
  avatar?: string
  is_active: boolean
  is_superuser: boolean
}

export interface CreateUserParams {
  username: string
  email: string
  password: string
  is_superuser?: boolean
}

export interface ResetPasswordParams {
  password: string
}

export const userService = {
  async getUsers(): Promise<User[]> {
    const data = await request.get<User[]>('/api/users/')
    return data.data
  },

  async createUser(params: CreateUserParams) {
    const data = await request.post<User>('/api/users/', params)
    return data.data
  },

  async resetPassword(userId: string, params: ResetPasswordParams) {
    const data = await request.put<User>(`/api/users/${userId}/password`, params)
    return data.data
  },

  async getCurrentUser() {
    const data = await request.get<User>('/api/users/me')
    return data.data
  },

  async updateCurrentUser(params: { nickname?: string, avatar?: string }) {
    const data = await request.put<User>('/api/users/me', params)
    return data.data
  },

  async deleteUser(userId: string) {
    const data = await request.delete<User>(`/api/users/${userId}`)
    return data.data
  }
}


