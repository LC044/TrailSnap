import { ref } from 'vue'
import { useResizeObserver } from '@vueuse/core'

export function useHorizontalScroll() {
  const container = ref<HTMLElement | null>(null)
  const canScrollLeft = ref(false)
  const canScrollRight = ref(false)
  const update = () => {
    const el = container.value
    canScrollLeft.value = !!el && el.scrollLeft > 1
    canScrollRight.value = !!el && el.scrollLeft + el.clientWidth < el.scrollWidth - 1
  }
  useResizeObserver(container, update)
  const scroll = (direction: number) => {
    const el = container.value
    el?.scrollBy({ left: direction * el.clientWidth * 0.8, behavior: 'smooth' })
  }
  return { container, canScrollLeft, canScrollRight, update, scroll }
}
