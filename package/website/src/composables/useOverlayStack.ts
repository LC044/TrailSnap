import { onBeforeUnmount, watch, type Ref } from 'vue'

type OverlayCloser = () => void | Promise<void>

interface OverlayEntry {
  id: symbol
  close: OverlayCloser
}

const overlays: OverlayEntry[] = []
let elementPlusBridgeRegistered = false

export function registerOverlay(close: OverlayCloser, id = Symbol('overlay')) {
  const existing = overlays.findIndex(item => item.id === id)
  if (existing >= 0) overlays.splice(existing, 1)
  overlays.push({ id, close })

  return () => {
    const index = overlays.findIndex(item => item.id === id)
    if (index >= 0) overlays.splice(index, 1)
  }
}

export async function closeTopOverlay(): Promise<boolean> {
  const top = overlays.at(-1)
  if (!top) return false

  overlays.pop()
  await top.close()
  return true
}

export function useOverlayStack(visible: Ref<boolean>, close: OverlayCloser) {
  const id = Symbol('component-overlay')
  let unregister: (() => void) | undefined

  watch(visible, (isVisible) => {
    unregister?.()
    unregister = undefined
    if (isVisible) unregister = registerOverlay(close, id)
  }, { immediate: true, flush: 'sync' })

  onBeforeUnmount(() => unregister?.())
}

/**
 * Registers every Element Plus dialog/drawer/message box with the same LIFO
 * stack used by custom overlays. This keeps Android back behavior correct for
 * existing and future overlays without requiring every feature component to
 * repeat registration boilerplate.
 */
export function registerElementPlusOverlayBridge() {
  if (elementPlusBridgeRegistered || typeof document === 'undefined') return
  elementPlusBridgeRegistered = true

  const registered = new Map<HTMLElement, () => void>()
  const selector = '.el-overlay'

  const isManagedOverlay = (element: HTMLElement) =>
    Boolean(element.querySelector('.el-dialog, .el-drawer, .el-message-box'))

  const closeElementOverlay = (element: HTMLElement) => {
    const closeButton = element.querySelector<HTMLElement>(
      '.el-dialog__headerbtn, .el-drawer__close-btn, .el-message-box__btns .el-button:not(.el-button--primary)'
    )
    if (closeButton) {
      closeButton.click()
      return
    }

    document.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'Escape',
      code: 'Escape',
      bubbles: true,
    }))
  }

  const sync = () => {
    const active = new Set(
      Array.from(document.querySelectorAll<HTMLElement>(selector))
        .filter(isManagedOverlay)
        .filter(element => element.style.display !== 'none' && element.getAttribute('aria-hidden') !== 'true')
    )

    for (const [element, unregister] of registered) {
      if (!active.has(element)) {
        unregister()
        registered.delete(element)
      }
    }

    for (const element of active) {
      if (registered.has(element)) continue
      registered.set(element, registerOverlay(() => closeElementOverlay(element)))
    }
  }

  let scheduled = false
  const scheduleSync = () => {
    if (scheduled) return
    scheduled = true
    queueMicrotask(() => {
      scheduled = false
      sync()
    })
  }

  new MutationObserver(scheduleSync).observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['style', 'class', 'aria-hidden'],
  })
  sync()
}
