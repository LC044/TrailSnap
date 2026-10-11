<template>
  <div v-if="maxScroll > 0" class="picker-scroll-track absolute bottom-3 right-0 top-3 z-40 w-11 touch-none select-none md:hidden"
    ref="track" role="scrollbar" aria-label="快速滚动照片" aria-orientation="vertical"
    :aria-valuenow="Math.round(progress * 100)" aria-valuemin="0" aria-valuemax="100" tabindex="0"
    @pointerdown="start" @pointermove="move" @pointerup="finish" @pointercancel="finish" @lostpointercapture="finish" @keydown="onKeydown">
    <div class="pointer-events-none absolute bottom-0 right-4 top-0 w-1 rounded-full bg-gray-200/70 dark:bg-gray-700/70" />
    <div class="pointer-events-none absolute right-1 flex h-[72px] w-9 items-center justify-center rounded-full border border-gray-200 bg-white/95 text-gray-600 shadow-md dark:border-gray-700 dark:bg-gray-800/95 dark:text-gray-200"
      :class="dragging && 'ring-2 ring-primary-500'" :style="{ top: `${progress * Math.max(0, trackHeight - 72)}px` }">
      <ChevronsUpDown class="h-5 w-5" aria-hidden="true" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ChevronsUpDown } from 'lucide-vue-next'

const props = defineProps<{ container: HTMLElement | null; content: HTMLElement | null }>()
const track = ref<HTMLElement | null>(null)
const maxScroll = ref(0)
const progress = ref(0)
const trackHeight = ref(0)
const dragging = ref(false)
let pointerId: number | null = null
let observer: ResizeObserver | null = null
const update = () => {
  const container = props.container
  maxScroll.value = container ? Math.max(0, container.scrollHeight - container.clientHeight) : 0
  progress.value = maxScroll.value && container ? Math.min(1, container.scrollTop / maxScroll.value) : 0
  trackHeight.value = Math.max(0, (container?.clientHeight ?? 0) - 24)
}
watch(() => [props.container, props.content], async (_value, _old, onCleanup) => {
  const container = props.container
  if (!container) return
  container.addEventListener('scroll', update, { passive: true })
  observer = new ResizeObserver(update)
  observer.observe(container)
  if (props.content) observer.observe(props.content)
  const currentObserver = observer
  onCleanup(() => { container.removeEventListener('scroll', update); currentObserver.disconnect() })
  await nextTick()
  update()
}, { immediate: true, flush: 'post' })
const scrollAt = (clientY: number) => {
  const rect = track.value?.getBoundingClientRect()
  if (!rect || !props.container) return
  const fraction = Math.max(0, Math.min(1, (clientY - rect.top - 36) / Math.max(1, rect.height - 72)))
  props.container.scrollTop = fraction * maxScroll.value
  update()
}
const start = (event: PointerEvent) => {
  if (event.button !== 0) return
  event.preventDefault()
  pointerId = event.pointerId
  dragging.value = true
  track.value?.setPointerCapture(event.pointerId)
  scrollAt(event.clientY)
}
const move = (event: PointerEvent) => {
  if (event.pointerId === pointerId) scrollAt(event.clientY)
}
const finish = () => { dragging.value = false; pointerId = null }
const onKeydown = (event: KeyboardEvent) => {
  const container = props.container
  if (!container) return
  const steps: Record<string, number> = {
    ArrowDown: 80, ArrowUp: -80, PageDown: container.clientHeight, PageUp: -container.clientHeight,
    Home: -maxScroll.value, End: maxScroll.value,
  }
  if (!(event.key in steps)) return
  event.preventDefault()
  container.scrollTop += steps[event.key]
  update()
}
onBeforeUnmount(() => observer?.disconnect())
</script>

<style scoped>
.picker-scroll-track:focus-visible { outline: 2px solid var(--theme-primary); outline-offset: -2px; border-radius: 999px; }
</style>
