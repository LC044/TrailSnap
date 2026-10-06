import { watch, onBeforeUnmount, nextTick, type Ref } from 'vue'
import { closeTopOverlay } from './useOverlayStack'

// One same-URL entry represents the dialog stack. Back dismisses its top layer;
// remaining layers get a fresh entry after the close/unsaved confirmation settles.
const openDialogs = new Set<symbol>()
const historyKey = '__trailsnapDialogStack'
let active = false
let handlingBack = false
let entryUrl = ''
let listenerAttached = false
let entryId = ''

function pushEntry() {
  if (active || !openDialogs.size) return
  entryUrl = window.location.href
  entryId = `${Date.now()}-${Math.random().toString(36).slice(2)}`
  window.history.pushState({ ...window.history.state, [historyKey]: entryId }, '', entryUrl)
  active = true
}

async function syncEntry() {
  await nextTick()
  if (handlingBack) return
  if (openDialogs.size) pushEntry()
  else if (active) {
    active = false
    if (window.location.href === entryUrl && window.history.state?.[historyKey] === entryId) window.history.back()
  }
}

async function onPopState() {
  if (!active || window.history.state?.[historyKey] === entryId) return
  active = false
  // Explicit route navigation is handled by route guards and route dismissal.
  if (window.location.href !== entryUrl) return
  handlingBack = true
  try {
    await closeTopOverlay()
    await nextTick()
  } finally {
    handlingBack = false
    pushEntry()
  }
}

export function useDialogHistory(visible: Ref<boolean>, enabled: () => boolean) {
  const id = Symbol('history-dialog')
  if (!listenerAttached) {
    window.addEventListener('popstate', onPopState)
    listenerAttached = true
  }
  watch(visible, value => {
    if (value && enabled()) openDialogs.add(id)
    else openDialogs.delete(id)
    void syncEntry()
  }, { immediate: true, flush: 'post' })
  onBeforeUnmount(() => {
    openDialogs.delete(id)
    void syncEntry()
  })
}
