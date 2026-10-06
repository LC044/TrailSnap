import { onBeforeUnmount, ref, watch, nextTick, type Ref } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { rubberBand, snapAnchor, spring } from '@/utils/motion'

export function useSheetGesture(panel: Ref<HTMLElement | null>, visible: Ref<boolean>, enabled: Ref<boolean>, close: () => void) {
  const mobile = useMediaQuery('(max-width: 767px)')
  const style = ref<Record<string, string>>({})
  let height = 0, normal = 0, maximum = 0, pointer: number | null = null
  let startY = 0, startHeight = 0, lastY = 0, lastTime = 0, velocity = 0
  let moved = false
  let stop = () => {}, capture: HTMLElement | null = null
  const render = (value: number) => {
    height = value
    style.value = { height: `${Math.max(1, Math.min(maximum, value))}px`, maxHeight: `${maximum}px`, transform: `translateY(${Math.max(0, -value)}px) scaleY(${Math.max(1, value / maximum)})`, transformOrigin: 'bottom', transition: 'none' }
  }
  const reset = () => {
    stop()
    if (pointer !== null && capture?.hasPointerCapture(pointer)) capture.releasePointerCapture(pointer)
    pointer = null
    style.value = {}
  }
  watch([visible, mobile, enabled], async ([open, small, active]) => {
    reset()
    if (!open || !small || !active) return
    await nextTick()
    if (!visible.value || !panel.value) return
    maximum = Math.min(window.visualViewport?.height ?? window.innerHeight, window.innerHeight) * .92
    normal = Math.min(panel.value.offsetHeight, maximum)
    height = normal
  }, { immediate: true, flush: 'post' })
  const start = (event: PointerEvent) => {
    if (!mobile.value || !enabled.value || !event.isPrimary || event.button !== 0 || !panel.value) return
    if ((event.target as HTMLElement).closest('button, a, input, select, textarea')) return
    stop()
    maximum = (window.visualViewport?.height ?? window.innerHeight) * .92
    height = panel.value.offsetHeight
    normal ||= height
    pointer = event.pointerId
    capture = event.currentTarget as HTMLElement
    capture.setPointerCapture(pointer)
    startY = lastY = event.clientY
    startHeight = height
    lastTime = event.timeStamp
    velocity = 0
    moved = false
  }
  const move = (event: PointerEvent) => {
    if (event.pointerId !== pointer) return
    event.preventDefault()
    moved ||= Math.abs(event.clientY - startY) > 4
    const elapsed = event.timeStamp - lastTime
    if (elapsed > 0) velocity = (lastY - event.clientY) / elapsed
    lastY = event.clientY
    lastTime = event.timeStamp
    render(rubberBand(startHeight + startY - event.clientY, 0, maximum))
  }
  const finish = (event: PointerEvent) => {
    if (event.pointerId !== pointer) return
    const cancelled = event.type === 'pointercancel' || event.type === 'lostpointercapture'
    pointer = null
    if (capture?.hasPointerCapture(event.pointerId)) capture.releasePointerCapture(event.pointerId)
    if (!moved) return
    // A pause before release must not reuse a stale flick velocity.
    const speed = cancelled || event.timeStamp - lastTime > 100 ? 0 : velocity
    const target = cancelled ? normal : snapAnchor(height, speed, [0, Math.min(normal, maximum * .6), maximum])
    stop = spring(height, target, speed, render, () => { if (target === 0) close() })
  }
  const resize = () => { if (visible.value) reset() }
  window.addEventListener('resize', resize)
  window.visualViewport?.addEventListener('resize', resize)
  onBeforeUnmount(() => {
    reset()
    window.removeEventListener('resize', resize)
    window.visualViewport?.removeEventListener('resize', resize)
  })
  return { style, start, move, finish }
}
