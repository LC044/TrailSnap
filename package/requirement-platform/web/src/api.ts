import axios from 'axios'

export type User = { id: string; username: string; email: string; role: 'viewer' | 'admin' | 'owner'; is_active: boolean }
export type Requirement = {
  id: string; type: string; title: string; description: string; current_behavior?: string; expected_behavior?: string
  steps_to_reproduce?: string; severity: string; product_version?: string; environment: Record<string, unknown>
  visibility: string; status: string; priority: string; risk_level: string; review_reason?: string
  duplicate_of_id?: string; github_issue_number?: number; github_issue_url?: string; github_state?: string
  created_by: string; created_at: string; updated_at: string; follower_count: number; triage?: Record<string, unknown>
}
export type BatchItem = { id: string; requirement_id: string; priority_order: number; delivery_status: string; requirement_snapshot: Record<string, unknown> }
export type Batch = {
  id: string; name: string; version_name: string; batch_type: string; goal: string; status: string; target_date?: string
  max_risk_level: string; github_milestone_number?: number; github_milestone_url?: string; items: BatchItem[]
}

const client = axios.create({ baseURL: import.meta.env.VITE_REQUIREMENT_API_URL || '/api', timeout: 20000 })
client.interceptors.request.use(config => {
  const token = localStorage.getItem('rp_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

async function call<T>(method: string, url: string, data?: unknown): Promise<T> {
  const response = await client.request({ method, url, data })
  return response.data.data as T
}

export const api = {
  register: (data: { username: string; email: string; password: string }) => call<{ token: string; user: User }>('post', '/auth/register', data),
  login: (data: { identifier: string; password: string }) => call<{ token: string; user: User }>('post', '/auth/login', data),
  me: () => call<User>('get', '/auth/me'),
  requirements: (params = '') => call<Requirement[]>('get', `/requirements${params}`),
  createRequirement: (data: unknown) => call<Requirement>('post', '/requirements', data),
  updateRequirement: (id: string, data: unknown) => call<Requirement>('patch', `/requirements/${id}`, data),
  withdrawRequirement: (id: string) => call<Requirement>('post', `/requirements/${id}/withdraw`),
  followRequirement: (id: string) => call<{ following: boolean }>('post', `/requirements/${id}/follow`),
  triage: (id: string) => call<{ job_id: string }>('post', `/requirements/${id}/triage`),
  review: (id: string, data: unknown) => call<Requirement>('post', `/requirements/${id}/review`, data),
  batches: () => call<Batch[]>('get', '/versions'),
  createBatch: (data: unknown) => call<Batch>('post', '/versions', data),
  addBatchItem: (batchId: string, requirementId: string) => call<Batch>('post', `/versions/${batchId}/items`, { requirement_id: requirementId }),
  removeBatchItem: (batchId: string, itemId: string) => call<{ removed: boolean }>('delete', `/versions/${batchId}/items/${itemId}`),
  lockBatch: (batchId: string) => call<Batch>('post', `/versions/${batchId}/lock`),
  updateBatchStatus: (batchId: string, status: string, reason: string) => call<Batch>('patch', `/versions/${batchId}/status`, { status, reason }),
  updateDeliveryStatus: (batchId: string, itemId: string, status: string) => call('patch', `/versions/${batchId}/items/${itemId}/status`, { status }),
  users: () => call<User[]>('get', '/admin/users'),
  updateRole: (id: string, role: 'viewer' | 'admin') => call<User>('patch', `/admin/users/${id}/role`, { role }),
}
