import request from '@/utils/request'

export type ToolKind = 'organize' | 'rename' | 'album' | 'cleanup' | 'metadata'
export interface MediaScope {
  source: 'albums' | 'folders' | 'filter' | 'selected' | 'all'
  album_ids: string[]
  folders: string[]
  include_children: boolean
  photo_ids: string[]
  excluded_ids: string[]
  start_date: string | null
  end_date: string | null
  upload_time_fallback: boolean
  media_type: 'image' | 'video' | 'all'
}
export interface OrganizeRule {
  strategy: 'time' | 'location' | 'person' | 'category'
  granularity: string
  nested: boolean
  groups: string[] | null
}
export interface ToolConfig {
  kind: ToolKind
  action: 'move' | 'copy' | null
  target: string
  layout: 'rebuild' | 'preserve'
  rules: OrganizeRule[]
  missing: 'skip' | 'placeholder' | 'upload'
  multi_group: 'skip' | 'first' | 'all'
  template: string
  start_index: number
  reset_index: boolean
  descending: boolean
  album_prefix: string
  cleanup_mode: 'duplicate' | 'similar' | 'quality'
  compare_all: boolean
  similarity: number
  quality_max: number
  time_mode: 'none' | 'auto' | 'custom'
  custom_time: string | null
  make: string
  model: string
  only_missing_metadata: boolean
}
export interface ToolPreset { id: string; name: string; config: ToolConfig }
export interface ToolboxPreferences {
  version: number
  presets: ToolPreset[]
  default_rename_id: string | null
  recent: ToolConfig[]
}
export interface ToolPlan {
  id: string
  kind: ToolKind | 'undo'
  status: string
  version: number
  request: { scope: MediaScope; config: ToolConfig }
  summary: Record<string, number>
  task_id: string | null
  created_at: string
  expires_at: string
  finished_at: string | null
  stop_requested: boolean
}
export interface ToolPlanItem {
  id: number
  photo_id: string
  source: string
  target: string
  status: string
  reason: string
  detail: { label?: string; targets?: string[]; related_ids?: string[]; time?: string; make?: string; model?: string }
}
export interface ScopeItem { id: string; filename: string; photo_time: string | null; file_type: string }
export interface PageResult<T> { total: number; items: T[] }

export const emptyScope = (): MediaScope => ({
  source: 'albums', album_ids: [], folders: [], include_children: true, photo_ids: [], excluded_ids: [],
  start_date: null, end_date: null, upload_time_fallback: false, media_type: 'image',
})
export const defaultConfig = (kind: ToolKind): ToolConfig => ({
  kind, action: null, target: '', layout: 'rebuild',
  rules: [{ strategy: 'time', granularity: 'year', nested: true, groups: null }],
  missing: 'skip', multi_group: 'skip', template: 'IMG_{date}_{time}', start_index: 1,
  reset_index: false, descending: false, album_prefix: '', cleanup_mode: 'duplicate',
  compare_all: false, similarity: .95, quality_max: 40, time_mode: 'auto', custom_time: null,
  make: '', model: '', only_missing_metadata: true,
})

export function renameTemplateError(template: string): string {
  const allowed = new Set(['date', 'time', 'year', 'month', 'day', 'hour', 'minute', 'second',
    'city', 'location', 'province', 'district', 'original', 'index', 'sequence3', 'sequence4',
    'camera', 'lens', 'iso', 'extension'])
  const unknown = [...template.matchAll(/\{([^{}]*)\}/g)].map(match => match[1]).filter(key => !allowed.has(key))
  if (unknown.length) return `未知变量：${unknown.join('、')}`
  const literal = template.replace(/\{[^{}]*\}/g, '')
  const broken = literal.match(/[{}][^{}]*/g)
  if (broken?.length) return `存在未闭合的变量占位符：${broken.join('、')}`
  if (/[\\/:\x00*?"<>|]/.test(literal)) return '模板包含非法路径字符：\\ / : * ? " < > |'
  return template.trim() ? '' : '请选择模板或输入命名规则'
}

const base = '/api/toolbox'
export const workflowApi = {
  async resolveFolder(parent: string) {
    return (await request.get<{ path: string }>(`${base}/folders/resolve`, { params: { parent } })).data.path
  },
  async scope(scope: MediaScope, offset = 0) {
    return (await request.post<PageResult<ScopeItem>>(`${base}/scopes/preview`, scope, { params: { offset } })).data
  },
  async options(scope: MediaScope, rule: OrganizeRule) {
    return (await request.post<{ id: string; name: string; count: number }[]>(`${base}/organize/options`, {
      scope, config: { ...defaultConfig('album'), rules: [rule] },
    })).data
  },
  async preview(scope: MediaScope, config: ToolConfig) {
    return (await request.post<ToolPlan>(`${base}/plans`, { scope, config }, { timeout: 120000 })).data
  },
  async plan(id: string) { return (await request.get<ToolPlan>(`${base}/plans/${id}`)).data },
  async history(offset = 0, limit = 20, activeOnly = false) {
    return (await request.get<ToolPlan[]>(`${base}/plans`, { params: { offset, limit, active_only: activeOnly } })).data
  },
  async items(id: string, offset = 0, status?: string) {
    return (await request.get<PageResult<ToolPlanItem>>(`${base}/plans/${id}/items`, { params: { offset, status } })).data
  },
  async execute(plan: ToolPlan, selectedItems?: number[]) {
    return (await request.post<ToolPlan>(`${base}/plans/${plan.id}/execute`, {
      version: plan.version, confirmed: true, selected_items: selectedItems,
    })).data
  },
  async stop(id: string) { return (await request.post<ToolPlan>(`${base}/plans/${id}/stop`)).data },
  async recover(id: string, mode: 'retry' | 'undo') {
    return (await request.post<ToolPlan>(`${base}/plans/${id}/${mode}`)).data
  },
  async preferences() { return (await request.get<ToolboxPreferences>(`${base}/preferences`)).data },
  async savePreferences(value: ToolboxPreferences) {
    return (await request.put<ToolboxPreferences>(`${base}/preferences`, value)).data
  },
}
