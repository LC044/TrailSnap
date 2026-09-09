import axios from 'axios'

export type GitHubIdentity = { github_user_id: number; login: string; avatar_url?: string; profile_url?: string; email?: string; linked_at: string; last_login_at?: string }
export type GitHubPullRequest = { number: number; title: string; url: string; state: 'open' | 'closed' | 'merged'; draft: boolean; merged_at?: string; updated_at?: string }
export type User = { id: string; username: string; email: string; role: 'viewer' | 'admin' | 'owner'; is_active: boolean; github?: GitHubIdentity }
export type AgentToken = { id: string; name: string; token_prefix: string; scopes: string[]; expires_at?: string; last_used_at?: string; revoked_at?: string; created_at: string }
export type Requirement = {
  id: string; public_number?: number; type: string; title: string; description: string; log_text?: string; current_behavior?: string; expected_behavior?: string
  steps_to_reproduce?: string; severity: string; product_version?: string; environment: Record<string, unknown>
  visibility: string; status: string; priority: string; risk_level: string; review_reason?: string
  duplicate_of_id?: string; github_issue_number?: number; github_issue_url?: string; github_state?: string
  github_pull_requests: GitHubPullRequest[]
  created_by?: string; created_by_name?: string; submitter_name?: string; submitter_contact?: string; upload_token?: string
  created_at: string; updated_at: string; follower_count: number; triage?: Record<string, unknown>
  deleted_at?: string; deleted_by?: string; delete_reason?: string; source: 'platform' | 'github'
  attachments?: Array<{ id: string; name: string; content_type: string; size_bytes: number; kind: string; download_url: string }>
}
export type BatchItem = { id: string; requirement_id: string; priority_order: number; delivery_status: string; requirement_snapshot: Record<string, unknown> }
export type Batch = {
  id: string; name: string; version_name: string; batch_type: string; goal: string; status: string; target_date?: string
  max_risk_level: string; github_milestone_number?: number; github_milestone_url?: string; items: BatchItem[]
}
export type RequirementHistory = { id: string; action: string; actor_name: string; before?: string; after?: string; reason?: string; created_at: string }
export type Dashboard = { total: number; new_last_7_days: number; pending_review: number; in_progress: number; github_linked: number; anonymous: number; by_status: Record<string, number>; by_type: Record<string, number> }

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
  authStatus: () => call<{ has_owner: boolean; allow_registration: boolean; github_oauth_enabled: boolean }>('get', '/auth/status'),
  githubStart: (mode: 'login' | 'link') => call<{ authorize_url: string }>('get', `/auth/github/start?mode=${mode}`),
  githubRedeem: (grant: string) => call<{ token: string; user: User }>('post', '/auth/github/redeem', { grant }),
  githubUnlink: () => call<{ unlinked: boolean }>('delete', '/auth/github/link'),
  requirements: (params = '') => call<Requirement[]>('get', `/requirements${params}`),
  createRequirement: (data: unknown) => call<Requirement>('post', '/requirements', data),
  uploadAttachment: (id: string, file: File, uploadToken?: string) => {
    const data = new FormData(); data.append('file', file)
    return client.post(`/requirements/${id}/attachments`, data, {
      headers: uploadToken ? { 'X-Requirement-Upload-Token': uploadToken } : undefined,
    }).then(response => response.data.data as { id: string; name: string })
  },
  requirementByNumber: (number: number) => call<Requirement>('get', `/requirements/number/${number}`),
  requirementHistory: (id: string) => call<RequirementHistory[]>('get', `/requirements/${id}/history`),
  downloadAttachment: async (requirementId: string, attachmentId: string, name: string) => {
    const response = await client.get(`/requirements/${requirementId}/attachments/${attachmentId}`, { responseType: 'blob' })
    const url = URL.createObjectURL(response.data)
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = name; anchor.click()
    URL.revokeObjectURL(url)
  },
  updateRequirement: (id: string, data: unknown) => call<Requirement>('patch', `/requirements/${id}`, data),
  withdrawRequirement: (id: string) => call<Requirement>('post', `/requirements/${id}/withdraw`),
  followRequirement: (id: string) => call<{ following: boolean }>('post', `/requirements/${id}/follow`),
  triage: (id: string) => call<{ job_id: string }>('post', `/requirements/${id}/triage`),
  review: (id: string, data: unknown) => call<Requirement>('post', `/requirements/${id}/review`, data),
  closeRequirement: (id: string, reason: string) => call<Requirement>('post', `/requirements/${id}/close`, { reason }),
  deleteRequirement: (id: string, reason: string) => call<{ deleted: boolean }>('delete', `/requirements/${id}`, { reason }),
  restoreRequirement: (id: string) => call<Requirement>('post', `/requirements/${id}/restore`),
  createGithubIssue: (id: string) => call<Requirement>('post', `/requirements/${id}/github/create`),
  linkGithubIssue: (id: string, issue_number: number) => call<Requirement>('post', `/requirements/${id}/github/link`, { issue_number }),
  unlinkGithubIssue: (id: string) => call<Requirement>('delete', `/requirements/${id}/github/link`),
  closeGithubIssue: (id: string, reason: string) => call<Requirement>('post', `/requirements/${id}/github/close`, { reason }),
  syncGithubIssues: () => call<{ created: number; updated: number; skipped: number; total: number }>('post', '/admin/github/issues/sync'),
  dashboard: () => call<Dashboard>('get', '/admin/dashboard'),
  batches: () => call<Batch[]>('get', '/versions'),
  createBatch: (data: unknown) => call<Batch>('post', '/versions', data),
  addBatchItem: (batchId: string, requirementId: string) => call<Batch>('post', `/versions/${batchId}/items`, { requirement_id: requirementId }),
  removeBatchItem: (batchId: string, itemId: string) => call<{ removed: boolean }>('delete', `/versions/${batchId}/items/${itemId}`),
  lockBatch: (batchId: string) => call<Batch>('post', `/versions/${batchId}/lock`),
  updateBatchStatus: (batchId: string, status: string, reason: string) => call<Batch>('patch', `/versions/${batchId}/status`, { status, reason }),
  updateDeliveryStatus: (batchId: string, itemId: string, status: string) => call('patch', `/versions/${batchId}/items/${itemId}/status`, { status }),
  users: () => call<User[]>('get', '/admin/users'),
  updateRole: (id: string, role: 'viewer' | 'admin') => call<User>('patch', `/admin/users/${id}/role`, { role }),
  agentTokens: () => call<AgentToken[]>('get', '/admin/agent-tokens'),
  createAgentToken: (data: { name: string; scopes: string[]; expires_in_days?: number | null }) => call<AgentToken & { token: string }>('post', '/admin/agent-tokens', data),
  revokeAgentToken: (id: string) => call<{ revoked: boolean }>('delete', `/admin/agent-tokens/${id}`),
}
