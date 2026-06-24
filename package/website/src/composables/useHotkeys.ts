import { onMounted, onBeforeUnmount, getCurrentInstance } from 'vue'

export interface HotkeyDef {
  key: string
  handler: (e: KeyboardEvent) => void
  when?: () => boolean
  shift?: boolean
  ctrl?: boolean
  alt?: boolean
  meta?: boolean
}

export interface HotkeyOptions {
  /** Higher priority wins. Default 0. */
  priority?: number
  /** Master switch — when false, all hotkeys in this group are skipped. */
  enabled?: () => boolean
}

interface RegisteredGroup {
  hotkeys: HotkeyDef[]
  options: HotkeyOptions
  id: number
}

let globalListenerAttached = false
const groups: RegisteredGroup[] = []
let nextId = 1

function matchesKey(def: HotkeyDef, e: KeyboardEvent): boolean {
  if (def.key !== e.key) return false
  if (!!def.shift !== e.shiftKey) return false
  if (!!def.ctrl !== e.ctrlKey) return false
  if (!!def.alt !== e.altKey) return false
  if (!!def.meta !== e.metaKey) return false
  return true
}

function handleGlobalKeydown(e: KeyboardEvent) {
  // Skip when user is typing in an input/textarea/contenteditable
  const target = e.target as HTMLElement
  const tag = target?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || target?.isContentEditable) {
    // Only let through keys that are explicitly Escape or modifier combos
    if (e.key !== 'Escape' && !e.ctrlKey && !e.metaKey) return
  }

  // Let Element Plus handle its own Esc (el-dialog, el-select dropdown, etc.)
  if (e.key === 'Escape') {
    const elOverlay = target?.closest('.el-overlay, .el-dialog, .el-select__popper, .el-message-box')
    if (elOverlay) return
  }

  // Process groups in priority order (highest first)
  const sorted = [...groups].sort((a, b) => (b.options.priority ?? 0) - (a.options.priority ?? 0))

  for (const group of sorted) {
    if (group.options.enabled && !group.options.enabled()) continue

    for (const def of group.hotkeys) {
      if (def.when && !def.when()) continue
      if (matchesKey(def, e)) {
        e.preventDefault()
        e.stopPropagation()
        def.handler(e)
        return
      }
    }
  }
}

function ensureListener() {
  if (!globalListenerAttached) {
    document.addEventListener('keydown', handleGlobalKeydown, true)
    globalListenerAttached = true
  }
}

function removeListenerIfNeeded() {
  if (groups.length === 0 && globalListenerAttached) {
    document.removeEventListener('keydown', handleGlobalKeydown, true)
    globalListenerAttached = false
  }
}

/**
 * Composable to register a group of keyboard shortcuts with priority-based stacking.
 *
 * ```ts
 * useHotkeys([
 *   { key: 'ArrowLeft', handler: prev, when: () => hasPrev.value && !isEditing.value },
 *   { key: 'd', handler: download },
 * ], { priority: 100, enabled: () => visible.value })
 * ```
 *
 * - Single `document` listener (event delegation) regardless of how many groups are registered.
 * - Groups are evaluated in priority order; highest first.
 * - Within a group, first matching hotkey wins.
 * - Automatically cleaned up on component unmount.
 */
export function useHotkeys(hotkeys: HotkeyDef[], options: HotkeyOptions = {}) {
  const id = nextId++
  const group: RegisteredGroup = { hotkeys, options, id }

  ensureListener()
  groups.push(group)

  // Auto-cleanup if called inside a component setup
  if (getCurrentInstance()) {
    onBeforeUnmount(() => {
      const idx = groups.findIndex(g => g.id === id)
      if (idx !== -1) groups.splice(idx, 1)
      removeListenerIfNeeded()
    })
  }

  return {
    /** Update the hotkey definitions in-place. */
    update(newHotkeys: HotkeyDef[]) {
      const g = groups.find(g => g.id === id)
      if (g) g.hotkeys = newHotkeys
    },
    /** Manually remove this group (useful outside component setup). */
    dispose() {
      const idx = groups.findIndex(g => g.id === id)
      if (idx !== -1) groups.splice(idx, 1)
      removeListenerIfNeeded()
    },
  }
}
