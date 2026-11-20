<template>
  <div v-if="maxScroll > 0" class="picker-scroll-track pointer-events-none absolute right-0 z-40 w-7 select-none md:hidden"
    ref="track" role="scrollbar" aria-label="快速滚动照片" aria-orientation="vertical"
    :aria-valuenow="Math.round(progress * 100)" aria-valuemin="0" aria-valuemax="100" tabindex="0"
    @pointerdown="start" @pointermove="move" @pointerup="finish" @pointercancel="finish" @lostpointercapture="finish" @keydown="onKeydown">
    <div class="pointer-events-auto absolute bottom-0 right-3 top-0 w-1 touch-none rounded-full bg-gray-200/70 dark:bg-gray-700/70" />
    <div class="pointer-events-auto absolute right-0.5 flex w-6 touch-none items-center justify-center rounded-full border border-gray-200 bg-white/95 text-gray-600 shadow-md dark:border-gray-700 dark:bg-gray-800/95 dark:text-gray-200"
      :class="dragging && 'ring-2 ring-primary-500'" :style="{ height: `${thumbHeight}px`, top: `calc(${progress * 100}% - ${progress * thumbHeight}px)` }">
      <ChevronsUpDown class="h-4 w-4" aria-hidden="true" />
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
const thumbHeight = 56
const dragging = ref(false)
let pointerId: number | null = null
let observer: ResizeObserver | null = null
const update = () => {
  const container = props.container
  maxScroll.value = container ? Math.max(0, container.scrollHeight - container.clientHeight) : 0
  progress.value = maxScroll.value && container ? Math.min(1, container.scrollTop / maxScroll.value) : 0
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
  const fraction = Math.max(0, Math.min(1, (clientY - rect.top - thumbHeight / 2) / Math.max(1, rect.height - thumbHeight)))
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
.picker-scroll-track { top: calc(var(--photo-page-header-height) + 8px); bottom: calc(12px + var(--ts-safe-area-bottom)); }
.picker-scroll-track:focus-visible { outline: 2px solid var(--theme-primary); outline-offset: -2px; border-radius: 999px; }
</style>
