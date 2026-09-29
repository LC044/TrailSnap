import request from '@/utils/request'
import type { RelationPage, RelationResults, RelationType } from '@/types/relations'

export const relationsApi = {
  async neighbors(root: string, types: RelationType[], cursor?: string | null) {
    return (
      await request.get<RelationPage>('/api/relations/neighbors', {
        params: { root, types: types.join(','), limit: 20, cursor: cursor || undefined },
      })
    ).data
  },
  async evidence(left: string, right: string, kind: 'memory' | 'photo', cursor?: string | null) {
    const path = kind === 'memory' ? 'common-memories' : 'evidence'
    return (
      await request.get<RelationResults>(`/api/relations/${path}`, {
        params: { left, right, kind, cursor: cursor || undefined, limit: 20 },
      })
    ).data
  },
  async search(type: RelationType, q: string, cursor?: string | null) {
    return (
      await request.get<RelationResults>('/api/relations/search', {
        params: { type, q, cursor: cursor || undefined, limit: 20 },
      })
    ).data
  },
}
