import axios from 'axios'

export type GitHubIdentity = { github_user_id: number; login: string; avatar_url?: string; profile_url?: string; email?: string; linked_at: string; last_login_at?: string }
export type GitHubPullRequest = { number: number; title: string; url: string; state: 'open' | 'closed' | 'merged'; draft: boolean; merged_at?: string; updated_at?: string }
export type User = { id: string; username: string; email: string; role: 'viewer' | 'admin' | 'owner'; is_active: boolean; github?: GitHubIdentity }
export type AgentToken = { id: string; name: string; token_prefix: string; scopes: string[]; project_key?: string; agent_role?: string; task_id?: string; expires_at?: string; last_used_at?: string; revoked_at?: string; created_at: string }
export type Clarification = { id: string; question_id: string; target_field?: string; question: string; rationale: string; blocking: boolean; suggested_options: string[]; status: string; answer?: string; round_number: number }
export type AcceptanceCriterion = { id: string; given: string; when: string; then: string; required: boolean; verification: string; dataset?: string }
export type RequirementSpec = { id: string; requirement_id: string; requirement_revision: number; revision: number; status: string; content: Record<string, any>; content_hash: string; state_version: number; acceptance: AcceptanceCriterion[]; approved_at?: string }
export type AgentRun = { id: string; task_id: string; attempt_id: string; status: string; provider: string; model?: string; runner_name: string; state_version: number; lease_expires_at: string; result?: Record<string, unknown>; questions: Array<{ id: string; question: string; blocking: boolean; status: string; answer?: string }> }
export type DeliveryTask = { id: string; requirement_id: string; spec_id: string; state: string; state_version: number; repository: string; target_branch: string; base_sha: string; risk_level: string; blocked_reason?: string; runs: AgentRun[]; pull_requests: Array<{ id: string; number: number; url: string; head_sha: string; state: string }>; context_bundle?: Record<string, any> }
export type Requirement = {
  id: string; public_number?: number; type: string; title: string; description: string; log_text?: string; current_behavior?: string; expected_behavior?: string
  steps_to_reproduce?: string; severity: string; product_version?: string; environment: Record<string, unknown>
  visibility: string; status: string; priority: string; risk_level: string; review_reason?: string
  duplicate_of_id?: string; github_issue_number?: number; github_issue_url?: string; github_state?: string
  github_pull_requests: GitHubPullRequest[]
  created_by?: string; created_by_name?: string; assignee_name?: string; submitter_name?: string; submitter_contact?: string; upload_token?: string
  created_at: string; updated_at: string; follower_count: number; triage?: Record<string, any>; triage_provider?: string; triage_model?: string
  content_revision: number; state_version: number; confirmed_summary?: string; clarifications?: Clarification[]
  specs?: RequirementSpec[]; delivery_tasks?: DeliveryTask[]
  deleted_at?: string; deleted_by?: string; delete_reason?: string; source: 'platform' | 'github'
  attachments?: Array<{ id: string; name: string; content_type: string; size_bytes: number; kind: string; download_url: string; content_sha256?: string; processing_status: string; processing_error?: string }>
}
export type BatchItem = { id: string; requirement_id: string; priority_order: number; delivery_status: string; requirement_snapshot: Record<string, unknown> }
export type Batch = {
  id: string; name: string; version_name: string; batch_type: string; goal: string; status: string; target_date?: string
  max_risk_level: string; github_milestone_number?: number; github_milestone_url?: string; items: BatchItem[]
}
export type BatchInput = {
  name: string; version_name: string; goal: string; batch_type: string
  target_date: string | null; max_risk_level: string
}
export type RequirementHistory = { id: string; action: string; actor_name: string; before?: string; after?: string; reason?: string; created_at: string }
export type Dashboard = {
  total: number; new_last_7_days: number; pending_review: number; in_progress: number
  github_linked: number; anonymous: number
  by_status: Record<string, number>; by_type: Record<string, number>
  contributor_count: number; follower_count: number
  daily_new_30d: Array<{ date: string; count: number }>
  top_contributors: Array<{ user_id: string; name: string; count: number }>
}
export type AIModel = { id: string; connection_id: string; model_name: string; display_name: string; enabled: boolean; supports_json_mode: boolean; context_window?: number; reasoning_levels: string[] }
export type AIConnection = { id: string; name: string; provider: string; api_base: string; has_api_key: boolean; api_key_hint?: string; enabled: boolean; timeout_seconds: number; priority: number; models: AIModel[] }
export type AITaskRoute = { task_type: string; label: string; description: string; enabled: boolean; model_ids: string[]; reasoning_effort: string; source: 'managed' | 'environment' | 'none'; updated_at?: string }
export type AISettings = { connections: AIConnection[]; routes: AITaskRoute[]; legacy_environment_configured: boolean }

