import { onBeforeUnmount, onMounted, type Ref } from 'vue'

interface SwipeNavigationOptions {
  /** Swipe left (finger moves leftwards) → typically "go to next" */
  onSwipeLeft?: () => void
  /** Swipe right (finger moves rightwards) → typically "go to previous" */
  onSwipeRight?: () => void
  /** Return false to ignore the gesture entirely (e.g. on desktop). */
  enabled?: () => boolean
  /** Minimum horizontal distance (px) to count as a swipe. */
  threshold?: number
  /** Max vertical drift (px) allowed for a horizontal swipe. */
  maxOffAxis?: number
  /** Movement (px) before axis (horizontal vs vertical) is locked. */
  axisLockDistance?: number
}

/**
 * Bind touch swipe handling to an element ref. Once the finger moves past
 * `axisLockDistance`, the gesture is locked to horizontal or vertical: a
 * horizontal lock calls `preventDefault()` so the container won't scroll
 * vertically mid-swipe, while a vertical lock leaves scrolling untouched.
 *
 * `enabled()` is re-evaluated on every `touchstart`, so passing a
 * `matchMedia` check makes the gesture mobile-only with no extra wiring.
 */
export function useSwipeNavigation(
  target: Ref<HTMLElement | null>,
  options: SwipeNavigationOptions = {}
) {
  const {
    onSwipeLeft,
    onSwipeRight,
    enabled = () => true,
    threshold = 50,
    maxOffAxis = 60,
    axisLockDistance = 8,
  } = options

  let startX = 0
  let startY = 0
  let tracking = false
  let axis: 'h' | 'v' | null = null

  const onTouchStart = (e: TouchEvent) => {
    if (!enabled() || e.touches.length !== 1) return
    const t = e.touches[0]
    startX = t.clientX
    startY = t.clientY
    tracking = true
    axis = null
  }

  const onTouchMove = (e: TouchEvent) => {
    if (!tracking || !enabled()) return
    const t = e.touches[0]
    const dx = t.clientX - startX
    const dy = t.clientY - startY
    if (axis === null) {
      if (Math.abs(dx) > axisLockDistance || Math.abs(dy) > axisLockDistance) {
        axis = Math.abs(dx) > Math.abs(dy) ? 'h' : 'v'
      }
    }
    // While swiping horizontally, stop the page from scrolling vertically.
    if (axis === 'h' && e.cancelable) {
      e.preventDefault()
    }
  }

  const onTouchEnd = (e: TouchEvent) => {
    if (!tracking) return
    tracking = false
    if (axis !== 'h') return
    const t = e.changedTouches[0]
    const dx = t.clientX - startX
    const dy = t.clientY - startY
    if (Math.abs(dx) >= threshold && Math.abs(dy) <= maxOffAxis) {
      if (dx < 0) onSwipeLeft?.()
      else onSwipeRight?.()
    }
  }

  onMounted(() => {
    const el = target.value
    if (!el) return
    el.addEventListener('touchstart', onTouchStart, { passive: true })
    el.addEventListener('touchmove', onTouchMove, { passive: false })
    el.addEventListener('touchend', onTouchEnd, { passive: true })
    el.addEventListener('touchcancel', onTouchEnd, { passive: true })
  })

  onBeforeUnmount(() => {
    const el = target.value
    if (!el) return
    el.removeEventListener('touchstart', onTouchStart)
    el.removeEventListener('touchmove', onTouchMove)
    el.removeEventListener('touchend', onTouchEnd)
    el.removeEventListener('touchcancel', onTouchEnd)
  })
}
