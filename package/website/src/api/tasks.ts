import request from '@/utils/request';

export interface Task {
  id: string
  type: string
  status: string
  priority: number
  created_at: string
  updated_at?: string
  error?: string
  payload?: any
  total_items?: number
  processed_items?: number
  result?: any
  owner_id?: string | null
}

const SSE_BASE = (import.meta.env.VITE_API_BASE_URL ?? '') || '';

/**
 * Build the URL for the task-event SSE stream. EventSource cannot set
 * headers, so we pass the JWT as a query param. The backend accepts both
 * `Authorization: Bearer <token>` and `?token=<token>`.
 */
export function buildTaskEventsUrl(token: string | null | undefined): string {
  const base = SSE_BASE || '';
  const params = new URLSearchParams();
  if (token) params.set('token', token);
  const qs = params.toString();
  return `${base}/api/tasks/events${qs ? '?' + qs : ''}`;
}

export const tasksApi = {
  async listTasks(status?: string, type?: string, limit = 50) {
    const params: any = { status, type, limit }
    const data = await request.get<Task[]>('/api/tasks/', { params })
    return data.data
  },

  async getTask(taskId: string) {
    const data = await request.get<Task>(`/api/tasks/${taskId}`)
    return data.data
  },

  async createTask(type: string, payload: any = {}) {
    const data = await request.post<Task>('/api/tasks/', { type, payload })
    return data.data
  },

  async cancelTask(taskId: string) {
    const data = await request.post<Task>(`/api/tasks/${taskId}/cancel`)
    return data.data
  },

  async retryTask(taskId: string) {
    const data = await request.post<Task>(`/api/tasks/${taskId}/retry`)
    return data.data
  },

  async retryAllFailedTasks(types?: string[]) {
    const params: any = {}
    if (types && types.length > 0) {
        params.types = types
    }
    const data = await request.post<{ message: string, count: number }>('/api/tasks/retry-all-failed', null, {
        params
    })
    return data.data
  },

  async deleteFailedTasks(types?: string[]) {
    const params: any = {}
    if (types && types.length > 0) {
        params.types = types
    }
    const data = await request.delete<{ message: string, count: number }>('/api/tasks/failed', {
        params
    })
    return data.data
  },

  async getTaskStats() {
    const data = await request.get<{ failed_process_tasks: number }>('/api/tasks/stats')
    return data.data
  },

  async getGroupedStatus() {
    const data = await request.get<any[]>('/api/tasks/grouped-status')
    return data.data
  },

  async pauseCategory(category: string) {
    const data = await request.post(`/api/tasks/categories/${category}/pause`)
    return data.data
  },

  async resumeCategory(category: string) {
    const data = await request.post(`/api/tasks/categories/${category}/resume`)
    return data.data
  },

  async toggleFastMode(enabled: boolean) {
    const data = await request.post('/api/tasks/fast-mode', { enabled })
    return data.data
  },

  async getGlobalStatus() {
      const data = await request.get('/api/tasks/status')
      return data.data
  },

  /** Fetch tasks updated after a given ISO timestamp (SSE catch-up). */
  async fetchRecent(since: string, limit = 100, token?: string | null) {
    const params: any = { since, limit }
    if (token) params.token = token
    const data = await request.get<Task[]>('/api/tasks/recent', { params })
    return data.data
  },
}