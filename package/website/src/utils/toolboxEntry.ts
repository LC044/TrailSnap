import type { Router } from 'vue-router'
import { emptyScope, type MediaScope } from '@/api/toolboxWorkflows'

export function openToolForSelection(router: Router, owner: string, ids: string[], kind: 'organize' | 'rename') {
  if (!owner || !ids.length) return
  const scope = { ...emptyScope(), source: 'selected' as const, photo_ids: [...new Set(ids)] }
  return openScopedTool(router, owner, scope, kind)
}

export function openToolForFolder(router: Router, owner: string, path: string, kind: 'organize' | 'rename') {
  if (!owner || !path) return
  return openScopedTool(router, owner, { ...emptyScope(), source: 'folders', folders: [path] }, kind)
}

function openScopedTool(router: Router, owner: string, scope: MediaScope, kind: 'organize' | 'rename') {
  const context = crypto.randomUUID()
  sessionStorage.setItem(`trailsnap:toolbox:context:${context}`, JSON.stringify({ owner, created: Date.now(), scope }))
  return router.push({ path: `/toolbox/${kind}`, query: { context } })
}