export type UsageBreakdownItem = {
  key: string; label?: string; requests: number; input_tokens: number; output_tokens: number
  cache_read_tokens: number; cache_creation_tokens: number; input_total_tokens: number
  real_total_tokens: number; cache_hit_rate: number; total_cost_usd: number
}
export type UsageOverview = {
  total: {
    requests: number; input_tokens: number; output_tokens: number; cache_read_tokens: number
    cache_creation_tokens: number; input_total_tokens: number; real_total_tokens: number
    cache_hit_rate: number; total_cost_usd: number; date_from?: string; date_to?: string
  }
  by_model: UsageBreakdownItem[]
  by_provider: UsageBreakdownItem[]
  by_app_type: UsageBreakdownItem[]
  by_device: UsageBreakdownItem[]
  device_count: number
}
export type UsageDailyPoint = {
  date: string; requests: number; input_tokens: number; output_tokens: number
  cache_read_tokens: number; cache_creation_tokens: number; total_cost_usd: number
}
export type UsageImportRecord = {
  id: string; device_id: string; device_label: string; file_name: string; file_sha256: string
  file_size: number; user_version?: number; detail_rows: number; detail_new: number
  detail_dup: number; detail_aged_out: number; rollup_rows: number; rollup_upserted: number
  date_min?: string; date_max?: string; imported_by?: string; imported_at?: string
}
export type UsageImportResult = {
  import_id: string; device_id: string; device_label: string; file_name: string
  file_sha256: string; user_version?: number; detail_rows: number; detail_new: number
  detail_dup: number; detail_aged_out: number; rollup_rows: number; rollup_upserted: number
  date_min?: string; date_max?: string
}

