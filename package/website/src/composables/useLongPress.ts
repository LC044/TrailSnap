import { onBeforeUnmount, ref, type Ref } from 'vue'

export interface UseLongPressOptions {
  /**
   * 长按触发后的回调。会在 450ms 延时 + 触觉反馈(vibrate 10ms)后被调用一次。
   * 调用方通过闭包传入上下文(如当前点击的相册)。
   */
  onLongPress: (event: TouchEvent) => void
  /** 触发延时,默认 450ms */
  delay?: number
  /** 触发期间允许的触点位移容差,默认 10px */
  moveTolerance?: number
  /** 是否触发触觉反馈,默认 true */
  vibrate?: boolean
}

interface LongPressBindings {
  onTouchstart: (event: TouchEvent) => void
}

/**
 * 提供一个轻量的"长按 ~450ms"手势封装。
 *
 * 仅响应单指触屏(由调用方通过 width < breakpoint 决定是否绑定);
 * 多指、超过 moveTolerance 位移、手指抬起/取消都会自动取消本次长按。
 *
 * 用法:
 * ```ts
 * const { onTouchstart } = useLongPress({
 *   onLongPress: () => { showMenu.value = true },
 * })
 * // 仅在 isMobile 时绑定到元素
 * <div v-if="isMobile" @touchstart="onTouchstart">...</div>
 * ```
 */
export function useLongPress(options: UseLongPressOptions): LongPressBindings {
  const delay = options.delay ?? 450
  const moveTolerance = options.moveTolerance ?? 10
  const vibrate = options.vibrate ?? true

  const timerRef: Ref<ReturnType<typeof setTimeout> | null> = ref(null)
  let startX = 0
  let startY = 0
  let active = false

  const clear = () => {
    if (timerRef.value !== null) {
      clearTimeout(timerRef.value)
      timerRef.value = null
    }
    active = false
    if (typeof window !== 'undefined') {
      window.removeEventListener('touchmove', handleMove)
      window.removeEventListener('touchend', handleEnd)
      window.removeEventListener('touchcancel', handleEnd)
    }
  }

  function handleMove(event: TouchEvent) {
    if (active) return
    if (event.touches.length !== 1) {
      clear()
      return
    }
    const touch = event.touches[0]
    if (
      Math.abs(touch.clientX - startX) > moveTolerance
      || Math.abs(touch.clientY - startY) > moveTolerance
    ) {
      clear()
    }
  }

  function handleEnd() {
    clear()
  }

  const onTouchstart = (event: TouchEvent) => {
    if (event.touches.length !== 1) return
    const touch = event.touches[0]
    clear()
    startX = touch.clientX
    startY = touch.clientY
    timerRef.value = setTimeout(() => {
      timerRef.value = null
      active = true
      if (vibrate && typeof navigator !== 'undefined') {
        navigator.vibrate?.(10)
      }
      options.onLongPress(event)
      window.removeEventListener('touchmove', handleMove)
    }, delay)
    window.addEventListener('touchmove', handleMove, { passive: true })
    window.addEventListener('touchend', handleEnd)
    window.addEventListener('touchcancel', handleEnd)
  }

  onBeforeUnmount(clear)

  return { onTouchstart }
}