import { onBeforeUnmount, ref } from 'vue'

/**
 * 移动端照片网格的滑选手势。
 *
 * 状态机（仅单指触屏生效，滑选只能作为长按的延续启动，与 iOS 相册一致，
 * 避免选择模式下普通拖动被劫持而无法滚动页面）：
 *
 * 1. 按下后 450ms 内位移 ≤ 10px → 长按触发 onLongPressActivate
 *    （调用方进入选择模式并 toggle 起始照片），同时进入滑选就绪态。
 * 2. 长按触发后不松手继续拖动 → 滑选：touchmove 被 preventDefault（页面
 *    不再滚动），沿手指路径逐点命中照片卡片并回调 onSwipePhoto。
 *    滑选目标状态由起始照片长按前的选中态决定：未选中 → 滑过全选，
 *    已选中 → 滑过全取消（取消滑选的入口）。
 * 3. 等待期内位移超容差 → 取消长按，页面正常滚动，手势作废。
 *
 * 命中检测用 elementFromPoint + 采样插值（约 20px 步长），快速甩动也能
 * 覆盖跳过的中间照片。同一张照片一次手势内只上报一次，来回滑动不重复处理。
 * 消耗长按后的 touchend，避免浏览器合成的 click 再次切换起始照片。
 */

export interface SwipeSelectOptions {
  /** 滑选路径命中照片卡片时调用（shouldSelect 为本次手势的目标状态）。 */
  onSwipePhoto: (photoId: string, shouldSelect: boolean) => void
  /** 长按触发时调用（进入选择模式 + toggle 起始照片）。 */
  onLongPressActivate: (photoId: string) => void
  /** touchend 无法取消时的合成 click 兜底。 */
  onSuppressClick: () => void
  /** 手势是否可用（调用方判断移动端视口等条件）。 */
  canStart: () => boolean
  /** 长按触发后是否进入滑选（如单选场景只保留长按选择，不滑选）。 */
  canSweep: () => boolean
  /** 照片当前是否已选中，用于决定滑选目标状态。 */
  isSelected: (photoId: string) => boolean
  /** 长按触发延时，默认 450ms，与 useLongPress 保持一致。 */
  longPressDelay?: number
  /** 等待期触点位移容差，默认 10px，与 useLongPress 保持一致。 */
  moveTolerance?: number
}

export function useSwipeSelect(options: SwipeSelectOptions) {
  const longPressDelay = options.longPressDelay ?? 450
  const moveTolerance = options.moveTolerance ?? 10
  const SWEEP_SAMPLE_STEP = 20

  const longPressFired = ref(false)
  let active = false

  let timer: ReturnType<typeof setTimeout> | null = null
  let startX = 0
  let startY = 0
  let lastX = 0
  let lastY = 0
  let touchId: number | null = null
  let gallery: HTMLElement | null = null
  let swipeTarget = true
  const handledIds = new Set<string>()

  const clear = () => {
    if (timer) clearTimeout(timer)
    timer = null
    active = false
    longPressFired.value = false
    touchId = null
    gallery = null
    handledIds.clear()
    window.removeEventListener('touchmove', handleMove)
    window.removeEventListener('touchend', finish)
    window.removeEventListener('touchcancel', clear)
    window.removeEventListener('touchstart', cancelMultiTouch, true)
  }

  const finish = (event: TouchEvent) => {
    const touch = Array.from(event.changedTouches).find(item => item.identifier === touchId)
    if (!touch) return
    if (longPressFired.value) {
      if (active && (touch.clientX !== lastX || touch.clientY !== lastY)) sweepTo(touch.clientX, touch.clientY)
      if (event.cancelable) event.preventDefault()
      else options.onSuppressClick()
    }
    clear()
  }

  const cancelMultiTouch = (event: TouchEvent) => {
    if (event.touches.length > 1) clear()
  }

  const photoIdAtPoint = (x: number, y: number): string | null => {
    const target = document.elementFromPoint(x, y)?.closest<HTMLElement>('[data-photo-id]')
    return target && gallery?.contains(target) ? target.dataset.photoId ?? null : null
  }

  // 从上一次采样点向当前触点插值采样，命中路径上的所有照片卡片。
  const sweepTo = (toX: number, toY: number) => {
    const dx = toX - lastX
    const dy = toY - lastY
    const distance = Math.hypot(dx, dy)
    const steps = Math.max(1, Math.ceil(distance / SWEEP_SAMPLE_STEP))
    for (let i = 1; i <= steps; i++) {
      const photoId = photoIdAtPoint(lastX + dx * i / steps, lastY + dy * i / steps)
      if (photoId && !handledIds.has(photoId)) {
        handledIds.add(photoId)
        options.onSwipePhoto(photoId, swipeTarget)
      }
    }
    lastX = toX
    lastY = toY
  }

  const handleMove = (event: TouchEvent) => {
    if (event.touches.length !== 1) {
      clear()
      return
    }
    const touch = event.touches[0]
    if (touch.identifier !== touchId) return
    if (!active) {
      // 等待长按期间手指移出容差：取消长按，交还页面滚动。
      if (Math.hypot(touch.clientX - startX, touch.clientY - startY) > moveTolerance) clear()
      return
    }
    // 滑选进行中：阻止页面滚动，跟手更新命中集合。
    if (!event.cancelable) {
      clear()
      return
    }
    event.preventDefault()
    sweepTo(touch.clientX, touch.clientY)
  }

  const onTouchstart = (event: TouchEvent) => {
    if (event.touches.length !== 1 || !options.canStart()) return
    const touch = event.touches[0]
    const root = event.currentTarget as HTMLElement | null
    const startCard = (event.target as HTMLElement | null)?.closest<HTMLElement>('[data-photo-id]')
    const photoId = startCard?.dataset.photoId ?? null
    if (!startCard || !photoId || !root?.contains(startCard)) return

    clear()
    gallery = root
    touchId = touch.identifier
    startX = touch.clientX
    startY = touch.clientY
    lastX = startX
    lastY = startY
    handledIds.add(photoId)

    timer = setTimeout(() => {
      timer = null
      const wasSelected = options.isSelected(photoId)
      longPressFired.value = true
      options.onLongPressActivate(photoId)
      if (options.canSweep()) {
        // 目标状态取起始照片长按前选中态的反转：未选→滑过全选，已选→滑过全取消。
        swipeTarget = !wasSelected
        active = true
      }
    }, longPressDelay)

    window.addEventListener('touchmove', handleMove, { passive: false })
    window.addEventListener('touchend', finish, { passive: false })
    window.addEventListener('touchcancel', clear)
    window.addEventListener('touchstart', cancelMultiTouch, { capture: true, passive: true })
  }

  onBeforeUnmount(clear)

  return { onTouchstart, cancel: clear, longPressFired }
}
