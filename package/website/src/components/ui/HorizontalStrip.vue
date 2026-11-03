<template>
  <div class="horizontal-strip">
    <div ref="strip" :class="stripClass" @scroll.passive="onScroll"><slot /></div>
    <button v-if="canPrevious" type="button" class="horizontal-strip__arrow horizontal-strip__arrow--previous" :aria-label="`向前浏览${label}`" @click="move(-1)"><ChevronLeft class="h-5 w-5" /></button>
    <button v-if="canNext" type="button" class="horizontal-strip__arrow horizontal-strip__arrow--next" :aria-label="`向后浏览${label}`" @click="move(1)"><ChevronRight class="h-5 w-5" /></button>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'

defineProps<{ label: string; stripClass: string }>()
const emit = defineEmits<{ scroll: [event: Event] }>()
const strip = ref<HTMLElement | null>(null)
const canPrevious = ref(false)
const canNext = ref(false)
let resizeObserver: ResizeObserver | undefined
let mutationObserver: MutationObserver | undefined

function update() {
  const el = strip.value
  if (!el) return
  canPrevious.value = el.scrollLeft > 1
  canNext.value = el.scrollLeft + el.clientWidth < el.scrollWidth - 1
}
function onScroll(event: Event) { update(); emit('scroll', event) }
function move(direction: number) { if (strip.value) strip.value.scrollBy({ left: direction * strip.value.clientWidth * 0.8, behavior: 'smooth' }) }
function setScrollLeft(value: number) { if (strip.value) { strip.value.scrollLeft = value; update() } }
defineExpose({ setScrollLeft })
onMounted(() => {
  if (!strip.value) return
  resizeObserver = new ResizeObserver(update)
  resizeObserver.observe(strip.value)
  mutationObserver = new MutationObserver(update)
  mutationObserver.observe(strip.value, { childList: true, subtree: true })
  update()
})
onBeforeUnmount(() => { resizeObserver?.disconnect(); mutationObserver?.disconnect() })
</script>

<style scoped>
.horizontal-strip { position: relative; min-width: 0; }
.horizontal-strip__arrow { display: none; position: absolute; top: 50%; z-index: 1; width: 44px; height: 44px; align-items: center; justify-content: center; border: 1px solid var(--ts-color-border); border-radius: 9999px; background: var(--ts-color-surface); color: var(--ts-color-text); box-shadow: var(--ts-shadow-card); transform: translateY(-50%); }
.horizontal-strip__arrow:focus-visible { outline: 2px solid var(--theme-primary); outline-offset: 2px; }
.horizontal-strip__arrow--previous { left: 4px; }
.horizontal-strip__arrow--next { right: 4px; }
@media (min-width: 768px) { .horizontal-strip__arrow { display: flex; } }
</style>
