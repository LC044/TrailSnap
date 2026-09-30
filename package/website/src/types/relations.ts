export type RelationType = 'person' | 'place' | 'memory' | 'photo'
export interface RelationTarget {
  kind: RelationType
  id?: string
  name?: string
  level?: string
  place_key?: string
  sceneId?: string
}
export interface RelationNode {
  id: string
  type: RelationType
  label: string
  subtitle: string
  photo_id: string | null
  detail_target: RelationTarget | null
}
export interface RelationEdge {
  source: string
  target: string
  memory_count: number
  photo_count: number
  relation_kinds: string[]
  evidence_summary: string
}
export interface RelationPage {
  center: RelationNode
  nodes: RelationNode[]
  edges: RelationEdge[]
  has_more: boolean
  next_cursor: string | null
}
export interface RelationResults {
  items: RelationNode[]
  has_more: boolean
  next_cursor: string | null
  objects?: RelationNode[]
}
export const relationLabels: Record<RelationType, string> = {
  person: '人物',
  place: '地点',
  memory: '记忆',
  photo: '照片',
}
