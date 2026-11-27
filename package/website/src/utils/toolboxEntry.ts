import type { Router } from 'vue-router'
import { emptyScope, type MediaScope } from '@/api/toolboxWorkflows'

interface ToolboxContext {
  owner: string
  created: number
  scope: MediaScope
}

const contextPrefix = 'trailsnap:toolbox:context:'
const contextLifetime = 15 * 60 * 1000
const inMemoryContexts = new Map<string, { created: number; serialized: string }>()

export function readToolboxScope(id: string, owner: string | undefined): MediaScope | null {
  if (!owner) return null
  try {
    const saved = inMemoryContexts.get(id)?.serialized ?? sessionStorage.getItem(contextPrefix + id)
    const value: ToolboxContext | null = saved ? JSON.parse(saved) : null
    if (value?.owner === owner && Date.now() - value.created < contextLifetime) return value.scope ?? null
  } catch {
    return null
  }
  return null
}

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
  // LAN HTTP can use getRandomValues even when randomUUID requires HTTPS.
  const context = crypto.randomUUID?.() ?? Array.from(crypto.getRandomValues(new Uint8Array(16)),
    byte => byte.toString(16).padStart(2, '0')).join('')
  const created = Date.now()
  const serialized = JSON.stringify({ owner, created, scope })
  try {
    sessionStorage.setItem(contextPrefix + context, serialized)
  } catch {
    for (const [id, entry] of inMemoryContexts) {
      if (created - entry.created >= contextLifetime) inMemoryContexts.delete(id)
    }
    inMemoryContexts.set(context, { created, serialized })
  }
  return router.push({ path: `/toolbox/${kind}`, query: { context } })
}