const client = axios.create({ baseURL: import.meta.env.VITE_REQUIREMENT_API_URL || '/api', timeout: 20000 })
client.interceptors.request.use(config => {
  const token = localStorage.getItem('rp_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

async function call<T>(method: string, url: string, data?: unknown, headers?: Record<string, string>): Promise<T> {
  const response = await client.request({ method, url, data, headers })
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
  preflightTriage: (data: unknown) => call<{ available: boolean; questions: Array<{ question_id: string; question: string; rationale: string; suggested_options: string[] }>; analysis?: Record<string, any>; model?: string; reason?: string }>('post', '/requirements/preflight-triage', data),
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
  updateRequirementStatus: (id: string, status: string, reason: string) => call<Requirement>('patch', `/requirements/${id}/status`, { status, reason }),
  withdrawRequirement: (id: string) => call<Requirement>('post', `/requirements/${id}/withdraw`),
  followRequirement: (id: string) => call<{ following: boolean }>('post', `/requirements/${id}/follow`),
  triage: (id: string) => call<{ job_id: string }>('post', `/requirements/${id}/triage`),
  review: (id: string, data: unknown) => call<Requirement>('post', `/requirements/${id}/review`, data),
  correctSummary: (id: string, summary: string, expected_state_version: number) => call<Requirement>('post', `/requirements/${id}/summary-corrections`, { summary, expected_state_version }),
  answerClarification: (id: string, questionId: string, answer: string, expected_state_version: number) => call<Requirement>('post', `/requirements/${id}/clarifications/${questionId}/answers`, { answer, expected_state_version }),
  createSpec: (id: string, data: unknown) => call<RequirementSpec>('post', `/requirements/${id}/specs`, data, { 'Idempotency-Key': crypto.randomUUID() }),
  updateSpec: (id: string, data: unknown) => call<RequirementSpec>('patch', `/specs/${id}`, data, { 'Idempotency-Key': crypto.randomUUID() }),
  approveSpec: (id: string, data: unknown) => call<RequirementSpec>('post', `/specs/${id}/approve`, data, { 'Idempotency-Key': crypto.randomUUID() }),
  createDeliveryTask: (data: unknown) => call<DeliveryTask>('post', '/delivery-tasks', data, { 'Idempotency-Key': crypto.randomUUID() }),
  deliveryTask: (id: string) => call<DeliveryTask>('get', `/delivery-tasks/${id}`),
  cancelRun: (id: string) => call<AgentRun>('post', `/agent-runs/${id}/cancel`),
  answerRunQuestion: (id: string, data: unknown) => call<AgentRun>('post', `/agent-run-questions/${id}/answer`, data, { 'Idempotency-Key': crypto.randomUUID() }),
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
  createBatch: (data: BatchInput) => call<Batch>('post', '/versions', data),
  updateBatch: (batchId: string, data: Partial<BatchInput>) => call<Batch>('patch', `/versions/${batchId}`, data),
  addBatchItem: (batchId: string, requirementId: string) => call<Batch>('post', `/versions/${batchId}/items`, { requirement_id: requirementId }),
  removeBatchItem: (batchId: string, itemId: string) => call<{ removed: boolean }>('delete', `/versions/${batchId}/items/${itemId}`),
  lockBatch: (batchId: string) => call<Batch>('post', `/versions/${batchId}/lock`),
  updateBatchStatus: (batchId: string, status: string, reason: string) => call<Batch>('patch', `/versions/${batchId}/status`, { status, reason }),
  updateDeliveryStatus: (batchId: string, itemId: string, status: string) => call('patch', `/versions/${batchId}/items/${itemId}/status`, { status }),
  users: () => call<User[]>('get', '/admin/users'),
  updateRole: (id: string, role: 'viewer' | 'admin') => call<User>('patch', `/admin/users/${id}/role`, { role }),
  agentTokens: () => call<AgentToken[]>('get', '/admin/agent-tokens'),
  createAgentToken: (data: { name: string; scopes: string[]; expires_in_days?: number | null; project_key?: string; agent_role?: string | null; task_id?: string | null }) => call<AgentToken & { token: string }>('post', '/admin/agent-tokens', data),
  revokeAgentToken: (id: string) => call<{ revoked: boolean }>('delete', `/admin/agent-tokens/${id}`),
  usageOverview: (params = '') => call<UsageOverview>('get', `/usage/overview${params}`),
  usageDaily: (params = '') => call<UsageDailyPoint[]>('get', `/usage/daily${params}`),
  usageFilters: () => call<{ models: string[]; app_types: string[] }>('get', '/usage/filters'),
  usageImports: () => call<UsageImportRecord[]>('get', '/usage/imports'),
  uploadUsageImport: (deviceLabel: string, file: File) => {
    const data = new FormData(); data.append('file', file); data.append('device_label', deviceLabel)
    return client.post('/usage/imports', data, {
      timeout: 120000,
    }).then(response => response.data.data as UsageImportResult)
  },
  deleteUsageImport: (id: string) => call<{ deleted: boolean; detail_removed: number }>('delete', `/usage/imports/${id}`),
  deleteUsageDevice: (id: string) => call<{ deleted: boolean; device_label: string }>('delete', `/usage/devices/${id}`),
  aiSettings: () => call<AISettings>('get', '/admin/ai-settings'),
  createAIConnection: (data: unknown) => call<AIConnection>('post', '/admin/ai-connections', data),
  updateAIConnection: (id: string, data: unknown) => call<AIConnection>('patch', `/admin/ai-connections/${id}`, data),
  deleteAIConnection: (id: string) => call<{ deleted: boolean }>('delete', `/admin/ai-connections/${id}`),
  createAIModel: (connectionId: string, data: unknown) => call<AIModel>('post', `/admin/ai-connections/${connectionId}/models`, data),
  updateAIModel: (id: string, data: unknown) => call<AIModel>('patch', `/admin/ai-models/${id}`, data),
  deleteAIModel: (id: string) => call<{ deleted: boolean }>('delete', `/admin/ai-models/${id}`),
  updateAITaskRoute: (taskType: string, data: unknown) => call<AITaskRoute>('put', `/admin/ai-task-routes/${taskType}`, data),
  testAIConnection: (connectionId: string, modelId?: string) => call<{ available: boolean; model: string; response?: string; error?: string }>('post', `/admin/ai-connections/${connectionId}/test`, { model_id: modelId || null }),
}
