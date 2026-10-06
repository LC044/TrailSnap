import { onBeforeUnmount, ref, type Ref } from 'vue'
import { rubberBand, snapAnchor, spring } from '@/utils/motion'

/** Persistent map/configuration sheets keep their own non-dismissable anchors. */
export function useAnchoredSheet(initial: number, anchors: () => number[], enabled: Ref<boolean>) {
  const height = ref(initial)
  const dragging = ref(false)
  let stop = () => {}, pointer: number | null = null, moved = false
  let startY = 0, startHeight = 0, lastY = 0, lastTime = 0, velocity = 0
  let capture: HTMLElement | null = null
  const settle = (target: number, speed = 0) => {
    stop()
    stop = spring(height.value, target, speed, value => height.value = value)
  }
  const detach = () => {
    const id = pointer
    pointer = null
    dragging.value = false
    if (id !== null && capture?.hasPointerCapture(id)) capture.releasePointerCapture(id)
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', finish)
    window.removeEventListener('pointercancel', cancel)
    window.removeEventListener('blur', cancel)
    capture?.removeEventListener('lostpointercapture', cancel)
  }
  const start = (event: PointerEvent) => {
    if (!enabled.value || event.button !== 0 || !event.isPrimary) return
    stop(); detach()
    pointer = event.pointerId
    capture = event.currentTarget as HTMLElement
    capture.setPointerCapture(pointer)
    startY = lastY = event.clientY
    startHeight = height.value
    lastTime = event.timeStamp
    velocity = 0; moved = false; dragging.value = true
    window.addEventListener('pointermove', move, { passive: false })
    window.addEventListener('pointerup', finish)
    window.addEventListener('pointercancel', cancel)
    window.addEventListener('blur', cancel)
    capture.addEventListener('lostpointercapture', cancel)
  }
  const move = (event: PointerEvent) => {
    if (event.pointerId !== pointer) return
    event.preventDefault()
    moved ||= Math.abs(event.clientY - startY) > 3
    const dt = event.timeStamp - lastTime
    if (dt > 0) velocity = (lastY - event.clientY) / dt
    lastY = event.clientY; lastTime = event.timeStamp
    const stops = anchors()
    height.value = rubberBand(startHeight + startY - event.clientY, Math.min(...stops), Math.max(...stops))
  }
  const finish = (event: PointerEvent) => {
    if (event.pointerId !== pointer) return
    const speed = event.timeStamp - lastTime > 100 ? 0 : velocity
    detach()
    if (moved) settle(snapAnchor(height.value, speed, anchors()), speed)
  }
  const cancel = () => {
    if (pointer === null) return
    detach()
    settle(snapAnchor(height.value, 0, anchors()))
  }
  const toggle = (event?: Event) => {
    if (!enabled.value || (event instanceof MouseEvent && event.detail > 0 && moved)) return
    const stops = anchors()
    const nearest = snapAnchor(height.value, 0, stops)
    settle(stops[(stops.indexOf(nearest) + 1) % stops.length]!)
  }
  const resize = () => {
    detach(); stop()
    const stops = anchors()
    height.value = Math.max(Math.min(...stops), Math.min(Math.max(...stops), height.value))
  }
  onBeforeUnmount(() => { detach(); stop() })
  return { height, dragging, start, toggle, settle, resize }
}
