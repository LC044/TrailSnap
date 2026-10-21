import { ref } from 'vue'

// Short lived, account-scoped metadata only. Lists and filtered photos stay fresh.
const entries = new Map<string, { expires: number; promise: Promise<unknown> }>()
export const locationMetadataRevision = ref(0)

export function invalidateLocationMetadata() {
  entries.clear()
  locationMetadataRevision.value++
}

export function cachedLocationMetadata<T>(key: string, load: () => Promise<T>): Promise<T> {
  const cached = entries.get(key)
  if (cached && cached.expires > Date.now()) return cached.promise as Promise<T>
  const entry = { expires: Infinity, promise: Promise.resolve().then(load) as Promise<unknown> }
  entries.set(key, entry)
  entry.promise = entry.promise.then(value => {
    entry.expires = Date.now() + 15_000
    return value
  }, error => {
    if (entries.get(key) === entry) entries.delete(key)
    throw error
  })
  return entry.promise as Promise<T>
}

let taskScope = ''
let taskSignature = ''
export function observeLocationTasks(scope: string, groups: unknown) {
  if (!Array.isArray(groups)) return
  const signature = JSON.stringify(groups.map(group => [group.category, group.pending, group.processing, group.failed, group.completed, group.status]))
  if (scope === taskScope && taskSignature && signature !== taskSignature) invalidateLocationMetadata()
  taskScope = scope
  taskSignature = signature
}
