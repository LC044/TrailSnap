import { onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { reducedMotion } from '@/utils/motion'

/**
 * Counts a number up from its previous value when the source changes.
 *
 * Used for figures that summarise a collection ("我的照片 4,921"): the movement
 * tells the reader the number is live, and the ease-out makes the final value
 * land cleanly instead of stopping abruptly. Falls back to the exact value
 * under reduced motion.
 */
export function useCountUp(source: Ref<number>, duration = 950) {
  const value = ref(0)
  let frame = 0

  const run = (target: number) => {
    cancelAnimationFrame(frame)
    if (reducedMotion() || !Number.isFinite(target)) {
      value.value = target
      return
    }
    const from = value.value
    const start = performance.now()
    const step = (now: number) => {
      const progress = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - progress, 3)
      value.value = Math.round(from + (target - from) * eased)
      if (progress < 1) frame = requestAnimationFrame(step)
      else value.value = target
    }
    frame = requestAnimationFrame(step)
  }

  watch(source, run, { immediate: true })
  onBeforeUnmount(() => cancelAnimationFrame(frame))

  return value
}